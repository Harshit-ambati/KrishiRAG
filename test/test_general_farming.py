import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from advisory_generation import ChatProvider, GeminiProvider
from advisory_rules import INDIA, question_topic
from evidence_seed import seed
from evidence_store import evidence_db
from general_farming import DECISION, approved_general_passages, retrieve
from main import app
from trusted_web import load_publication, official_url, search_publications, web_row


class GeneralFarmingTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.dict("os.environ", {
            "AGRIRAG_DB_PATH": str(Path(directory) / "test.sqlite3"),
            "AGRIRAG_EVIDENCE_MODE": "sqlite",
        }))
        self.client = self.enterContext(TestClient(app))
        seed(None)

    def test_potato_maturity_answers_with_icar_sources_without_a_model(self):
        questions = {
            "en": "How many days after planting seed potatoes is the crop ready to harvest?",
            "te": "బంగాళాదుంప నాటిన తర్వాత కోతకు ఎన్ని రోజులు పడుతుంది?",
            "hi": "आलू लगाने के बाद कटाई में कितने दिन लगते हैं?",
        }
        with patch("advisory_api.ChatProvider.configured") as provider:
            for language, question in questions.items():
                response = self.client.post("/api/advisories", json={
                    "question_type": "general", "question": question, "language": language,
                })
                self.assertEqual(response.status_code, 200)
                result = response.json()
                self.assertEqual(result["status"], "supported")
                self.assertEqual(result["generation_outcome"], "verified_template")
                self.assertIn("70–100", result["answer"])
                for duration in ("70–90", "75–80", "90–100"):
                    self.assertIn(duration, result["explanation"])
                self.assertEqual(result["evidence"][0]["publisher"], "Indian Council of Agricultural Research")
            provider.assert_not_called()

    def test_potato_duration_intent_leaves_other_potato_questions_open(self):
        self.assertEqual(question_topic("how many days it take to cultivate the potato crop after the sampling"),
                         "potato-harvest-duration")
        for query in ("How many days after planting should I fertilize potatoes?",
                      "How long until I harvest sweet potatoes?"):
            self.assertNotEqual(question_topic(query), "potato-harvest-duration")

    def test_web_fallback_uses_fetched_passages_and_keeps_them_when_translating(self):
        provider = GeminiProvider("https://example.com", "test-model")
        row = web_row("https://icar.gov.in/extension/test", "Indian Council of Agricultural Research",
                      "Crop spacing", "Wider spacing between young example plants increases airflow.", "test-hash")

        def complete(instruction, payload, schema, max_tokens):
            if "pairs" in payload:
                return '{"supported":true}'
            if not any(p["id"] == row["id"] for p in payload["passages"]):
                return '{"claims":[],"clarification":null}'
            return json.dumps({"claims": [{"text": "Improving airflow is possible with wider spacing.",
                                           "passage_id": row["id"], "quote": row["content"]}], "clarification": None})

        with patch("advisory_api.ChatProvider.configured", return_value=provider), \
                patch("advisory_api.search_publications", return_value=([row], None)) as search, \
                patch.object(GeminiProvider, "complete", side_effect=complete):
            answer = self.client.post("/api/advisories", json={
                "question_type": "general", "question": "How can I improve airflow around a young crop?", "language": "en",
            }).json()
            self.assertEqual(answer["status"], "supported")
            self.assertEqual(answer["evidence"][0]["source_id"], "trusted-web")
            translated = self.client.post("/api/advisories", json={
                "session_id": answer["session_id"], "translate_advisory_id": answer["advisory_id"], "language": "te",
            })
            self.assertEqual(translated.status_code, 200, translated.text)
            self.assertEqual(translated.json()["evidence"], answer["evidence"])
            search.assert_called_once()
        with evidence_db() as connection:
            self.assertFalse(connection.execute("SELECT 1 FROM evidence_passages WHERE id=?", (row["id"],)).fetchone())

    def test_general_follow_up_preserves_question_and_accepts_field_observations(self):
        provider = ChatProvider("https://example.com", "test-model")

        def complete(instruction, payload, schema, max_tokens):
            self.assertEqual(payload["question"], "Why are my plant leaves yellow?")
            if payload["observations"]:
                self.assertEqual(payload["observations"], "My okra has yellow veins.")
                return '{"claims":[],"clarification":null}'
            return '{"claims":[],"clarification":"crop"}'

        with patch("advisory_api.ChatProvider.configured", return_value=provider), \
                patch.object(ChatProvider, "complete", side_effect=complete):
            original = self.client.post("/api/advisories", json={
                "question_type": "general", "question": "Why are my plant leaves yellow?", "language": "en",
            }).json()
            self.assertEqual(original["follow_up_question"], "Which crop are you asking about?")
            localized = self.client.post("/api/advisories", json={
                "session_id": original["session_id"], "translate_advisory_id": original["advisory_id"], "language": "hi",
            })
            self.assertEqual(localized.status_code, 200, localized.text)
            self.assertNotEqual(localized.json()["follow_up_question"], original["follow_up_question"])
            reply = self.client.post("/api/advisories", json={
                "session_id": original["session_id"], "field_observations": "My okra has yellow veins.", "language": "en",
            })
            self.assertEqual(reply.status_code, 200)
            self.assertEqual(reply.json()["session_id"], original["session_id"])

    def test_web_rejects_other_hosts_and_checks_publisher_html(self):
        for url in ("http://tnau.ac.in/guide", "https://tnau.ac.in.evil.test/guide", "https://user@tnau.ac.in/guide",
                    "https://tnau.ac.in:1234/guide"):
            self.assertIsNone(official_url(url))
        website = "https://agritech.tnau.ac.in/crop/guide"
        html = "<script>untrusted script</script><p>A soil test is an important part of assessing soil conditions for tomatoes before planting.</p>"

        def handler(request):
            if request.url.path == "/grounding-api-redirect/test":
                return httpx.Response(302, headers={"Location": website})
            self.assertEqual(str(request.url), website)
            return httpx.Response(200, text=html, headers={"Content-Type": "text/html; charset=utf-8"})

        with httpx.Client(transport=httpx.MockTransport(handler)) as client, patch("trusted_web.httpx.stream", client.stream):
            rows = load_publication({"uri": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/test",
                                     "title": "Soil and tomato cultivation"}, "When should I test tomato soil?")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["original_url"], website)
        self.assertNotIn("untrusted script", rows[0]["content"])

    def test_grounded_search_discovers_links_without_using_generated_text(self):
        provider = GeminiProvider("https://example.com", "test-model", "test-key")
        source = {"uri": "https://icar.gov.in/guide"}
        response = httpx.Response(200, request=httpx.Request("POST", provider.base_url), json={"candidates": [{
            "content": {"parts": [{"text": "Unverified text must never become evidence."}]},
            "groundingMetadata": {"groundingChunks": [{"web": source}]},
        }]})
        with patch.dict("os.environ", {"AGRIRAG_WEB_EVIDENCE": "1"}), \
                patch("trusted_web.httpx.post", return_value=response) as post, \
                patch("trusted_web.load_publication", return_value=[]) as load:
            self.assertEqual(search_publications(provider, "How can I improve potato storage?"), ([], None))
            self.assertEqual(post.call_args.kwargs["json"]["tools"], [{"google_search": {}}])
            load.assert_called_once_with(source, "How can I improve potato storage?")

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
