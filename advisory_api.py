import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from advisory_rules import ACTIONS, INDIA, WEATHER_TOPIC, applicable, citation, decision, needs_forecast, preferred, question_topic, rainfall_on, requested_day
from advisory_generation import ChatProvider, CitedClaim, render_with_provider
from advisory_log import decision_signature, deliver, ensure_advisory_tables, latest_run
from evidence_index import EvidenceIndexUnavailable
from evidence_coverage import reviewed_crops
from evidence_store import database_path, ensure_evidence_schema, evidence_db
from general_farming import DECISION as GENERAL_DECISION, answer_with_evidence, approved_general_passages, current_evidence, retrieve
from general_farming import CLARIFICATION, CLARIFICATION_PREFIX, clarification_response
from live_weather import FORECAST_DAYS, Forecast, fetch_forecast, fetch_forecast_days, forecast_configured
from locations import CONFIG, DISTRICTS, DEMO_DISTRICTS
from trusted_web import pinned_web_rows, search_publications, web_enabled

ROOT = Path(__file__).resolve().parent
FIXTURES = json.loads((ROOT / "demo_advisories.json").read_text(encoding="utf-8"))
CONTEXT_FIELDS = ("state_id", "district_id", "crop", "question_type")
Language = Literal["en", "te", "hi"]
QuestionType = Literal["local", "general"]
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
    question_type: QuestionType | None = None
    field_observations: Annotated[str, Field(max_length=1200)] | None = None
    session_id: UUID | None = None
    demo_scenario: DemoStatus | None = None
    requested_date: date | None = None
    translate_advisory_id: UUID | None = None

    @field_validator("crop")
    @classmethod
    def supported_crop(cls, value):
        if value is not None and value not in CONFIG["crop_stages"]:
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
            required = ("question", "language") if self.question_type == "general" else (
                "state_id", "district_id", "question", "language",
            )
            missing = [field for field in required if getattr(self, field) is None]
            if missing:
                raise ValueError(f"Required to start a session: {', '.join(missing)}")
            if self.question_type != "general" and self.district_id not in DISTRICTS.get(self.state_id, set()):
                raise ValueError("District does not belong to the selected state")
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
    answer: str | None = None
    explanation: str
    follow_up_question: str | None
    follow_up_field: Literal["crop_stage", "field_observations"] | None
    follow_up_kind: Literal["soil_moisture"] | None = None
    evidence: list[EvidenceReference | DemoEvidence]
    validity_window: ValidityWindow | None
    is_demo: bool
    requested_date: date | None = None
    claims: list[CitedClaim] = Field(default_factory=list)
    decision_code: str | None = None
    forecast_rainfall_mm: float | None = None
    weather_snapshot: Forecast | None = None
    answer_type: Literal["advice", "information"] = "advice"
    generation_outcome: Literal[
        "system", "verified_template", "llm", "provider_limit", "provider_error", "invalid_output", "demo",
    ] = "system"


class AdvisorySession(BaseModel):
    session_id: UUID
    state_id: str
    district_id: str
    crop: str
    crop_stage: str
    question: str
    language: Language
    question_type: QuestionType = "local"
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


def evaluate(session: AdvisorySession, connection, advisory_id=None, forecast=None):
    supported_location = session.district_id in DISTRICTS.get(session.state_id, set())
    if session.demo_scenario and session.crop == "paddy" and session.state_id == "andhra-pradesh" and session.district_id in DEMO_DISTRICTS:
        response = evaluate_demo(session)
        return (response.model_copy(update={"advisory_id": advisory_id}) if advisory_id else response), {}

    try:
        result = decision(session, connection, supported_location, forecast)
    except EvidenceIndexUnavailable as exc:
        raise HTTPException(503, detail="evidence_index_unavailable") from exc
    wording = result.pop("claim_wording", {})
    response = AdvisoryResponse(
        advisory_id=advisory_id or uuid4(), session_id=session.session_id, language=session.language,
        crop_stage=session.crop_stage, requested_date=session.requested_date, is_demo=False,
        generation_outcome="verified_template" if wording else "system", **result,
    )
    return response, wording


