import io
import json
import os
import secrets
import sqlite3
from datetime import date
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator
from pypdf import PdfReader

from advisory_api import CONFIG, DISTRICTS
from advisory_rules import ACTIONS, WEATHER_TOPIC
from evidence_store import DOCUMENT_COLUMNS, DOCUMENT_FIELDS, PASSAGE_FIELDS, evidence_db

ROOT = Path(__file__).resolve().parent
MAX_UPLOAD = 12 * 1024 * 1024
MAX_PAGES = 200
MAX_PASSAGES = 400
Language = Annotated[str, Field(pattern=r"^[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$", max_length=24)]
Short = Annotated[str, Field(max_length=240)]
Notes = Annotated[str, Field(max_length=1800)]
AreaId = Annotated[str, Field(max_length=80)]


class Dates(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    valid_from: date | None = None
    valid_until: date | None = None

    @model_validator(mode="after")
    def check_window(self):
        if (self.valid_from is None) != (self.valid_until is None):
            raise ValueError("Enter both validity dates or leave both blank.")
        if self.valid_from and self.valid_until < self.valid_from:
            raise ValueError("Validity end must be on or after its start.")
        return self


class DocumentMetadata(Dates):
    publisher: Short = ""
    title: Short = ""
    original_url: HttpUrl | None = None
    language: Language = "en"
    state_id: AreaId | None = None
    geographic_scope: Notes = ""
    issue_date: date | None = None
    version: Short = ""
    source_verified: bool = False
    review_notes: Notes = ""


class PassageReview(Dates):
    id: str | None = None
    page_number: Annotated[int, Field(ge=1)] | None = None
    section: Short = ""
    district_id: AreaId | None = None
    language: Language | None = None
    kind: Literal["advisory", "weather", "background"] = "background"
    crop: AreaId | None = None
    crop_stage: Short = ""
    topic: Short = ""
    stage_id: AreaId | None = None
    statewide: bool = False
    decision_code: AreaId | None = None
    daily_rainfall: Annotated[dict[date, Annotated[float, Field(ge=0, le=3000, allow_inf_nan=False)]], Field(max_length=366)] | None = None
    content: Annotated[str, Field(max_length=16000)] = ""
    include: bool = False
    reviewed: bool = False
    review_notes: Notes = ""


class DraftUpdate(BaseModel):
    revision: int = Field(ge=1)
    metadata: DocumentMetadata
    passages: list[PassageReview] = Field(max_length=MAX_PASSAGES)


class Revision(BaseModel):
    revision: int = Field(ge=1)


class ArchiveRequest(Revision):
    superseded_by: str | None = None


security = HTTPBasic()


def require_admin(credentials: Annotated[HTTPBasicCredentials, Depends(security)]):
    password = os.environ.get("AGRIRAG_ADMIN_PASSWORD")
    if not password:
        raise HTTPException(503, "Evidence administration is disabled until credentials are configured.")
    username = os.environ.get("AGRIRAG_ADMIN_USER", "admin")
    user_matches = secrets.compare_digest(credentials.username.encode(), username.encode())
    pass_matches = secrets.compare_digest(credentials.password.encode(), password.encode())
    if not (user_matches and pass_matches):
        raise HTTPException(401, "Invalid admin credentials.", headers={"WWW-Authenticate": "Basic"})


def require_admin_header(x_admin_request: Annotated[str | None, Header()] = None):
    if x_admin_request != "evidence-admin":
        raise HTTPException(403, "Required admin request header is missing.")


admin = APIRouter(dependencies=[Depends(require_admin)])
public = APIRouter()
mutating = [Depends(require_admin_header)]


def get_document(connection, document_id):
    row = connection.execute(f"SELECT {DOCUMENT_COLUMNS} FROM source_documents WHERE id = ?", (document_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Source document not found.")
    return dict(row)


def get_detail(connection, document_id):
    document = get_document(connection, document_id)
    document["passages"] = [dict(row) for row in connection.execute(
        "SELECT * FROM evidence_passages WHERE document_id = ? ORDER BY page_number, rowid", (document_id,)
    )]
    for passage in document["passages"]:
        passage["daily_rainfall"] = json.loads(passage["daily_rainfall"] or "null")
    document["has_snapshot"] = bool(connection.execute(
        "SELECT content IS NOT NULL FROM source_documents WHERE id = ?", (document_id,)
    ).fetchone()[0])
    return document


def require_version(document, revision, status):
    if document["revision"] != revision:
        raise HTTPException(409, "This source changed. Reload it before saving.")
    if document["status"] != status:
        raise HTTPException(409, f"This action requires a {status} source.")


def extract_pages(filename, data):
    suffix = Path(filename).suffix.lower()
    if suffix == ".txt":
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise HTTPException(422, "Text uploads must be UTF-8.") from exc
        return [(None, text[:16000], "UTF-8 text. Verify the original and record a section.")]
    if suffix != ".pdf" or not data.startswith(b"%PDF-"):
        raise HTTPException(415, "Upload a PDF or a UTF-8 text document.")
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted or len(reader.pages) > MAX_PAGES:
            raise HTTPException(422, "Upload an unlocked PDF with at most 200 pages.")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, "The PDF could not be opened.") from exc

    pages = []
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            text = (page.extract_text() or "").strip()
        except Exception:
            text = ""
        if not text or "\ufffd" in text or any("\ue000" <= char <= "\uf8ff" for char in text):
            note = "Extraction is empty or unreliable. Inspect the original image and transcribe this page manually."
        elif any("\u0c00" <= char <= "\u0c7f" for char in text):
            note = "Telugu detected. Check glyphs, line order and any table cells against the rendered page."
        else:
            note = "Check the original page. Columns and tables may be out of order in extracted text."
        if len(text) > 16000:
            note += " Preview shortened. Refer to the complete original."
        pages.append((page_number, text[:16000], note))
    if not pages:
        raise HTTPException(422, "The PDF has no pages.")
    return pages


@admin.get("/admin", include_in_schema=False)
def admin_page():
    return FileResponse(ROOT / "admin" / "index.html", headers={"Cache-Control": "no-store"})


@admin.get("/api/admin/evidence/config")
def admin_config():
    return {"coverage": CONFIG["coverage"], "crops": CONFIG["crops"], "stages": CONFIG["stages"],
            "decisions": {topic: list(codes) for topic, codes in ACTIONS.items()}}


@admin.get("/api/admin/evidence")
def list_sources():
    with evidence_db() as connection:
        return [dict(row) for row in connection.execute(
            f"SELECT {DOCUMENT_COLUMNS} FROM source_documents ORDER BY status, issue_date DESC, title"
        )]


@admin.get("/api/admin/evidence/{document_id}")
def read_source(document_id: str):
    with evidence_db() as connection:
        return get_detail(connection, document_id)


@admin.get("/api/admin/evidence/{document_id}/original")
def download_source(document_id: str):
    with evidence_db() as connection:
        row = connection.execute("SELECT filename, content FROM source_documents WHERE id = ?", (document_id,)).fetchone()
    if not row or row["content"] is None:
        raise HTTPException(404, "No local snapshot is attached to this source.")
    pdf = row["filename"].lower().endswith(".pdf")
    extension = "pdf" if pdf else "txt"
    return Response(row["content"], media_type="application/pdf" if pdf else "text/plain", headers={
        "Content-Disposition": f'attachment; filename="evidence.{extension}"',
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
    })


@admin.post("/api/admin/evidence", dependencies=mutating, status_code=201)
def upload_source(file: Annotated[UploadFile, File()]):
    filename = Path(file.filename or "").name
    data = file.file.read(MAX_UPLOAD + 1)
    if not data or len(data) > MAX_UPLOAD:
        raise HTTPException(413, "Choose a nonempty document no larger than 12 MiB.")
    pages = extract_pages(filename, data)
    document_id = str(uuid4())
    with evidence_db(write=True) as connection:
        connection.execute("""
            INSERT INTO source_documents (id, title, filename, sha256, content, page_count)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (document_id, Path(filename).stem[:240], filename, sha256(data).hexdigest(), data, pages[-1][0]))
        connection.executemany("""
            INSERT INTO evidence_passages
                (id, document_id, page_number, extracted_page, extracted_text, extraction_note)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ((str(uuid4()), document_id, page, page, text, note) for page, text, note in pages))
        return get_detail(connection, document_id)


@admin.put("/api/admin/evidence/{document_id}", dependencies=mutating)
def save_source(document_id: str, draft: DraftUpdate):
    metadata = draft.metadata.model_dump(mode="json")
    if metadata["state_id"] and metadata["state_id"] not in DISTRICTS:
        raise HTTPException(422, "Choose a configured state.")
    requested_ids = [passage.id for passage in draft.passages if passage.id is not None]
    if len(set(requested_ids)) != len(requested_ids):
        raise HTTPException(422, "A passage can be updated only once per save.")
    with evidence_db(write=True) as connection:
        document = get_document(connection, document_id)
        require_version(document, draft.revision, "draft")
        existing = {row[0] for row in connection.execute("SELECT id FROM evidence_passages WHERE document_id = ?", (document_id,))}
        if not set(requested_ids) <= existing:
            raise HTTPException(422, "A passage does not belong to this source.")
        if len(existing) + len(draft.passages) - len(requested_ids) > MAX_PASSAGES:
            raise HTTPException(422, "This source already has the maximum number of passages.")
        try:
            assignments = ", ".join(f"{field} = ?" for field in DOCUMENT_FIELDS)
            connection.execute(f"UPDATE source_documents SET {assignments}, revision = revision + 1 WHERE id = ?",
                               (*[metadata[field] for field in DOCUMENT_FIELDS], document_id))
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "This source URL and version already exist.") from exc
        for passage in draft.passages:
            save_passage(connection, document, metadata, passage)
        return get_detail(connection, document_id)


def save_passage(connection, document, metadata, passage):
    if passage.district_id and passage.district_id not in DISTRICTS.get(metadata["state_id"], set()):
        raise HTTPException(422, "A passage district is not enabled for the selected state.")
    if passage.crop and passage.crop not in CONFIG["crops"]:
        raise HTTPException(422, "Choose a configured passage crop.")
    if passage.stage_id and passage.stage_id not in CONFIG["stages"]:
        raise HTTPException(422, "Choose a configured crop stage.")
    if passage.statewide and passage.district_id:
        raise HTTPException(422, "District-specific passages cannot also be marked statewide.")
    if passage.decision_code and passage.decision_code not in ACTIONS.get(passage.topic, {}):
        raise HTTPException(422, "The reviewed decision does not match the passage topic.")
    if passage.daily_rainfall and (passage.kind != "weather" or passage.topic != WEATHER_TOPIC):
        raise HTTPException(422, "Daily rainfall belongs on district-rainfall-forecast weather passages.")
    if passage.page_number and document["page_count"] and passage.page_number > document["page_count"]:
        raise HTTPException(422, "A passage page is outside the uploaded PDF.")
    saved = passage.model_dump(mode="json")
    if saved["daily_rainfall"]:
        saved["daily_rainfall"] = json.dumps(saved["daily_rainfall"], sort_keys=True)
    else:
        saved["daily_rainfall"] = None
    values = [saved[field] for field in PASSAGE_FIELDS]
    if passage.id:
        assignments = ", ".join(f"{field} = ?" for field in PASSAGE_FIELDS)
        connection.execute(f"UPDATE evidence_passages SET {assignments} WHERE id = ?", (*values, passage.id))
    else:
        columns = ", ".join(PASSAGE_FIELDS)
        placeholders = ", ".join("?" for _ in PASSAGE_FIELDS)
        connection.execute(f"INSERT INTO evidence_passages (id, document_id, {columns}) VALUES (?, ?, {placeholders})",
                           (str(uuid4()), document["id"], *values))


@admin.post("/api/admin/evidence/{document_id}/publish", dependencies=mutating)
def publish_source(document_id: str, request: Revision):
    with evidence_db(write=True) as connection:
        document = get_detail(connection, document_id)
        require_version(document, request.revision, "draft")
        if not all(document[field] for field in ("publisher", "title", "version", "language", "state_id", "geographic_scope", "review_notes", "source_verified")):
            raise HTTPException(422, "Complete source metadata and record the original-link verification before publishing.")
        if not (document["original_url"] or "").startswith("https://"):
            raise HTTPException(422, "A verified HTTPS original URL is required.")
        included = [passage for passage in document["passages"] if passage["include"]]
        if not included:
            raise HTTPException(422, "Select at least one reviewed passage to publish.")
        for passage in included:
            validate_publication(document, passage)
        connection.execute("UPDATE evidence_passages SET status = 'approved' WHERE document_id = ? AND include = 1", (document_id,))
        connection.execute("UPDATE source_documents SET status = 'approved', revision = revision + 1 WHERE id = ?", (document_id,))
        return get_detail(connection, document_id)


def validate_publication(document, passage):
    if not all(passage[field] for field in ("reviewed", "review_notes", "content", "topic")) or not (passage["section"] or passage["page_number"]):
        raise HTTPException(422, "Each selected passage needs reviewed text, a page or section, a topic, and review notes.")
    if passage["district_id"] and passage["district_id"] not in DISTRICTS.get(document["state_id"], set()):
        raise HTTPException(422, "A selected passage district no longer matches the source state.")
    if passage["kind"] == "advisory" and not passage["crop"]:
        raise HTTPException(422, "Select a crop for each advisory passage.")
    start = passage["valid_from"] or document["valid_from"]
    if passage["kind"] == "weather" and not (passage["district_id"] and document["issue_date"] and start):
        raise HTTPException(422, "District weather passages need an issue date, district and explicit validity window.")
    end = passage["valid_until"] or document["valid_until"]
    if passage["daily_rainfall"] and any(not start <= day <= end for day in passage["daily_rainfall"]):
        raise HTTPException(422, "Every rainfall date must fall within the effective forecast window.")
    if start and document["issue_date"] and start < document["issue_date"]:
        raise HTTPException(422, "Passage validity cannot begin before the source issue date.")
    if passage["valid_from"] and document["valid_from"] and (
        passage["valid_from"] < document["valid_from"] or passage["valid_until"] > document["valid_until"]
    ):
        raise HTTPException(422, "A passage validity window falls outside the source window.")


@admin.post("/api/admin/evidence/{document_id}/archive", dependencies=mutating)
def archive_source(document_id: str, request: ArchiveRequest):
    with evidence_db(write=True) as connection:
        document = get_document(connection, document_id)
        require_version(document, request.revision, "approved")
        if request.superseded_by:
            replacement = get_document(connection, request.superseded_by)
            if replacement["id"] == document_id or replacement["status"] != "approved" or replacement["state_id"] != document["state_id"]:
                raise HTTPException(422, "Choose a different published replacement for the same state.")
        connection.execute("UPDATE source_documents SET status = 'archived', superseded_by = ?, revision = revision + 1 WHERE id = ?",
                           (request.superseded_by, document_id))
        return get_detail(connection, document_id)


@public.get("/api/evidence")
def published_evidence(state_id: str, district_id: str, on_date: date):
    if district_id not in DISTRICTS.get(state_id, set()):
        raise HTTPException(422, "District is not enabled for the selected state.")
    with evidence_db() as connection:
        rows = connection.execute("""
            SELECT p.id AS passage_id, d.id AS source_id, d.publisher, d.title, d.original_url, d.version,
                   d.issue_date, d.sha256, d.state_id, p.district_id, COALESCE(p.language, d.language) AS language,
                   p.kind, p.crop, p.crop_stage, p.topic, p.page_number, p.section, p.content,
                   COALESCE(p.valid_from, d.valid_from) AS valid_from,
                   COALESCE(p.valid_until, d.valid_until) AS valid_until
            FROM evidence_passages AS p JOIN source_documents AS d ON p.document_id = d.id
            WHERE d.status = 'approved' AND p.status = 'approved' AND d.state_id = ? AND p.district_id = ?
              AND (d.issue_date IS NULL OR d.issue_date <= ?)
              AND COALESCE(p.valid_from, d.valid_from) <= ? AND COALESCE(p.valid_until, d.valid_until) >= ?
            ORDER BY d.issue_date DESC, p.topic, p.id
        """, (state_id, district_id, on_date.isoformat(), on_date.isoformat(), on_date.isoformat()))
        passages = [dict(row) for row in rows]
    covered = any(p["kind"] == "weather" for p in passages) and any(p["kind"] == "advisory" and p["crop"] == "paddy" for p in passages)
    return {"state_id": state_id, "district_id": district_id, "on_date": on_date, "covered": covered, "passages": passages}
