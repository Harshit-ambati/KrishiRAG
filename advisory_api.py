import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import date
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from advisory_rules import decision, requested_day
from advisory_generation import ChatProvider, CitedClaim, render_with_provider
from advisory_log import decision_signature, deliver, ensure_advisory_tables, latest_run
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
    translate_advisory_id: UUID | None = None

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
        if self.translate_advisory_id is not None:
            allowed = {"session_id", "language", "translate_advisory_id"}
            if not (self.session_id and self.language) or self.model_fields_set - allowed:
                raise ValueError("Translate with only the advisory ID, its session ID, and the new language.")
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
    claims: list[CitedClaim] = Field(default_factory=list)
    decision_code: str | None = None
    forecast_rainfall_mm: float | None = None
    generation_outcome: Literal["system", "verified_template", "llm", "provider_error", "invalid_output", "demo"] = "system"


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
        is_demo=True, generation_outcome="demo",
    )


def evaluate(session: AdvisorySession, connection, advisory_id=None):
    supported_location = session.district_id in DISTRICTS.get(session.state_id, set())
    if session.demo_scenario and supported_location:
        response = evaluate_demo(session)
        return (response.model_copy(update={"advisory_id": advisory_id}) if advisory_id else response), {}

    try:
        result = decision(session, connection, supported_location)
    except EvidenceIndexUnavailable as exc:
        raise HTTPException(503, detail="evidence_index_unavailable") from exc
    wording = result.pop("claim_wording", {})
    response = AdvisoryResponse(
        advisory_id=advisory_id or uuid4(), session_id=session.session_id, language=session.language,
        crop_stage=session.crop_stage, requested_date=session.requested_date, is_demo=False,
        generation_outcome="verified_template" if wording else "system", **result,
    )
    return response, wording


def load_session(connection, request: AdvisoryRequest) -> AdvisorySession:
    if request.session_id is None:
        session = AdvisorySession(session_id=uuid4(), **request.model_dump(exclude={"session_id", "translate_advisory_id"}))
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


@contextmanager
def advisory_transaction():
    database = Path(os.environ.get("AGRIRAG_DB_PATH", ROOT / "data" / "advisories.sqlite3"))
    database.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(database, timeout=20)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        ensure_evidence_schema(connection)
        ensure_advisory_tables(connection)
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
    finally:
        connection.close()


def request_fingerprint(request, exclude=None):
    return sha256(request.model_dump_json(exclude=exclude).encode("utf-8")).hexdigest()


def replay_request(connection, request, key, fingerprint):
    if not key:
        return None
    cached = connection.execute(
        "SELECT fingerprint, response FROM advisory_retries WHERE request_key = ?", (key,)
    ).fetchone()
    if not cached:
        return None
    valid = {fingerprint}
    if request.translate_advisory_id is None:
        valid.add(request_fingerprint(request, {"translate_advisory_id"}))
        if request.requested_date is None:
            valid.add(request_fingerprint(request, {"requested_date", "translate_advisory_id"}))
    if cached["fingerprint"] not in valid:
        raise HTTPException(409, detail="request_key_reused")
    return json.loads(cached["response"])


router = APIRouter()


@router.post("/api/advisories")
def create_advisory(
    request: AdvisoryRequest,
    idempotency_key: Annotated[str | None, Header(min_length=16, max_length=100)] = None,
) -> AdvisoryResponse:
    fingerprint = request_fingerprint(request)
    with advisory_transaction() as connection:
        replay = replay_request(connection, request, idempotency_key, fingerprint)
        translation_run = None
        if request.translate_advisory_id:
            translation_run = latest_run(connection, request.translate_advisory_id, request.session_id)
            if translation_run is None:
                raise HTTPException(404, detail="advisory_not_found")
        if replay and "context" not in replay:
            previous = AdvisoryResponse.model_validate(replay)
            session = load_session(connection, AdvisoryRequest(session_id=previous.session_id))
            return deliver(connection, session, previous)
        if replay:
            session = AdvisorySession.model_validate(replay["context"])
        elif translation_run:
            session = AdvisorySession.model_validate_json(translation_run["context"])
            session.language = request.language
        else:
            session = load_session(connection, request)
            save_session(connection, session)

        response, wording = evaluate(session, connection, UUID(replay["advisory_id"]) if replay else None)
        signature = decision_signature(response)
        if translation_run and signature != translation_run["decision_signature"]:
            raise HTTPException(409, detail="advisory_changed")
        if replay:
            delivered = latest_run(connection, response.advisory_id, response.session_id)
            if delivered and delivered["decision_signature"] == signature:
                return AdvisoryResponse.model_validate_json(delivered["response"])
        if idempotency_key and not replay:
            connection.execute(
                "INSERT INTO advisory_retries VALUES (?, ?, ?)",
                (idempotency_key, fingerprint, json.dumps({
                    "context": session.model_dump(mode="json"), "advisory_id": str(response.advisory_id),
                })),
            )
        provider = ChatProvider.configured() if wording else None
        if provider is None:
            return deliver(connection, session, response)

    # Provider I/O runs outside the SQLite write lock.
    proposed = render_with_provider(provider, session, response, wording)
    with advisory_transaction() as connection:
        fresh, _ = evaluate(session, connection, response.advisory_id)
        if decision_signature(fresh) != signature:
            if translation_run:
                raise HTTPException(409, detail="advisory_changed")
            return deliver(connection, session, fresh)
        return deliver(connection, session, proposed, provider.model)


def save_session(connection, session):
    connection.execute("""
        INSERT INTO advisory_sessions (session_id, context) VALUES (?, ?)
        ON CONFLICT(session_id) DO UPDATE SET context = excluded.context
    """, (str(session.session_id), session.model_dump_json()))