def initial_session(request):
    fields = request.model_dump(exclude={"session_id", "translate_advisory_id"})
    fields["crop"] = request.crop or "none"
    fields["crop_stage"] = request.crop_stage or "unknown"
    fields["question_type"] = request.question_type or "local"
    if fields["question_type"] == "general":
        fields.update(state_id="india", district_id="national", crop="none", crop_stage="unknown")
    session = AdvisorySession(session_id=uuid4(), **fields)
    session.requested_date, session.date_explicit = (
        (datetime.now(INDIA).date(), False) if session.question_type == "general"
        else requested_day(session.question, request.requested_date)
    )
    return session


def demos_enabled():
    return os.environ.get("AGRIRAG_ENABLE_DEMOS") == "1"


def validate_demo(scenario):
    if scenario and not demos_enabled():
        raise HTTPException(404, detail="demo_disabled")


def validate_stage(session):
    if session.crop_stage != "unknown" and session.crop_stage not in CONFIG["crop_stages"].get(session.crop, ()):
        raise HTTPException(422, detail="stage_not_valid_for_crop")


def load_session(connection, request: AdvisoryRequest) -> AdvisorySession:
    if request.session_id is None:
        session = initial_session(request)
        validate_stage(session)
        return session

    row = connection.execute(
        "SELECT context FROM advisory_sessions WHERE session_id = ?", (str(request.session_id),)
    ).fetchone()
    if row is None:
        raise HTTPException(404, detail="session_not_found")
    session = AdvisorySession.model_validate_json(row[0])
    validate_demo(session.demo_scenario)
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
    if "field_observations" in request.model_fields_set and request.field_observations != "":
        session.field_observations = request.field_observations
    if request.language is not None:
        session.language = request.language
    validate_stage(session)
    return session


@contextmanager
def advisory_transaction():
    database = database_path()
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
    if request.question_type is None:
        exclude = (exclude or set()) | {"question_type"}
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


@router.get("/api/farm-config")
def farm_config(response: Response):
    response.headers["Cache-Control"] = "no-store"
    with evidence_db() as connection:
        scoped_crops = reviewed_crops(connection)

    coverage = []
    for state in CONFIG["coverage"]:
        state_id = state["id"]
        statewide = scoped_crops[state_id, None]
        districts = [
            {**district, "crop_ids": sorted(statewide | scoped_crops[state_id, district["id"]])}
            for district in state["districts"]
        ]
        crop_ids = sorted({crop for district in districts if district["enabled"] for crop in district["crop_ids"]})
        coverage.append({**state, "districts": districts, "crop_ids": crop_ids})

    config = {**CONFIG, "coverage": coverage}
    if not demos_enabled():
        config.pop("demo_districts")
    return config


@router.get("/api/forecast")
def district_forecast(state_id: Identifier, district_id: Identifier,
                      days: Annotated[int, Query(ge=1, le=FORECAST_DAYS)] = 3,
                      start_date: date | None = None):
    if district_id not in DISTRICTS.get(state_id, ()):
        raise HTTPException(422, detail="district_not_in_state")
    now = datetime.now(INDIA)
    first_day = start_date or now.date()
    try:
        last_day = first_day + timedelta(days=days - 1)
    except OverflowError as exc:
        raise HTTPException(422, detail="invalid_forecast_range") from exc
    live = fetch_forecast_days(state_id, district_id, first_day, last_day, now)
    context = SimpleNamespace(state_id=state_id, district_id=district_id, crop="none")
    outlook = []
    with evidence_db() as connection:
        for offset in range(days):
            day = first_day + timedelta(days=offset)
            key = day.isoformat()
            weather = preferred([row for row in applicable(connection, context, WEATHER_TOPIC, key)
                                 if row["kind"] == "weather" and row["stage_id"] is None and not row["crop_stage"]])
            amounts = {rainfall_on(row, key) for row in weather}
            point = live.get(day)
            rain, sources = None, []
            if len(amounts - {None}) > 1:
                rain_status = "conflicting"
                sources = [citation(row) for row in weather]
            elif len(amounts) == 1 and None not in amounts:
                rain = next(iter(amounts))
                rain_status = "reviewed"
                sources = [citation(row) for row in weather]
            elif point:
                rain, rain_status = point.rainfall_mm, "live"
            else:
                rain_status = "unavailable"
            outlook.append({
                "date": day, "rainfall_mm": rain, "rain_status": rain_status,
                "low_c": point.low_c if point else None, "high_c": point.high_c if point else None,
                "wind_kmh": point.wind_kmh if point else None, "sources": sources,
                "soil_moisture_m3_m3": point.soil_moisture_m3_m3 if point else None,
            })
    return {"state_id": state_id, "district_id": district_id, "timezone": "Asia/Kolkata",
            "live_retrieved_at": now if live else None, "days": outlook}


