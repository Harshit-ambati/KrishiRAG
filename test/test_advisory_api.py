import json
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from main import app


QUESTION = {
    "state_id": "andhra-pradesh",
    "district_id": "krishna",
    "crop": "paddy",
    "crop_stage": "reproductive",
    "question": "Will I need to irrigate after rain?",
    "language": "en",
}


class AdvisoryApiTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.database = Path(directory) / "sessions.sqlite3"
        self.enterContext(patch.dict("os.environ", {"AGRIRAG_DB_PATH": str(self.database)}))
        self.client = self.enterContext(TestClient(app))

    def create(self, **changes):
        response = self.client.post("/api/advisories", json=QUESTION | changes)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def follow_up(self, session_id, **changes):
        response = self.client.post("/api/advisories", json={"session_id": session_id} | changes)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def read_session(self, session_id):
        with closing(sqlite3.connect(self.database)) as connection:
            row = connection.execute(
                "SELECT context FROM advisory_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        return json.loads(row[0])

    def test_validates_new_requests(self):
        for changes in (
            {"state_id": "telangana"}, {"district_id": "eluru"}, {"language": "fr"},
            {"crop_stage": "unknown-stage"}, {"crop": "maize"}, {"question": "   "},
            {"question": None}, {"district_id": None},
        ):
            with self.subTest(changes=changes):
                response = self.client.post("/api/advisories", json=QUESTION | changes)
                self.assertEqual(response.status_code, 422)

    def test_demo_statuses_and_optional_fields(self):
        for status in ("supported", "conditional", "clarification", "coverageGap", "conflict"):
            with self.subTest(status=status):
                result = self.create(demo_scenario=status, language="te")
                self.assertEqual(result["status"], status)
                self.assertIn("follow_up_question", result)
                self.assertTrue(result["suggested_action"])
                self.assertTrue(result["explanation"])
                self.assertTrue(result["is_demo"])
                self.assertTrue(all(item["is_demo"] for item in result["evidence"]))
                self.assertEqual(result["validity_window"] is not None, status == "supported")

    def test_clarification_preserves_original_question_and_context(self):
        initial = self.create(crop_stage="unknown")
        self.assertEqual(initial["status"], "clarification")
        self.assertEqual(initial["follow_up_field"], "crop_stage")

        updated = self.follow_up(
            initial["session_id"], crop_stage="tillering", question="When should I spray?",
            field_observations="Water is standing.", language="hi",
        )
        self.assertEqual(updated["status"], "supported")
        self.assertEqual(updated["language"], "hi")
        self.assertIsNone(updated["follow_up_question"])
        self.assertEqual(updated["session_id"], initial["session_id"])
        self.assertNotEqual(updated["advisory_id"], initial["advisory_id"])

        repeated = self.follow_up(updated["session_id"], crop_stage="unknown", field_observations=" ")
        self.assertEqual(repeated["crop_stage"], "tillering")
        stored = self.read_session(initial["session_id"])
        self.assertEqual(stored["question"], QUESTION["question"])
        self.assertEqual(stored["district_id"], QUESTION["district_id"])
        self.assertEqual(stored["field_observations"], "Water is standing.")

    def test_observation_follow_up_and_session_conflicts(self):
        initial = self.create(question="When should I spray?")
        self.assertEqual(initial["follow_up_field"], "field_observations")
        updated = self.follow_up(initial["session_id"], field_observations="It is still raining.")
        self.assertEqual(updated["status"], "conditional")
        self.assertIsNone(updated["follow_up_question"])

        conflict = self.client.post("/api/advisories", json={
            "session_id": initial["session_id"], "district_id": "west-godavari",
        })
        self.assertEqual(conflict.status_code, 409)
        missing = self.client.post("/api/advisories", json={"session_id": str(uuid4())})
        self.assertEqual(missing.status_code, 404)

    def test_retry_replays_same_response_even_under_concurrency(self):
        headers = {"Idempotency-Key": str(uuid4())}

        def submit():
            with TestClient(app) as client:
                return client.post("/api/advisories", json=QUESTION, headers=headers)

        with ThreadPoolExecutor(max_workers=2) as pool:
            one, two = list(pool.map(lambda _: submit(), range(2)))
        self.assertEqual(one.status_code, 200, one.text)
        self.assertEqual(two.status_code, 200, two.text)
        self.assertEqual(one.json(), two.json())

        with closing(sqlite3.connect(self.database)) as connection:
            count = connection.execute("SELECT count(*) FROM advisory_sessions").fetchone()[0]
        self.assertEqual(count, 1)
        invalid = self.client.post("/api/advisories", json=QUESTION | {"language": "te"}, headers=headers)
        self.assertEqual(invalid.status_code, 409)
