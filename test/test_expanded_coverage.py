import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from advisory_generation import ChatProvider
from advisory_rules import INDIA
from evidence_seed import seed
from live_weather import DAILY_UNITS, Forecast, fetch_forecast
from main import app


PUNE = {"state_id": "maharashtra", "district_id": "lgd-490"}
COIMBATORE = {"state_id": "tamil-nadu", "district_id": "lgd-569"}
DAY = date(2026, 11, 23)
NOW = datetime(2026, 11, 23, 9, tzinfo=INDIA)


class ExpandedCoverageTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.dict("os.environ", {
            "AGRIRAG_DB_PATH": str(Path(directory) / "test.sqlite3"),
            "AGRIRAG_LIVE_WEATHER": "0",
            "OPENAI_API_KEY": "",
        }))
        self.enterContext(patch("advisory_rules.rank", side_effect=lambda _, rows: rows))
        self.client = self.enterContext(TestClient(app))
        seed(None)

    def ask(self, location, question, **fields):
        response = self.client.post("/api/advisories", json=location | {
            "question": question, "language": "en", "requested_date": DAY.isoformat(), **fields,
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_national_directory_and_crop_stage_validation(self):
        config = self.client.get("/api/farm-config").json()
        self.assertEqual(len(config["coverage"]), 36)
        self.assertGreaterEqual(sum(len(state["districts"]) for state in config["coverage"]), 780)
        self.assertEqual(set(config["crops"]), {
            "paddy", "tomato", "chilli", "onion", "okra", "brinjal", "bottle-gourd",
            "cabbage", "cauliflower", "peas", "potato",
        })
        states = {state["id"]: set(state["vegetable_ids"]) for state in config["coverage"]}
        self.assertEqual(states["chandigarh"], {"onion", "potato"})
        self.assertEqual(states["andhra-pradesh"], set(config["crops"]) - {"paddy"})
        self.assertIn("chilli", states["uttarakhand"])
        self.assertTrue(all(vegetables and vegetables <= config["crops"].keys() for vegetables in states.values()))
        self.assertIn("panicle-initiation", config["crop_stages"]["paddy"])
        self.assertIn("curd-formation", config["crop_stages"]["cauliflower"])
        self.assertIn("tuber-bulking", config["crop_stages"]["potato"])
        for fields in (PUNE | {"state_id": "andhra-pradesh"},
                       COIMBATORE | {"crop": "tomato", "crop_stage": "tillering"},
                       COIMBATORE | {"crop": "okra", "crop_stage": "tuber-initiation"}):
            response = self.client.post("/api/advisories", json=fields | {"question": "Rain?", "language": "en"})
            self.assertEqual(response.status_code, 422)

    def test_new_stage_and_new_crop_are_valid_without_broadening_advice(self):
        for crop, stage in (("okra", "establishment"), ("potato", "tuber-initiation")):
            result = self.ask(COIMBATORE, "How should I irrigate?", crop=crop, crop_stage=stage, requested_date=None)
            self.assertEqual(result["crop_stage"], stage)
            self.assertEqual(result["status"], "insufficient_evidence")

    def test_vegetable_guidance_respects_crop_and_state(self):
        question = "How do I irrigate the crop?"
        for location, crop, code in (
            (COIMBATORE, "tomato", "tomato_even_water"),
            (COIMBATORE, "onion", "onion_good_drainage"),
            ({"state_id": "uttarakhand", "district_id": "lgd-49"}, "chilli", "chilli_avoid_stagnation"),
        ):
            with self.subTest(crop=crop):
                backed = self.ask(location, question, crop=crop, requested_date=None)
                self.assertEqual(backed["status"], "supported")
                self.assertEqual(backed["decision_code"], code)
                self.assertEqual(backed["evidence"][0]["crop"], crop)
                self.assertEqual(self.ask(PUNE, question, crop=crop, requested_date=None)["status"], "insufficient_evidence")

    def test_pre_submission_coverage_respects_scope_stage_date_and_approval(self):
        from evidence_store import evidence_db

        def lookup(**changes):
            query = {"state_id": "andhra-pradesh", "district_id": "krishna", "crop": "paddy",
                     "on_date": "2026-11-24", **changes}
            response = self.client.get("/api/coverage", params=query)
            self.assertEqual(response.status_code, 200, response.text)
            return response.json()

        with patch("live_weather.httpx.get") as network:
            today = lookup()
            self.assertTrue(today["has_reviewed_forecast"])
            self.assertIn({"topic": "irrigation", "status": "stage_needed"}, today["crop_topics"])
            staged = lookup(crop_stage="grain-filling")
            self.assertIn({"topic": "irrigation", "status": "reviewed"}, staged["crop_topics"])
            self.assertFalse(lookup(on_date="2026-12-01")["has_reviewed_forecast"])
            self.assertEqual(lookup(district_id="eluru")["crop_topics"], [])
            self.assertEqual(lookup(**COIMBATORE, crop="tomato")["crop_topics"],
                             [{"topic": "irrigation", "status": "reviewed"}])
            with evidence_db(write=True) as connection:
                connection.execute("UPDATE source_documents SET status='archived' WHERE id='imd-agromet-ap-93-2026'")
            self.assertNotIn({"topic": "irrigation", "status": "reviewed"}, lookup(crop_stage="grain-filling")["crop_topics"])
            network.assert_not_called()

    def test_okra_stage_and_brinjal_drainage_have_scoped_coverage(self):
        for language, query in (
            ("en", "How should I irrigate my okra?"),
            ("te", "నా బెండకు ఎలా నీరు పెట్టాలి?"),
            ("hi", "भिंडी की सिंचाई कैसे करूँ?"),
        ):
            with self.subTest(language=language):
                response = self.ask(COIMBATORE, query, crop="okra", language=language, requested_date=None)
                self.assertEqual(response["follow_up_field"], "crop_stage")
                self.assertEqual(response["status"], "clarification")
                answer = self.client.post("/api/advisories", json={
                    "session_id": response["session_id"], "crop_stage": "flowering",
                }).json()
                self.assertEqual(answer["decision_code"], "okra_moisture_at_fruit_set")
                self.assertEqual(answer["evidence"][0]["passage_id"], "tnau-organic-okra-water-1")
        okra = self.ask(PUNE, "How should I irrigate my okra?", crop="okra", crop_stage="flowering", requested_date=None)
        self.assertEqual(okra["status"], "insufficient_evidence")
        early = self.ask(COIMBATORE, "How should I irrigate my okra?", crop="okra", crop_stage="seedling", requested_date=None)
        self.assertEqual(early["status"], "insufficient_evidence")
        brinjal = self.ask(COIMBATORE, "How should I manage brinjal drainage?", crop="brinjal", requested_date=None)
        self.assertEqual(brinjal["decision_code"], "brinjal_rainy_season_drainage")
        self.assertEqual(brinjal["evidence"][0]["passage_id"], "tnau-brinjal-rainy-season-drainage-1")

    def test_direct_definition_in_all_three_languages_without_crop_details(self):
        for language, question in (("en", "What is drip irrigation?"), ("hi", "ड्रिप सिंचाई क्या है?"),
                                   ("te", "బిందు సేద్యం అంటే ఏమిటి?")):
            answer = self.ask(PUNE, question, language=language)
            self.assertEqual(answer["answer_type"], "information")
            self.assertEqual(answer["decision_code"], "define_drip_irrigation")
            self.assertEqual(answer["evidence"][0]["source_id"], "pib-water-efficiency-2026")
            self.assertTrue(answer["answer"])
        sprinkler = self.ask(PUNE, "What is sprinkler irrigation?")
        self.assertEqual(sprinkler["decision_code"], "define_sprinkler_irrigation")
        self.assertEqual(self.ask(PUNE, "When is the next train?")["status"], "insufficient_evidence")

    def test_live_forecast_citation_and_translation_use_same_snapshot(self):
        forecast = Forecast(day=DAY, latitude=18.52, longitude=73.85, retrieved_at=NOW,
                            rainfall_mm=3.25, low_c=18, high_c=29, wind_kmh=12)
        with patch("advisory_api.fetch_forecast", return_value=forecast) as fetch:
            request = PUNE | {"question": "What's the weather?", "language": "en", "requested_date": DAY.isoformat()}
            headers = {"Idempotency-Key": str(uuid4())}
            answer = self.client.post("/api/advisories", json=request, headers=headers).json()
            self.assertEqual(answer["status"], "supported")
            self.assertEqual(answer["answer_type"], "information")
            self.assertIn("3.25 mm", answer["answer"])
            self.assertEqual(answer["evidence"][0]["publisher"], "Open-Meteo")
            self.assertEqual(answer["evidence"][0]["district_id"], PUNE["district_id"])
            repeated = self.client.post("/api/advisories", json=request, headers=headers).json()
            self.assertEqual(repeated, answer)
            translated = self.client.post("/api/advisories", json={
                "session_id": answer["session_id"], "translate_advisory_id": answer["advisory_id"], "language": "te",
            }).json()
            self.assertNotEqual(translated["answer"], answer["answer"])
            self.assertEqual(translated["evidence"], answer["evidence"])
            fetch.assert_called_once()


class ProviderIntegrationTests(unittest.TestCase):
    def test_weather_provider_date_units_and_expiry(self):
        payload = {"timezone": "Asia/Kolkata", "daily_units": DAILY_UNITS.copy(), "daily": {
            "time": [DAY.isoformat()], "rain_sum": [2.0], "showers_sum": [1.25],
            "temperature_2m_min": [18], "temperature_2m_max": [29], "wind_speed_10m_max": [12],
        }}
        with patch.dict("os.environ", {"AGRIRAG_LIVE_WEATHER": "1", "OPEN_METEO_API_KEY": ""}):
            with patch("live_weather.httpx.get") as get:
                get.return_value = httpx.Response(200, json=payload, request=httpx.Request("GET", "https://example.com"))
                forecast = fetch_forecast(*PUNE.values(), DAY, NOW)
                self.assertEqual(forecast.rainfall_mm, 3.25)
                self.assertEqual(get.call_args.kwargs["params"]["start_date"], DAY.isoformat())
                get.reset_mock()
                self.assertIsNone(fetch_forecast(*PUNE.values(), date(2026, 11, 22), NOW))
                get.assert_not_called()
                payload["daily_units"]["rain_sum"] = "inch"
                get.return_value = httpx.Response(200, json=payload, request=httpx.Request("GET", "https://example.com"))
                self.assertIsNone(fetch_forecast(*PUNE.values(), DAY, NOW))

    def test_openai_endpoint_and_auth_are_server_side(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key", "AGRIRAG_OPENAI_MODEL": "",
                                       "AGRIRAG_LLM_URL": "http://localhost:8879/v1"}):
            provider = ChatProvider.configured()
            with patch("advisory_generation.httpx.post") as post:
                post.return_value = httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]},
                                                   request=httpx.Request("POST", "https://example.com"))
                provider.complete("Use verified wording", {}, {"type": "object"})
                self.assertEqual(post.call_args.args[0], "https://api.openai.com/v1/chat/completions")
                self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer test-key")
                payload = post.call_args.kwargs["json"]
                self.assertEqual(payload["model"], "gpt-4.1-mini")
                self.assertTrue(payload["response_format"]["json_schema"]["strict"])
                self.assertFalse(payload["store"])