@router.get("/api/coverage")
def farm_coverage(state_id: Identifier, district_id: Identifier, crop: Identifier = "none",
                  crop_stage: Identifier = "unknown", on_date: date | None = None):
    if district_id not in DISTRICTS.get(state_id, ()):
        raise HTTPException(422, detail="district_not_in_state")
    if crop not in CONFIG["crop_stages"]:
        raise HTTPException(422, detail="unsupported_crop")
    context = SimpleNamespace(state_id=state_id, district_id=district_id, crop=crop, crop_stage=crop_stage)
    validate_stage(context)
    today = datetime.now(INDIA).date()
    day = on_date or today
    with evidence_db() as connection:
        rows = applicable(connection, context, None, day.isoformat())

    weather = preferred([row for row in rows if row["topic"] == WEATHER_TOPIC and row["kind"] == "weather"
                         and (row["stage_id"] == crop_stage or (row["stage_id"] is None and not row["crop_stage"]))])
    amounts = {rainfall_on(row, day.isoformat()) for row in weather}
    topics = []
    for topic, actions in ACTIONS.items():
        scoped = [row for row in rows if row["topic"] == topic and row["kind"] != "weather"
                  and (row["stage_id"] or not row["crop_stage"])]
        selected = preferred([row for row in scoped if row["stage_id"] in (None, crop_stage)])
        codes = {row["decision_code"] for row in selected}
        stage_codes = {row["decision_code"] for row in scoped if row["stage_id"]}
        if crop_stage == "unknown" and stage_codes & actions.keys() and (
                len(codes) != 1 or bool(stage_codes - codes)):
            topics.append({"topic": topic, "status": "stage_needed"})
        elif len(codes & actions.keys()) > 1:
            topics.append({"topic": topic, "status": "conflicting"})
        elif len(codes) == 1 and codes <= actions.keys():
            topics.append({"topic": topic, "status": "reviewed"})

    return {
        "on_date": day,
        "has_reviewed_forecast": len(amounts) == 1 and None not in amounts,
        "conflicting_forecasts": len(amounts - {None}) > 1,
        "live_forecast_configured": forecast_configured(state_id, district_id, day, today),
        "crop_topics": topics,
    }


def weather_context(request, key, fingerprint):
    if request.translate_advisory_id:
        return None
    if request.session_id or key:
        with advisory_transaction() as connection:
            replay = replay_request(connection, request, key, fingerprint)
            if replay:
                if "context" not in replay:
                    return None
                session = AdvisorySession.model_validate(replay["context"])
                return None if latest_run(connection, replay["advisory_id"], session.session_id) else session
            if request.session_id:
                return load_session(connection, request)
    session = initial_session(request)
    validate_stage(session)
    return session


def live_forecast_for(session):
    if not session or session.demo_scenario or session.question_type == "general":
        return None
    if not needs_forecast(session.question, question_topic(session.question), session.date_explicit):
        return None
    return fetch_forecast(session.state_id, session.district_id, session.requested_date, datetime.now(INDIA))


