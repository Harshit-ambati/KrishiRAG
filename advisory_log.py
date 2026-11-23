import json
from hashlib import sha256

ADVISORY_TABLES = """
CREATE TABLE IF NOT EXISTS advisory_sessions (
    session_id TEXT PRIMARY KEY,
    context TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS advisory_retries (
    request_key TEXT PRIMARY KEY,
    fingerprint TEXT NOT NULL,
    response TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS advisory_runs (
    id INTEGER PRIMARY KEY,
    advisory_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    context TEXT NOT NULL,
    response TEXT NOT NULL,
    decision_signature TEXT NOT NULL,
    provider_model TEXT,
    recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(advisory_id, response)
);
CREATE INDEX IF NOT EXISTS advisory_runs_lookup ON advisory_runs(advisory_id, id DESC);
CREATE TABLE IF NOT EXISTS advisory_feedback (
    advisory_id TEXT PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES advisory_runs(id),
    rating TEXT NOT NULL CHECK(rating IN ('useful','unclear','potentially_incorrect')),
    recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def ensure_advisory_tables(connection):
    connection.executescript(ADVISORY_TABLES)


def decision_signature(response):
    stable = response.model_dump(mode="json", include={
        "status", "follow_up_field", "requested_date", "crop_stage", "validity_window",
        "decision_code", "forecast_rainfall_mm", "evidence", "is_demo",
    })
    # Demo source titles are localized and do not participate in an official evidence decision.
    if response.is_demo:
        stable.pop("evidence")
    return sha256(json.dumps(stable, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def latest_run(connection, advisory_id, session_id):
    return connection.execute("""
        SELECT * FROM advisory_runs WHERE advisory_id = ? AND session_id = ? ORDER BY id DESC LIMIT 1
    """, (str(advisory_id), str(session_id))).fetchone()


def deliver(connection, session, response, provider_model=None):
    connection.execute("""
        INSERT INTO advisory_runs (advisory_id, session_id, context, response, decision_signature, provider_model)
        VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(advisory_id, response) DO NOTHING
    """, (str(response.advisory_id), str(response.session_id), session.model_dump_json(),
          response.model_dump_json(), decision_signature(response), provider_model))
    return response
