"""Report evidence upkeep and attach only checksum-matched original copies."""

import argparse
import json
from collections import Counter
from datetime import date, datetime, timedelta
from hashlib import sha256
from pathlib import Path

from advisory_log import ensure_advisory_tables
from advisory_rules import INDIA, question_topic
from evidence_coverage import national_coverage_inventory
from evidence_store import PUBLISHED_PASSAGES, evidence_db

MAX_SNAPSHOT_BYTES = 12 * 1024 * 1024


def maintenance_report(day):
    with evidence_db() as connection:
        ensure_advisory_tables(connection)
        inventory = national_coverage_inventory(connection, day)
        weather = connection.execute(f"""
            SELECT DISTINCT source_id AS id, title, version, state_id, district_id, effective_until AS valid_until
            FROM ({PUBLISHED_PASSAGES})
            WHERE kind = 'weather' AND effective_until <= ?
            ORDER BY valid_until, id, district_id
        """, ((day + timedelta(days=7)).isoformat(),))
        forecasts = [dict(row) for row in weather]
        missing_snapshots = [dict(row) for row in connection.execute("""
            SELECT id, title, version, sha256 IS NOT NULL AS has_checksum
            FROM source_documents
            WHERE source_verified = 1 AND status = 'approved' AND content IS NULL
            ORDER BY title, version
        """)]
        latest = connection.execute("""
            WITH recent AS (
                SELECT context, response, row_number() OVER (PARTITION BY session_id ORDER BY id DESC) AS newest
                FROM advisory_runs
                WHERE date(recorded_at, '+05:30') BETWEEN ? AND ?
            )
            SELECT context FROM recent
            WHERE newest = 1 AND json_extract(response, '$.is_demo') = 0
                AND json_extract(response, '$.status') = 'insufficient_evidence'
        """, ((day - timedelta(days=29)).isoformat(), day.isoformat()))
        gaps = Counter()
        for row in latest:
            farm = json.loads(row["context"])
            topic = question_topic(farm["question"]) or "unclassified"
            gaps[farm["state_id"], farm["district_id"], farm["crop"], farm["crop_stage"], topic] += 1
    return {
        "as_of": day.isoformat(),
        "national_coverage": inventory,
        "forecast_review": [
            {**row, "status": "expired" if row["valid_until"] < day.isoformat() else "expiring"}
            for row in forecasts
        ],
        "missing_snapshots": missing_snapshots,
        "coverage_gaps": [
            {"state_id": state, "district_id": district, "crop": crop, "crop_stage": stage,
             "topic": topic, "sessions": count}
            for (state, district, crop, stage, topic), count in sorted(gaps.items(), key=lambda item: (-item[1], item[0]))
        ],
    }


def attach_snapshot(source_id, path):
    with path.open("rb") as original:
        content = original.read(MAX_SNAPSHOT_BYTES + 1)
    if not content or len(content) > MAX_SNAPSHOT_BYTES:
        raise ValueError("Choose a nonempty original no larger than 12 MiB.")
    digest = sha256(content).hexdigest()
    with evidence_db(write=True) as connection:
        source = connection.execute("""
            SELECT sha256, content IS NOT NULL AS attached
            FROM source_documents
            WHERE id = ? AND source_verified = 1 AND status IN ('approved', 'archived')
        """, (source_id,)).fetchone()
        if not source or digest != source["sha256"]:
            raise ValueError("The file SHA-256 must match the audited checksum for this source edition.")
        if not source["attached"]:
            connection.execute("UPDATE source_documents SET content = ? WHERE id = ?", (content, source_id))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    report = commands.add_parser("report")
    report.add_argument("--date", type=date.fromisoformat, default=datetime.now(INDIA).date())
    attach = commands.add_parser("attach-snapshot")
    attach.add_argument("source_id")
    attach.add_argument("path", type=Path)
    args = parser.parse_args()
    if args.command == "report":
        print(json.dumps(maintenance_report(args.date), indent=2, ensure_ascii=True))
    else:
        try:
            attach_snapshot(args.source_id, args.path)
        except (ValueError, OSError) as exc:
            parser.error(str(exc))
        print(f"Audited snapshot attached for {args.source_id}.")
