import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest.mock import Mock, patch
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from advisory_generation import ChatProvider, GeminiProvider
from evidence_seed import seed
from evidence_store import evidence_db
from main import app

REQUEST = {
    "state_id": "andhra-pradesh", "district_id": "krishna", "crop": "paddy",
    "crop_stage": "grain-filling", "requested_date": "2026-11-24",
    "question": "Should I irrigate then?", "field_observations": "Standing water.", "language": "en",
}


def valid_proposal(payload):
    claims = [
        {"kind": item["kind"], "text": item["wording"][-1], "passage_ids": item["passage_ids"]}
        for item in payload["verified_claims"]
    ]
    return {"action": claims[0], "explanation": claims[1:]}


class CitedGenerationTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.dict("os.environ", {
            "AGRIRAG_DB_PATH": str(Path(directory) / "test.sqlite3"),
            "AGRIRAG_ADMIN_USER": "reviewer", "AGRIRAG_ADMIN_PASSWORD": "test-password",
        }))
        self.enterContext(patch("advisory_rules.rank", side_effect=lambda _, rows: rows))
        self.provider = Mock(model="test-model")
        self.provider.complete.side_effect = lambda _, payload, schema, **kwargs: json.dumps(valid_proposal(payload))
        self.enterContext(patch("advisory_api.ChatProvider.configured", return_value=self.provider))
        self.client = self.enterContext(TestClient(app))
        seed(None)

    def send(self, **updates):
        result = self.client.post("/api/advisories", json=REQUEST | updates)
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()

    def test_verified_generation_returns_claims_and_snapshots_source_versions(self):
        result = self.send()
        self.assertEqual(result["generation_outcome"], "llm")
        self.assertEqual(result["decision_code"], "avoid_irrigation_while_standing")
        self.assertEqual(result["forecast_rainfall_mm"], 1.0)
        self.assertEqual(result["claims"][0]["passage_ids"], ["imd-agromet-ap-93-2026-1"])
        self.assertEqual(result["claims"][-1]["passage_ids"], ["imd-value-added-ap-94-2026-1"])
        with evidence_db() as connection:
            saved = connection.execute("SELECT response,provider_model FROM advisory_runs WHERE advisory_id = ?", (result["advisory_id"],)).fetchone()
        self.assertEqual(saved["provider_model"], "test-model")
        self.assertEqual([ref["version"] for ref in json.loads(saved["response"])["evidence"]], ["93/2026", "94/2026"])

    def test_overlapping_provider_calls_deliver_one_response_per_retry_key(self):
        entered = Barrier(2, timeout=10)

        def first_succeeds(_, payload, schema, **kwargs):
            if entered.wait():
                return json.dumps(valid_proposal(payload))
            raise httpx.ReadTimeout("provider stopped responding")

        def submit():
            return self.client.post("/api/advisories", json=REQUEST, headers={"Idempotency-Key": uuid.hex})

        uuid = uuid4()
        self.provider.complete.side_effect = first_succeeds
        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = [executor.submit(submit) for _ in range(2)]
            first, second = [response.result(timeout=15).raise_for_status().json() for response in responses]
        self.assertEqual(first, second)
        with evidence_db() as connection:
            count = connection.execute("SELECT count(*) FROM advisory_runs WHERE advisory_id = ?", (first["advisory_id"],)).fetchone()[0]
        self.assertEqual(count, 1)

    def test_clearing_observations_rechecks_the_original_advisory(self):
        original = self.send()
        response = self.client.post("/api/advisories", json={
            "session_id": original["session_id"], "field_observations": None,
        }).raise_for_status().json()
        self.assertEqual(response["status"], "clarification")
        self.assertEqual(response["follow_up_field"], "field_observations")

    def test_made_up_wrong_passage_and_unsupported_action_are_suppressed(self):
        attacks = ("invented-citation", "wrong-allowed-passage", "unsupported-action", "changed-weather")
        for attack in attacks:
            with self.subTest(attack=attack):
                def attacked(_, payload, schema, **kwargs):
                    proposal = valid_proposal(payload)
                    if attack == "invented-citation":
                        proposal["action"]["passage_ids"] = ["invented"]
                    if attack == "wrong-allowed-passage":
                        proposal["action"]["passage_ids"] = ["imd-value-added-ap-94-2026-1"]
                    if attack == "unsupported-action":
                        proposal["action"]["text"] = "Apply 99 litres of water."
                    if attack == "changed-weather":
                        proposal["explanation"][-1]["text"] = "The district bulletin forecast 50 cm of rain."
                    return json.dumps(proposal)

                self.provider.complete.side_effect = attacked
                result = self.send()
                self.assertEqual(result["generation_outcome"], "invalid_output")
                self.assertIn("hold off", result["suggested_action"])
                self.assertNotIn("50 cm", result["explanation"])
                self.assertEqual(result["claims"][0]["passage_ids"], ["imd-agromet-ap-93-2026-1"])

    def test_system_gaps_and_followups_skip_model_and_timeout_uses_template(self):
        self.assertEqual(self.send(crop_stage="unknown")["status"], "clarification")
        self.assertEqual(self.send(district_id="eluru")["status"], "insufficient_evidence")
        self.provider.complete.assert_not_called()
        self.provider.complete.side_effect = httpx.ReadTimeout("provider stopped responding")
        self.assertEqual(self.send()["generation_outcome"], "provider_error")

    def test_provider_usage_limit_returns_cited_fallback_without_upstream_details(self):
        cases = (
            (GeminiProvider, {"status": "RESOURCE_EXHAUSTED"}),
            (ChatProvider, {"code": "insufficient_quota"}),
            (ChatProvider, {"code": "rate_limit_exceeded"}),
        )
        for provider_class, details in cases:
            with self.subTest(provider=provider_class.__name__, details=details):
                provider = provider_class("https://provider.example", "test-model")
                upstream = httpx.Response(429, json={"error": {"message": "private diagnostic", **details}},
                                          request=httpx.Request("POST", "https://provider.example"))
                with (
                    patch("advisory_api.ChatProvider.configured", return_value=provider),
                    patch("advisory_generation.httpx.post", return_value=upstream),
                ):
                    result = self.send()
                self.assertEqual(result["generation_outcome"], "provider_limit")
                self.assertEqual(result["status"], "supported")
                self.assertEqual(result["decision_code"], "avoid_irrigation_while_standing")
                self.assertTrue(result["claims"])
                self.assertEqual([ref["passage_id"] for ref in result["evidence"]],
                                 ["imd-agromet-ap-93-2026-1", "imd-value-added-ap-94-2026-1"])
                self.assertNotIn("private diagnostic", json.dumps(result))

    def test_language_switch_and_feedback_keep_plan_and_citations(self):
        for language, rating in (("en", "useful"), ("te", "unclear"), ("hi", "potentially_incorrect")):
            with self.subTest(language=language):
                first = self.send(crop_stage="unknown", language=language)
                updated = self.client.post("/api/advisories", json={
                    "session_id": first["session_id"], "crop_stage": "grain-filling", "language": language,
                }).json()
                self.assertEqual(updated["status"], "supported")
                other_language = "te" if language == "en" else "en"
                translated = self.client.post("/api/advisories", json={
                    "session_id": updated["session_id"], "translate_advisory_id": updated["advisory_id"],
                    "language": other_language,
                })
                self.assertEqual(translated.status_code, 200, translated.text)
                translated = translated.json()
                for field in ("decision_code", "forecast_rainfall_mm", "requested_date", "validity_window", "evidence"):
                    self.assertEqual(translated[field], updated[field])
                path = f'/api/advisories/{updated["advisory_id"]}/feedback'
                self.assertEqual(self.client.post(path, json={"session_id": str(uuid4()), "rating": rating}).status_code, 404)
                self.assertEqual(self.client.post(path, json={"session_id": updated["session_id"], "rating": rating}).status_code, 200)
        self.assertEqual(self.client.get("/api/admin/advisory-feedback").status_code, 401)
        reports = self.client.get("/api/admin/advisory-feedback", auth=("reviewer", "test-password")).json()
        self.assertEqual({row["response"]["language"] for row in reports}, {"en", "te", "hi"})
        self.assertTrue(all(row["question"] == REQUEST["question"] and row["response"]["evidence"] for row in reports))

    def test_archive_during_generation_cannot_leak_stale_action(self):
        def archive_during_call(_, payload, schema, **kwargs):
            with evidence_db(write=True) as connection:
                connection.execute("UPDATE source_documents SET status='archived' WHERE id='imd-agromet-ap-93-2026'")
            return json.dumps(valid_proposal(payload))
        self.provider.complete.side_effect = archive_during_call
        response = self.send()
        self.assertEqual(response["status"], "insufficient_evidence")
        self.assertEqual(response["claims"], [])

    def test_switch_rejects_changed_grounding_instead_of_substituting(self):
        first = self.send()
        with evidence_db(write=True) as connection:
            connection.execute("UPDATE source_documents SET status='archived' WHERE id='imd-agromet-ap-93-2026'")
        translated = self.client.post("/api/advisories", json={
            "session_id": first["session_id"], "translate_advisory_id": first["advisory_id"], "language": "hi",
        })
        self.assertEqual(translated.status_code, 409)
        self.assertEqual(translated.json()["detail"], "advisory_changed")