@router.post("/api/advisories")
def create_advisory(
    request: AdvisoryRequest,
    idempotency_key: Annotated[str | None, Header(min_length=16, max_length=100)] = None,
) -> AdvisoryResponse:
    validate_demo(request.demo_scenario)
    fingerprint = request_fingerprint(request)
    context = weather_context(request, idempotency_key, fingerprint)
    forecast = live_forecast_for(context)
    with advisory_transaction() as connection:
        replay = replay_request(connection, request, idempotency_key, fingerprint)
        translation_run = None
        previous = None
        if request.translate_advisory_id:
            translation_run = latest_run(connection, request.translate_advisory_id, request.session_id)
            if translation_run is None:
                raise HTTPException(404, detail="advisory_not_found")
            previous = AdvisoryResponse.model_validate_json(translation_run["response"])
        if replay and "context" not in replay:
            previous = AdvisoryResponse.model_validate(replay)
            session = load_session(connection, AdvisoryRequest(session_id=previous.session_id))
            return deliver(connection, session, previous)
        if replay:
            session = AdvisorySession.model_validate(replay["context"])
            run = latest_run(connection, replay["advisory_id"], session.session_id)
            if run:
                delivered = AdvisoryResponse.model_validate_json(run["response"])
                if ((delivered.decision_code or "").startswith(CLARIFICATION_PREFIX) or
                        delivered.decision_code == GENERAL_DECISION and current_evidence(connection, session, delivered)):
                    return delivered
                forecast = delivered.weather_snapshot
        elif translation_run:
            session = AdvisorySession.model_validate_json(translation_run["context"])
            session.language = request.language
            forecast = AdvisoryResponse.model_validate_json(translation_run["response"]).weather_snapshot
        else:
            session = load_session(connection, request) if request.session_id else context
            save_session(connection, session)

        validate_demo(session.demo_scenario)
        response, wording = evaluate(session, connection, UUID(replay["advisory_id"]) if replay else None, forecast)
        if previous and (previous.decision_code or "").startswith(CLARIFICATION_PREFIX):
            detail = previous.decision_code.removeprefix(CLARIFICATION_PREFIX)
            if detail in CLARIFICATION:
                response = clarification_response(response, detail)
        signature = decision_signature(response)
        dynamic_translation = previous is not None and previous.decision_code == GENERAL_DECISION
        open_question = session.question_type == "general" and response.status == "insufficient_evidence"
        if dynamic_translation and not current_evidence(connection, session, previous):
            raise HTTPException(409, detail="advisory_changed")
        if translation_run and not dynamic_translation and signature != translation_run["decision_signature"]:
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
        if session.question_type == "general" and wording:
            return deliver(connection, session, response)
        provider = ChatProvider.configured() if wording or open_question or dynamic_translation else None
        rows = []
        if provider and (open_question or dynamic_translation):
            rows = approved_general_passages(connection, session.requested_date.isoformat())
            if dynamic_translation:
                ids = {item.passage_id for item in previous.evidence}
                rows = pinned_web_rows(previous.evidence) or [row for row in rows if row["id"] in ids]
        if dynamic_translation and not rows:
            raise HTTPException(503, detail="general_answer_unavailable")
        if provider is None:
            return deliver(connection, session, response)
        search_web = open_question and not dynamic_translation and web_enabled(provider)
        if not wording and not rows and not search_web:
            return deliver(connection, session, response)

    # Provider I/O runs outside the SQLite write lock.
    if rows or search_web:
        candidates = rows if dynamic_translation else retrieve(session.question, rows)
        proposed = (answer_with_evidence(provider, session, response, candidates, previous if dynamic_translation else None)
                    if candidates else response)
        if search_web and proposed.status == "insufficient_evidence" and proposed.generation_outcome not in {
            "provider_limit", "provider_error",
        }:
            web_rows, error = search_publications(provider, session.question)
            if web_rows:
                proposed = answer_with_evidence(provider, session, response, web_rows)
            elif error:
                proposed = proposed.model_copy(update={"generation_outcome": error})
        with advisory_transaction() as connection:
            if not current_evidence(connection, session, proposed):
                if dynamic_translation:
                    raise HTTPException(409, detail="advisory_changed")
                return deliver(connection, session, response)
            if dynamic_translation:
                if proposed.status != "supported":
                    raise HTTPException(503, detail="general_answer_unavailable")
                if decision_signature(proposed) != translation_run["decision_signature"]:
                    raise HTTPException(409, detail="advisory_changed")
            if idempotency_key:
                delivered = latest_run(connection, response.advisory_id, response.session_id)
                if delivered:
                    cached = AdvisoryResponse.model_validate_json(delivered["response"])
                    if current_evidence(connection, session, cached):
                        return cached
            return deliver(connection, session, proposed, provider.model)

    proposed = render_with_provider(provider, session, response, wording)
    with advisory_transaction() as connection:
        fresh, _ = evaluate(session, connection, response.advisory_id, forecast)
        if decision_signature(fresh) != signature:
            if translation_run:
                raise HTTPException(409, detail="advisory_changed")
            return deliver(connection, session, fresh)
        if idempotency_key:
            delivered = latest_run(connection, response.advisory_id, session.session_id)
            if delivered and delivered["decision_signature"] == signature:
                return AdvisoryResponse.model_validate_json(delivered["response"])
        return deliver(connection, session, proposed, provider.model)


def save_session(connection, session):
    connection.execute("""
        INSERT INTO advisory_sessions (session_id, context) VALUES (?, ?)
        ON CONFLICT(session_id) DO UPDATE SET context = excluded.context
    """, (str(session.session_id), session.model_dump_json()))
