import argparse
import json
from hashlib import sha256
from pathlib import Path

from evidence_store import DOCUMENT_FIELDS, PASSAGE_FIELDS, evidence_db

SEED = Path(__file__).with_name("pilot_evidence.json")
EXPANSION_SEED = Path(__file__).with_name("expansion_evidence.json")


def seed(snapshots: Path | None):
    records = json.loads(SEED.read_text(encoding="utf-8"))
    files = {}
    if snapshots:
        for record in records:
            data = (snapshots / record["filename"]).read_bytes()
            if sha256(data).hexdigest() != record["sha256"]:
                raise ValueError(f'{record["filename"]} does not match the audited PDF.')
            files[record["id"]] = data
    expansion = json.loads(EXPANSION_SEED.read_text(encoding="utf-8"))

    with evidence_db(write=True) as connection:
        for record in [*records, *expansion]:
            document_id = record["id"]
            fields = (*DOCUMENT_FIELDS, "id", "filename", "sha256", "page_count", "status", "content")
            values = {
                **record["metadata"], **{field: record[field] for field in ("id", "filename", "sha256", "page_count")},
                "source_verified": True, "status": "approved", "content": files.get(document_id),
            }
            cursor = connection.execute(
                f"INSERT INTO source_documents ({', '.join(fields)}) VALUES ({', '.join('?' for _ in fields)}) "
                "ON CONFLICT (original_url, version) DO NOTHING",
                tuple(values.get(field) for field in fields),
            )
            if not cursor.rowcount:
                if document_id in files:
                    connection.execute(
                        "UPDATE source_documents SET content = ? WHERE id = ? AND sha256 = ? AND content IS NULL",
                        (files[document_id], document_id, record["sha256"]),
                    )
                # Add structured fields to the same originally audited, still-published records.
                for index, passage in enumerate(record["passages"], start=1):
                    rainfall = passage.get("daily_rainfall")
                    connection.execute("""
                        UPDATE evidence_passages
                        SET stage_id = COALESCE(stage_id, ?), decision_code = COALESCE(decision_code, ?),
                            daily_rainfall = COALESCE(daily_rainfall, ?)
                        WHERE id = ? AND document_id = ? AND status = 'approved' AND content = ?
                          AND EXISTS (
                              SELECT 1 FROM source_documents d WHERE d.id = ? AND d.sha256 = ? AND d.status = 'approved'
                          )
                    """, (passage.get("stage_id"), passage.get("decision_code"), json.dumps(rainfall) if rainfall else None,
                          f"{document_id}-{index}", document_id, passage["content"], document_id, record["sha256"]))
                continue
            fields = (*PASSAGE_FIELDS, "id", "document_id", "status", "extraction_note")
            for index, passage in enumerate(record["passages"], start=1):
                values = {
                    **passage, "id": f"{document_id}-{index}", "document_id": document_id,
                    "status": "approved", "reviewed": True, "include": True, "statewide": passage.get("statewide", False),
                    "daily_rainfall": json.dumps(passage["daily_rainfall"]) if passage.get("daily_rainfall") else None,
                    "review_notes": passage.get("review_notes") or record["metadata"].get("review_notes"),
                    "extraction_note": "Reviewed against the original section." if record in expansion
                    else "Manually reviewed against the rendered original PDF.",
                }
                connection.execute(
                    f"INSERT INTO evidence_passages ({', '.join(fields)}) VALUES ({', '.join('?' for _ in fields)})",
                    tuple(values.get(field) for field in fields),
                )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load reviewed starter evidence.")
    parser.add_argument("--snapshots", type=Path, help="Directory containing the original PDFs named in pilot_evidence.json.")
    args = parser.parse_args()
    seed(args.snapshots)
    print("Reviewed starter evidence loaded.")
