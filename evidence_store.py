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
)

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
    extracted_page INTEGER, extracted_text TEXT, extraction_note TEXT
);
CREATE INDEX IF NOT EXISTS evidence_scope ON evidence_passages(district_id, status, document_id);
"""


@contextmanager
def evidence_db(write=False):
    database = Path(os.environ.get("AGRIRAG_DB_PATH", ROOT / "data" / "advisories.sqlite3"))
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(SCHEMA)
        if write:
            connection.execute("BEGIN IMMEDIATE")
        yield connection
