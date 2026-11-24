import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from advisory_generation import ChatProvider
from evidence_seed import seed
from evidence_store import evidence_db
from general_farming import DECISION
from main import app


class GeneralFarmingTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.dict("os.environ", {
            "AGRIRAG_DB_PATH": str(Path(directory) / "test.sqlite3"),
            "AGRIRAG_EVIDENCE_MODE": "sqlite",
        }))
        self.client = self.enterContext(TestClient(app))
        seed(None)

    def test_open_question_proposes_and_checks_each_claim(self):
        provider = ChatProvider("https://example.com", "test-model")
        request = {"question_type": "general", "question": "Why are the veins on my bhindi yellow?", "language": "en"}
        key = {"Idempotency-Key": str(uuid4())}

        def complete(instruction, payload, schema, max_tokens):
            if "pairs" in payload:
                self.assertEqual([pair["passage"]["crop"] for pair in payload["pairs"]], ["okra", "okra"])
                return '{"supported":true}'
            first, second = [p for p in payload["passages"] if p["id"].startswith("tnau-okra-disease-general-")]
            translated = payload["language"] == "hi"
            return json.dumps({"claims": [
                {"text": "पीली नसें पीली शिरा मोज़ेक का संकेत हो सकती हैं।" if translated else "Yellow veins can indicate yellow vein mosaic.",
                 "passage_id": first["id"], "quote": first["text"]},
                {"text": "जहाँ संभव हो, खरपतवार और अन्य जंगली पोषक पौधे हटाएँ।" if translated else "Remove weeds and other wild host plants where possible.",
                 "passage_id": second["id"], "quote": second["text"]},
            ]})

        with patch("advisory_api.ChatProvider.configured", return_value=provider), patch.object(ChatProvider, "complete", side_effect=complete) as model:
            result = self.client.post("/api/advisories", json=request, headers=key).json()
            self.assertEqual(result["status"], "supported", (result, model.call_count))
            self.assertEqual(result["decision_code"], DECISION)
            self.assertEqual(len(result["claims"]), 2)
            self.assertEqual(len(result["evidence"]), 2)
            self.assertEqual(self.client.post("/api/advisories", json=request, headers=key).json(), result)
            self.assertEqual(model.call_count, 2)
            translation = self.client.post("/api/advisories", json={
                "session_id": result["session_id"], "translate_advisory_id": result["advisory_id"], "language": "hi",
            }).json()
            self.assertEqual(translation["evidence"], result["evidence"])
            self.assertNotEqual(translation["answer"], result["answer"])
            with evidence_db(write=True) as connection:
                connection.execute("UPDATE source_documents SET status='archived' WHERE id='tnau-okra-disease-general'")
            response = self.client.post("/api/advisories", json={
                "session_id": result["session_id"], "translate_advisory_id": result["advisory_id"], "language": "te",
            })
            self.assertEqual(response.status_code, 409)

    def test_open_question_suppresses_invented_quotes_and_rejected_actions(self):
        provider = ChatProvider("https://example.com", "test-model")
        with patch("advisory_api.ChatProvider.configured", return_value=provider):
            for result in ("fake_quote", "wrong_source", "unsupported", "unrelated", "quota"):
                with self.subTest(result=result):
                    def complete(instruction, payload, schema, max_tokens):
                        if result == "quota":
                            raise httpx.HTTPStatusError("rate limit", request=httpx.Request("POST", provider.base_url),
                                                        response=httpx.Response(429))
                        if "pairs" in payload:
                            self.assertEqual(result, "unsupported")
                            return '{"supported":false}'
                        if result == "unrelated":
                            return '{"claims":[]}'
                        source = next(p for p in payload["passages"] if p["id"].startswith("tnau-onion-thrips-general"))
                        self.assertTrue(all("ap-" not in p["id"] for p in payload["passages"]))
                        return json.dumps({"claims": [{"text": "Spray an insecticide now.",
                            "passage_id": "missing" if result == "wrong_source" else source["id"],
                            "quote": "invented quote" if result == "fake_quote" else source["text"]}]})

                    with patch.object(ChatProvider, "complete", side_effect=complete):
                        response = self.client.post("/api/advisories", json={
                            "question_type": "general", "question": "What causes silvery marks on onion leaves?", "language": "en",
                        })
                    self.assertEqual(response.status_code, 200)
                    answer = response.json()
                    self.assertEqual(answer["status"], "insufficient_evidence")
                    self.assertFalse(answer["evidence"])
                    self.assertFalse(answer["claims"])
                    if result == "quota":
                        self.assertEqual(answer["generation_outcome"], "provider_limit")
