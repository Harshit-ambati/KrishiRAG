import os
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import chromadb
from fastapi.testclient import TestClient

import evidence_index
from advisory_rules import requested_day
from evidence_seed import seed
from evidence_store import PUBLISHED_PASSAGES, ROOT, evidence_db
from main import app

REQUEST = {
    "state_id": "andhra-pradesh", "district_id": "krishna", "crop": "paddy",
    "crop_stage": "grain-filling", "requested_date": "2026-11-24",
    "question": "Should I irrigate if rain is expected?", "language": "en",
    "field_observations": "The soil is drying.",
}


def deterministic_vectors(texts, role):
    # Exercise real Chroma and the SQL boundary without a model download in unit tests.
    return [[1., 0., 0.] if "irrigat" in text.lower() else [0., 1., 0.] for text in texts]


class GroundedAdvisoryTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        database = Path(directory) / "evidence.sqlite3"
        self.enterContext(patch.dict("os.environ", {"AGRIRAG_DB_PATH": str(database)}))
        client = chromadb.EphemeralClient(settings=chromadb.Settings(anonymized_telemetry=False))
        self.vector = client.create_collection(f"evidence-{uuid4()}", embedding_function=None)
        self.addCleanup(client.delete_collection, self.vector.name)
        self.enterContext(patch("evidence_index.collection", return_value=self.vector))
        self.enterContext(patch("evidence_index.embed", side_effect=deterministic_vectors))
        self.client = self.enterContext(TestClient(app))
        seed(None)

    def ask(self, **updates):
        response = self.client.post("/api/advisories", json=REQUEST | updates)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def follow_up(self, session_id, **updates):
        response = self.client.post("/api/advisories", json={"session_id": session_id, **updates})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def add_alternative(self, *, district="krishna", stage="grain-filling", issue="2026-11-21",
                        url="https://example.org/independent.pdf", same_series=False):
        publisher = "Independent extension service"
        title = "Independent paddy field note"
        if same_series:
            with evidence_db() as connection:
                original = connection.execute(
                    "SELECT publisher, title, original_url FROM source_documents WHERE id = 'imd-agromet-ap-93-2026'"
                ).fetchone()
                publisher, title, url = original
        with evidence_db(write=True) as connection:
            connection.execute("""
                INSERT INTO source_documents (id,publisher,title,original_url,language,state_id,issue_date,version,status,source_verified)
                VALUES ('alternative',?,?,?,'en','andhra-pradesh',?,'94-test','approved',1)
            """, (publisher, title, url, issue))
            connection.execute("""
                INSERT INTO evidence_passages
                (id,document_id,section,district_id,statewide,kind,crop,stage_id,topic,content,reviewed,status,decision_code)
                VALUES ('alternative-1','alternative','Water management',?,?,'advisory','paddy',?,'irrigation',
                        'Hold off on irrigation.',1,'approved','avoid_irrigation')
            """, (district, district is None, stage))

    def test_localized_topic_lookup_uses_same_approved_passages(self):
        queries = [
            ("en", "Will I need to irrigate if it rains?"),
            ("te", "వర్షం పడితే వరి పొలానికి నీరు పెట్టాలా?"),
            ("hi", "बारिश हो तो धान की सिंचाई करूँ?"),
        ]
        actions = set()
        for language, question in queries:
            answer = self.ask(language=language, question=question)
            self.assertEqual(answer["status"], "supported")
            self.assertFalse(answer["is_demo"])
            self.assertEqual(answer["language"], language)
            self.assertEqual([row["passage_id"] for row in answer["evidence"]],
                             ["imd-agromet-ap-93-2026-1", "imd-value-added-ap-94-2026-1"])
            self.assertIn("2026-11-24", answer["explanation"])
            self.assertEqual(answer["validity_window"], {"valid_from": "2026-11-24", "valid_until": "2026-11-25"})
            actions.add(answer["suggested_action"])
        self.assertEqual(len(actions), 3)

    def test_follow_ups_ask_one_missing_detail_at_a_time(self):
        first = self.ask(crop_stage="unknown", field_observations=None)
        self.assertEqual(first["status"], "clarification")
        self.assertEqual(first["follow_up_field"], "crop_stage")
        second = self.follow_up(first["session_id"], crop_stage="grain-filling", question="Ignore the original topic.")
        self.assertEqual(second["follow_up_field"], "field_observations")
        final = self.follow_up(first["session_id"], field_observations="Standing water")
        self.assertEqual(final["status"], "supported")
        self.assertIn("hold off", final["suggested_action"])
        self.assertIsNone(final["follow_up_question"])
        self.assertEqual(final["requested_date"], first["requested_date"])
        self.assertEqual(self.ask(crop_stage="tillering")["status"], "insufficient_evidence")

    def test_render_defaults_to_sqlite_and_preserves_evidence_decisions(self):
        with (
            patch.dict("os.environ", {"RENDER": "true", "AGRIRAG_EVIDENCE_MODE": "", "AGRIRAG_LIVE_WEATHER": "0",
                                      "GEMINI_API_KEY": "", "OPENAI_API_KEY": ""}),
            patch("evidence_index.download_model") as download,
            patch("evidence_index.collection") as vector_index,
            patch("main.collection") as readiness_index,
            patch("builtins.print"),
        ):
            evidence_index.prepare_index(install_model=True)
            self.assertEqual(self.client.get("/readyz").json(), {"status": "ready"})
            answer = self.ask()
            self.assertEqual(answer["status"], "supported")
            self.assertEqual([row["passage_id"] for row in answer["evidence"]],
                             ["imd-agromet-ap-93-2026-1", "imd-value-added-ap-94-2026-1"])
            self.assertEqual(self.ask(district_id="eluru")["status"], "insufficient_evidence")
            self.assertEqual(self.ask(requested_date="2026-11-29")["status"], "insufficient_evidence")
            self.assertEqual(self.ask(crop_stage="unknown")["status"], "clarification")
            self.add_alternative()
            self.assertEqual(self.ask()["status"], "conflicting_evidence")
            with evidence_db(write=True) as connection:
                connection.execute("UPDATE source_documents SET status = 'archived' WHERE id = 'alternative'")
            self.assertEqual(self.ask()["status"], "supported")
            download.assert_not_called()
            vector_index.assert_not_called()
            readiness_index.assert_not_called()

    def test_explicit_retrieval_mode_overrides_host_default(self):
        with patch.dict("os.environ", {"RENDER": "true", "AGRIRAG_EVIDENCE_MODE": "chroma"}):
            self.assertEqual(evidence_index.evidence_mode(), "chroma")
        with patch.dict("os.environ", {"RENDER": "false", "AGRIRAG_EVIDENCE_MODE": ""}):
            self.assertEqual(evidence_index.evidence_mode(), "chroma")

    def test_wrong_district_and_expired_or_future_weather(self):
        unsupported = self.ask(district_id="eluru")
        self.assertEqual(unsupported["status"], "insufficient_evidence")
        self.assertEqual(unsupported["evidence"], [])
        for day in ("2026-11-22", "2026-11-29"):
            expired = self.ask(requested_date=day, question="Will it rain?")
            self.assertEqual(expired["status"], "insufficient_evidence")
            self.assertEqual(expired["evidence"], [])
        with evidence_db(write=True) as connection:
            connection.execute("UPDATE evidence_passages SET status = 'draft' WHERE id = 'imd-value-added-ap-94-2026-2'")
        west = self.ask(district_id="west-godavari")
        self.assertEqual(west["status"], "insufficient_evidence")
        self.assertEqual(west["evidence"], [])

    def test_archived_and_unpublished_vectors_never_return_even_on_retry(self):
        headers = {"Idempotency-Key": str(uuid4())}
        first = self.client.post("/api/advisories", json=REQUEST, headers=headers).json()
        self.assertEqual(first["status"], "supported")
        with evidence_db(write=True) as connection:
            connection.execute("UPDATE source_documents SET status = 'archived' WHERE id = 'imd-agromet-ap-93-2026'")
            connection.execute("UPDATE evidence_passages SET status = 'draft' WHERE id = 'imd-value-added-ap-94-2026-1'")
        stale_ids = self.vector.get()["ids"]
        self.assertIn("imd-agromet-ap-93-2026-1", stale_ids)
        self.assertIn("imd-value-added-ap-94-2026-1", stale_ids)
        replay = self.client.post("/api/advisories", json=REQUEST, headers=headers).json()
        self.assertEqual(replay["status"], "insufficient_evidence")
        self.assertEqual(replay["advisory_id"], first["advisory_id"])
        self.assertEqual(replay["evidence"], [])

    def test_equal_scope_independent_disagreement_is_conflict(self):
        self.add_alternative()
        answer = self.ask()
        self.assertEqual(answer["status"], "conflicting_evidence")
        self.assertEqual({row["passage_id"] for row in answer["evidence"]},
                         {"imd-agromet-ap-93-2026-1", "alternative-1"})

    def test_different_local_forecasts_for_same_day_conflict(self):
        self.add_alternative()
        with evidence_db(write=True) as connection:
            connection.execute("""
                UPDATE evidence_passages SET kind = 'weather', crop = NULL, stage_id = NULL,
                    topic = 'district-rainfall-forecast', decision_code = NULL, valid_from = '2026-11-24',
                    valid_until = '2026-11-24', daily_rainfall = '{"2026-11-24": 5}'
                WHERE id = 'alternative-1'
            """)
        answer = self.ask(question="Will it rain?")
        self.assertEqual(answer["status"], "conflicting_evidence")
        self.assertEqual({row["passage_id"] for row in answer["evidence"]},
                         {"imd-value-added-ap-94-2026-1", "alternative-1"})

    def test_local_scope_and_newer_edition_resolve_conflicts(self):
        self.add_alternative(district=None)
        self.assertEqual(self.ask()["status"], "supported")
        with evidence_db(write=True) as connection:
            connection.execute("DELETE FROM evidence_passages WHERE document_id = 'alternative'")
            connection.execute("DELETE FROM source_documents WHERE id = 'alternative'")
        self.add_alternative(same_series=True)
        answer = self.ask()
        self.assertEqual(answer["status"], "supported")
        self.assertEqual(answer["evidence"][0]["passage_id"], "alternative-1")

    def test_explicit_statewide_practice_does_not_create_a_weather_claim(self):
        self.add_alternative(district=None)
        with patch("advisory_rules.datetime", wraps=datetime) as clock:
            clock.now.return_value = datetime(2026, 11, 27, 12, tzinfo=timezone.utc)
            answer = self.ask(question="How should I irrigate paddy?", requested_date=None)
        self.assertEqual(answer["status"], "supported")
        self.assertEqual(answer["evidence"][0]["passage_id"], "alternative-1")
        self.assertIsNone(answer["evidence"][0]["district_id"])
        self.assertNotIn("forecast", answer["explanation"])

    def test_relative_dates_are_anchored_to_india_midnight(self):
        before = datetime(2026, 11, 23, 18, 29, tzinfo=timezone.utc)
        after = datetime(2026, 11, 23, 18, 30, tzinfo=timezone.utc)
        for question in ("rain tomorrow", "రేపు వర్షం", "कल बारिश"):
            self.assertEqual(requested_day(question, now=before), (date(2026, 11, 24), True))
            self.assertEqual(requested_day(question, now=after), (date(2026, 11, 25), True))
        with patch("advisory_rules.datetime", wraps=datetime) as clock:
            clock.now.return_value = before
            initial = self.ask(crop_stage="unknown", question="Should I irrigate tomorrow?", requested_date=None)
            clock.now.return_value = after
            updated = self.follow_up(initial["session_id"], crop_stage="grain-filling")
        self.assertEqual(initial["requested_date"], "2026-11-24")
        self.assertEqual(updated["requested_date"], "2026-11-24")
        self.assertEqual(updated["status"], "supported")

    @unittest.skipUnless(
        (Path(os.environ.get("AGRIRAG_E5_DIR", ROOT / "data" / "e5-small")) / "model.onnx").is_file(),
        "Install the E5 model to run the multilingual semantic-ranking test.",
    )
    def test_real_e5_ranks_irrigation_over_unrelated_passages_in_three_languages(self):
        with patch("evidence_index.embed", new=REAL_EMBEDDING):
            with evidence_db() as connection:
                passages = connection.execute(PUBLISHED_PASSAGES + """
                    AND p.id IN ('imd-agromet-ap-93-2026-1','imd-agromet-ap-93-2026-2','imd-value-added-ap-94-2026-1')
                """).fetchall()
            for question in ("How much irrigation should I use during grain filling?",
                             "గింజ నిండే దశలో వరికి ఎంత నీరు పెట్టాలి?",
                             "दाना भरते समय धान में कितनी सिंचाई करूँ?"):
                with self.subTest(question=question):
                    self.assertEqual(evidence_index.rank(question, passages)[0]["id"], "imd-agromet-ap-93-2026-1")


REAL_EMBEDDING = evidence_index.embed
