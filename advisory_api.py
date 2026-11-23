import json
import os
import sqlite3
from contextlib import closing
from datetime import date
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from advisory_rules import decision, requested_day
from evidence_index import EvidenceIndexUnavailable
from evidence_store import ensure_evidence_schema

ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / "dist" / "coverage.json").read_text(encoding="utf-8"))
FIXTURES = json.loads((ROOT / "demo_advisories.json").read_text(encoding="utf-8"))
DISTRICTS = {
    state["id"]: {district["id"] for district in state["districts"] if district["enabled"]}
    for state in CONFIG["coverage"]
}
CONTEXT_FIELDS = ("state_id", "district_id", "crop")
Language = Literal["en", "te", "hi"]
DemoStatus = Literal["supported", "conditional", "clarification", "coverageGap", "conflict"]
Status = Literal["supported", "conditional", "clarification", "coverageGap", "conflict",
                 "insufficient_evidence", "conflicting_evidence"]
Identifier = Annotated[str, Field(min_length=1, max_length=80)]
Question = Annotated[str, Field(min_length=1, max_length=1200)]


class AdvisoryRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    state_id: Identifier | None = None
    district_id: Identifier | None = None
    crop: Identifier | None = None
    crop_stage: Identifier | None = None
    question: Question | None = None
    language: Language | None = None
    field_observations: Annotated[str, Field(max_length=1200)] | None = None
    session_id: UUID | None = None
    demo_scenario: DemoStatus | None = None
    requested_date: date | None = None

    @field_validator("crop")
    @classmethod
    def supported_crop(cls, value):
        if value is not None and value not in CONFIG["crops"]:
            raise ValueError("Unsupported crop")
        return value

    @field_validator("crop_stage")
    @classmethod
    def supported_stage(cls, value):
        if value not in (None, "unknown") and value not in CONFIG["stages"]:
            raise ValueError("Unsupported crop stage")
        return value

    @model_validator(mode="after")
    def validate_initial_fields(self):
        if self.session_id is None:
            required = (*CONTEXT_FIELDS, "crop_stage", "question", "language")
            missing = [field for field in required if getattr(self, field) is None]
            if missing:
                raise ValueError(f"Required to start a session: {', '.join(missing)}")
        return self


class DemoEvidence(BaseModel):
    title: str
    is_demo: Literal[True] = True


class EvidenceReference(BaseModel):
    is_demo: Literal[False] = False
    title: str
    publisher: str
    original_url: str
    source_id: str
    passage_id: str
    version: str
    issue_date: date | None
    valid_from: date | None
    valid_until: date | None
    state_id: str
    district_id: str | None
    crop: str | None
    crop_stage: str | None
    topic: str
    page_number: int | None
    section: str | None
    sha256: str | None
    excerpt: str
    language: str


class ValidityWindow(BaseModel):
    valid_from: date
    valid_until: date


class AdvisoryResponse(BaseModel):
    advisory_id: UUID
    session_id: UUID
    language: Language
    crop_stage: str
    status: Status
    suggested_action: str
    explanation: str
    follow_up_question: str | None
    follow_up_field: Literal["crop_stage", "field_observations"] | None
    evidence: list[EvidenceReference | DemoEvidence]
    validity_window: ValidityWindow | None
    is_demo: bool
    requested_date: date | None = None


class AdvisorySession(BaseModel):
    session_id: UUID
    state_id: str
    district_id: str
    crop: str
    crop_stage: str
    question: str
    language: Language
    field_observations: str | None = None
    demo_scenario: DemoStatus | None = None
    requested_date: date | None = None
    date_explicit: bool | None = None


def evaluate_demo(session: AdvisorySession) -> AdvisoryResponse:
    question = session.question.casefold()
    follow_up_field = None
    scenario = session.demo_scenario
    if session.crop_stage == "unknown":
        status = "clarification"
        follow_up_field = "crop_stage"
    elif scenario == "clarification" and not session.field_observations:
        status = "clarification"
        follow_up_field = "field_observations"
    elif scenario and scenario != "clarification":
        status = scenario
    elif any(term in question for term in ("spray", "पिचकारी", "छिड़क", "छिडक", "పిచికారీ")):
        status = "conditional"
    elif any(term in question for term in ("irrigat", "drain", "waterlog", "सिंचाई", "पानी", "जल निकासी", "సాగునీ", "నీరు", "నీటి", "కాలువ")):
        status = "supported"
    else:
        status = "coverageGap"

    if status == "conditional" and not session.field_observations:
        follow_up_field = "field_observations"

    fixture = FIXTURES[status]
    if status == "clarification" and follow_up_field == "field_observations":
        fixture = fixture["observation"]
    copy = fixture[session.language]
    return AdvisoryResponse(
        advisory_id=uuid4(), session_id=session.session_id, language=session.language,
        crop_stage=session.crop_stage, status=status,
        suggested_action=copy["action"], explanation=copy["explanation"],
        follow_up_question=copy.get("follow_up_question") if follow_up_field else None,
        follow_up_field=follow_up_field,
        evidence=[DemoEvidence(title=source[session.language]) for source in fixture.get("sources", [])],
        validity_window=fixture.get("validity_window"),
        is_demo=True,
    )


