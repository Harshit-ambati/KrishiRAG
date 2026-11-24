import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from advisory_generation import ChatProvider
from advisory_rules import INDIA
from evidence_seed import seed
from evidence_store import evidence_db
from general_farming import DECISION, approved_general_passages, retrieve
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

    def test_named_crop_filters_other_crops_in_all_three_languages(self):
        with evidence_db(write=True) as connection:
            connection.execute("UPDATE evidence_passages SET crop=NULL WHERE document_id='umd-tomato-symptoms'")
        seed(None)
        with evidence_db() as connection:
            rows = approved_general_passages(connection, datetime.now(INDIA).date().isoformat())
        self.assertTrue(any(row["crop"] == "tomato" for row in rows))
        for question in ("Why are the veins of my bhindi yellow?",
                         "मेरी भिंडी की नसें पीली क्यों हैं?",
                         "నా బెండ ఆకుల ఈనెలు ఎందుకు పసుపు రంగులోకి మారుతున్నాయి?"):
            with self.subTest(question=question):
                candidates = retrieve(question, rows)
                self.assertEqual({row["crop"] for row in candidates}, {"okra", None})

    def test_tomato_yield_uses_cultivation_passages_instead_of_symptom_guides(self):
        queries = ("how can i increase the production of my tomato crop",
                   "मैं अपनी टमाटर की फसल की पैदावार कैसे बढ़ा सकता हूँ?",
                   "నా టమాటా పంట దిగుబడి ఎలా పెంచుకోవాలి?")
        with evidence_db() as connection:
            rows = approved_general_passages(connection, datetime.now(INDIA).date().isoformat())
        self.assertTrue(any(row["topic"] == "tomato-blossom-end-rot" for row in rows))
        for query in queries:
            with self.subTest(query=query):
                passages = retrieve(query, rows)
                self.assertEqual({row["crop"] for row in passages}, {"tomato"})
                self.assertEqual({row["topic"] for row in passages}, {"crop-production"})
                self.assertIn("Training of Hybrids", {row["section"] for row in passages})
        self.assertEqual(retrieve("How do I improve my onion yield?", rows), [])
        self.assertTrue(retrieve("How does yellow vein mosaic affect okra yield?", rows))

        provider = ChatProvider("https://example.com", "test-model")

        def complete(instruction, payload, schema, max_tokens):
            if "pairs" in payload:
                return '{"supported":true}'
            self.assertEqual({passage["topic"] for passage in payload["passages"]}, {"crop-production"})
            weed = next(p for p in payload["passages"] if p["id"] == "tnau-tomato-production-organic-1")
            return json.dumps({"claims": [{"text": "Control weeds early with shallow hoeing to avoid injuring roots.",
                                           "passage_id": weed["id"], "quote": weed["text"]}]})

        with patch("advisory_api.ChatProvider.configured", return_value=provider), patch.object(ChatProvider, "complete", side_effect=complete):
            result = self.client.post("/api/advisories", json={
                "question_type": "general", "question": queries[0], "language": "en",
            }).json()
            self.assertEqual(result["status"], "supported")
            self.assertEqual([evidence["topic"] for evidence in result["evidence"]], ["crop-production"])

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
