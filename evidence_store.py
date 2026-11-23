import os
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOCUMENT_FIELDS = (
    "publisher", "title", "original_url", "language", "state_id", "geographic_scope",
    "issue_date", "valid_from", "valid_until", "version", "source_verified", "review_notes",
)
DOCUMENT_COLUMNS = ", ".join(("id", *DOCUMENT_FIELDS, "status", "revision", "filename", "sha256", "page_count", "superseded_by"))
PASSAGE_FIELDS = (
    "page_number", "section", "district_id", "language", "kind", "crop", "crop_stage",
    "topic", "valid_from", "valid_until", "content", "include", "reviewed", "review_notes",
    "stage_id", "statewide", "decision_code", "daily_rainfall",
)
DECISION_COLUMNS = {
    "stage_id": "TEXT", "statewide": "INTEGER NOT NULL DEFAULT 0",
    "decision_code": "TEXT", "daily_rainfall": "TEXT",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS source_documents (
    id TEXT PRIMARY KEY,
    publisher TEXT, title TEXT, original_url TEXT, language TEXT, state_id TEXT, geographic_scope TEXT,
    issue_date TEXT, valid_from TEXT, valid_until TEXT, version TEXT,
    source_verified INTEGER NOT NULL DEFAULT 0, review_notes TEXT,
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','approved','archived')),
    revision INTEGER NOT NULL DEFAULT 1,
    filename TEXT, sha256 TEXT, page_count INTEGER,
    content BLOB, superseded_by TEXT REFERENCES source_documents(id),
    UNIQUE(original_url, version)
);
CREATE TABLE IF NOT EXISTS evidence_passages (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES source_documents(id),
    page_number INTEGER, section TEXT, district_id TEXT, language TEXT, kind TEXT,
    crop TEXT, crop_stage TEXT, topic TEXT, valid_from TEXT, valid_until TEXT,
    content TEXT NOT NULL DEFAULT '', include INTEGER NOT NULL DEFAULT 0,
    reviewed INTEGER NOT NULL DEFAULT 0, review_notes TEXT,
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','approved')),
    extracted_page INTEGER, extracted_text TEXT, extraction_note TEXT,
    stage_id TEXT, statewide INTEGER NOT NULL DEFAULT 0, decision_code TEXT, daily_rainfall TEXT
);
CREATE INDEX IF NOT EXISTS evidence_scope ON evidence_passages(district_id, status, document_id);
"""

PUBLISHED_PASSAGES = """
SELECT p.*, d.id AS source_id, d.publisher, d.title, d.original_url, d.version, d.issue_date, d.sha256,
       d.state_id, COALESCE(p.language, d.language) AS evidence_language,
       COALESCE(p.valid_from, d.valid_from) AS effective_from,
       COALESCE(p.valid_until, d.valid_until) AS effective_until
FROM evidence_passages AS p JOIN source_documents AS d ON d.id = p.document_id
WHERE p.status = 'approved' AND p.reviewed = 1 AND d.status = 'approved' AND d.source_verified = 1
"""


def ensure_evidence_schema(connection):
    connection.executescript(SCHEMA)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(evidence_passages)")}
    if not DECISION_COLUMNS.keys() <= columns:
        connection.execute("BEGIN IMMEDIATE")
        columns = {row[1] for row in connection.execute("PRAGMA table_info(evidence_passages)")}
        for field, type_ in DECISION_COLUMNS.items():
            if field not in columns:
                connection.execute(f"ALTER TABLE evidence_passages ADD COLUMN {field} {type_}")
        connection.commit()


@contextmanager
def evidence_db(write=False):
    database = Path(os.environ.get("AGRIRAG_DB_PATH", ROOT / "data" / "advisories.sqlite3"))
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        ensure_evidence_schema(connection)
        if write:
            connection.execute("BEGIN IMMEDIATE")
        yield connection