def evaluate(session: AdvisorySession, connection, advisory_id=None) -> AdvisoryResponse:
    supported_location = session.district_id in DISTRICTS.get(session.state_id, set())
    if session.demo_scenario and supported_location:
        return evaluate_demo(session)

    try:
        result = decision(session, connection, supported_location)
    except EvidenceIndexUnavailable as exc:
        raise HTTPException(503, detail="evidence_index_unavailable") from exc
    return AdvisoryResponse(
        advisory_id=advisory_id or uuid4(), session_id=session.session_id, language=session.language,
        crop_stage=session.crop_stage, requested_date=session.requested_date, is_demo=False, **result,
    )


def load_session(connection, request: AdvisoryRequest) -> AdvisorySession:
    if request.session_id is None:
        session = AdvisorySession(session_id=uuid4(), **request.model_dump(exclude={"session_id"}))
        session.requested_date, session.date_explicit = requested_day(session.question, request.requested_date)
        return session

    row = connection.execute(
        "SELECT context FROM advisory_sessions WHERE session_id = ?", (str(request.session_id),)
    ).fetchone()
    if row is None:
        raise HTTPException(404, detail="session_not_found")
    session = AdvisorySession.model_validate_json(row[0])
    for field in (*CONTEXT_FIELDS, "demo_scenario"):
        value = getattr(request, field)
        if value is not None and value != getattr(session, field):
            raise HTTPException(409, detail="session_context_mismatch")

    if session.date_explicit is None:
        session.requested_date, session.date_explicit = requested_day(session.question, request.requested_date)
    elif request.requested_date and request.requested_date != session.requested_date:
        raise HTTPException(409, detail="session_context_mismatch")
    # A follow-up supplies context for the question already stored in this session.
    if request.crop_stage and request.crop_stage != "unknown":
        session.crop_stage = request.crop_stage
    if request.field_observations:
        session.field_observations = request.field_observations
    if request.language is not None:
        session.language = request.language
    return session


router = APIRouter()


@router.post("/api/advisories")
def create_advisory(
    request: AdvisoryRequest,
    idempotency_key: Annotated[str | None, Header(min_length=16, max_length=100)] = None,
) -> AdvisoryResponse:
    database = Path(os.environ.get("AGRIRAG_DB_PATH", ROOT / "data" / "advisories.sqlite3"))
    database.parent.mkdir(parents=True, exist_ok=True)

    with closing(sqlite3.connect(database, timeout=20)) as connection, connection:
        connection.row_factory = sqlite3.Row
        ensure_evidence_schema(connection)
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS advisory_sessions (
                session_id TEXT PRIMARY KEY,
                context TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS advisory_retries (
                request_key TEXT PRIMARY KEY,
                fingerprint TEXT NOT NULL,
                response TEXT NOT NULL
            );
        """)
        connection.execute("BEGIN IMMEDIATE")
        if idempotency_key:
            fingerprint = sha256(request.model_dump_json().encode("utf-8")).hexdigest()
            cached = connection.execute(
                "SELECT fingerprint, response FROM advisory_retries WHERE request_key = ?", (idempotency_key,)
            ).fetchone()
            if cached:
                # Demo retries created before requested_date was added used the older schema.
                legacy_fingerprint = sha256(request.model_dump_json(exclude={"requested_date"}).encode("utf-8")).hexdigest()
                if fingerprint != cached[0] and (request.requested_date is not None or legacy_fingerprint != cached[0]):
                    raise HTTPException(409, detail="request_key_reused")
                recorded = json.loads(cached[1])
                if "context" not in recorded:
                    return AdvisoryResponse.model_validate(recorded)
                # Recheck SQLite on exact retries. An archived source must never
                # leak back through the previously cached advisory.
                context = AdvisorySession.model_validate(recorded["context"])
                return evaluate(context, connection, UUID(recorded["advisory_id"]))

        session = load_session(connection, request)
        response = evaluate(session, connection)
        connection.execute("""
            INSERT INTO advisory_sessions (session_id, context) VALUES (?, ?)
            ON CONFLICT(session_id) DO UPDATE SET context = excluded.context
        """, (str(session.session_id), session.model_dump_json()))
        if idempotency_key:
            saved = response.model_dump_json() if response.is_demo else json.dumps({
                "context": session.model_dump(mode="json"), "advisory_id": str(response.advisory_id),
            })
            connection.execute(
                "INSERT INTO advisory_retries VALUES (?, ?, ?)",
                (idempotency_key, fingerprint, saved),
            )
        return response
