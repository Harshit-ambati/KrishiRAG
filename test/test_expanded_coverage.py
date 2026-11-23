import tempfile
import unittest
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from advisory_generation import ChatProvider, ModelAdvisory
from advisory_rules import INDIA
from evidence_seed import seed
from live_weather import DAILY_UNITS, Forecast, fetch_forecast, fetch_forecast_days
from main import app


PUNE = {"state_id": "maharashtra", "district_id": "lgd-490"}
COIMBATORE = {"state_id": "tamil-nadu", "district_id": "lgd-569"}
KRISHNA = {"state_id": "andhra-pradesh", "district_id": "krishna"}
DAY = date(2026, 11, 23)
NOW = datetime(2026, 11, 23, 9, tzinfo=INDIA)


class ExpandedCoverageTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.dict("os.environ", {
            "AGRIRAG_DB_PATH": str(Path(directory) / "test.sqlite3"),
            "AGRIRAG_LIVE_WEATHER": "0",
            "GEMINI_API_KEY": "",
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

    def test_crop_menu_only_lists_approved_state_and_district_guidance(self):
        from evidence_store import evidence_db

        def coverage():
            response = self.client.get("/api/farm-config")
            self.assertEqual(response.headers["cache-control"], "no-store")
            return {state["id"]: state for state in response.raise_for_status().json()["coverage"]}

        states = coverage()
        self.assertEqual(states["andhra-pradesh"]["crop_ids"], ["paddy"])
        self.assertEqual(states["tamil-nadu"]["crop_ids"], ["brinjal", "okra", "onion", "tomato"])
        self.assertEqual(states["uttarakhand"]["crop_ids"], ["chilli"])
        self.assertEqual(states["delhi"]["crop_ids"], [])
        self.assertEqual(states["maharashtra"]["crop_ids"], [])
        districts = {item["id"]: item["crop_ids"] for item in states["andhra-pradesh"]["districts"]}
        self.assertEqual(districts["krishna"], ["paddy"])
        self.assertEqual(districts["west-godavari"], ["paddy"])
        self.assertEqual(districts["eluru"], [])
        coimbatore = next(item for item in states["tamil-nadu"]["districts"] if item["id"] == COIMBATORE["district_id"])
        self.assertEqual(coimbatore["crop_ids"], states["tamil-nadu"]["crop_ids"])
        with evidence_db(write=True) as connection:
            connection.execute("UPDATE source_documents SET status='archived' WHERE id='tnau-organic-tomato-water'")
            connection.execute("UPDATE evidence_passages SET status='draft' WHERE document_id='tnau-chilli-water'")
        states = coverage()
        self.assertNotIn("tomato", states["tamil-nadu"]["crop_ids"])
        self.assertEqual(states["uttarakhand"]["crop_ids"], [])

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

    def test_district_outlook_uses_reviewed_rainfall_and_never_fills_a_missing_day(self):
        day = date(2026, 11, 24)
        point = Forecast(day=day, latitude=16, longitude=81, retrieved_at=NOW,
                         rainfall_mm=55, low_c=17, high_c=30, wind_kmh=10)
        with patch("advisory_api.fetch_forecast_days", return_value={day: point}) as fetch:
            response = self.client.get("/api/forecast", params=KRISHNA | {"start_date": day.isoformat(), "days": 7})
            self.assertEqual(response.status_code, 200, response.text)
            days = response.json()["days"]
            fetch.assert_called_once()
            self.assertEqual(len(days), 7)
            self.assertEqual(days[0]["rain_status"], "reviewed")
            self.assertEqual(days[0]["rainfall_mm"], 1)
            self.assertEqual(days[0]["high_c"], 30)
            self.assertEqual(days[0]["sources"][0]["passage_id"], "imd-value-added-ap-94-2026-1")
            self.assertEqual(days[-1]["rain_status"], "unavailable")
            self.assertIsNone(days[-1]["rainfall_mm"])
        wrong = self.client.get("/api/forecast", params=KRISHNA | {"state_id": "maharashtra"})
        self.assertEqual(wrong.status_code, 422)
        self.assertEqual(self.client.get("/api/forecast", params=KRISHNA | {"days": 8}).status_code, 422)

    def test_harvest_thresholds_and_irrigation_gaps_use_the_reviewed_passage(self):
        harvest = self.ask(KRISHNA, "When should I harvest my paddy?", crop="paddy", crop_stage="mature",
                           requested_date="2026-11-24")
        self.assertIn("80–85%", harvest["suggested_action"])
        self.assertIn("12–14%", harvest["suggested_action"])
        self.assertEqual(harvest["claims"][0]["passage_ids"], ["imd-agromet-ap-93-2026-2"])
        quantity = self.ask(KRISHNA, "How much water should I apply?", crop="paddy", crop_stage="grain-filling",
                            requested_date="2026-11-24", field_observations="The soil is drying")
        self.assertEqual(quantity["status"], "conditional")
        self.assertIn("does not specify how much water", quantity["explanation"])
        gap = self.ask(KRISHNA, "Should I irrigate okra?", crop="okra", crop_stage="flowering",
                       requested_date="2026-11-24")
        self.assertEqual(gap["status"], "insufficient_evidence")
        self.assertIn("A forecast is available", gap["explanation"])
        self.assertEqual(gap["evidence"][0]["passage_id"], "imd-value-added-ap-94-2026-1")
        okra = self.ask(COIMBATORE, "How long should the pods be at harvest?", crop="okra",
                        crop_stage="harvesting", requested_date=None)
        self.assertEqual(okra["status"], "supported")
        self.assertIn("7–10 cm", okra["suggested_action"])
        self.assertIn("variety and market", okra["suggested_action"])
        self.assertEqual(okra["claims"][0]["passage_ids"], ["tnau-organic-okra-harvest-2"])

    def test_multi_day_weather_questions_direct_the_farmer_to_the_outlook(self):
        response = self.client.post("/api/advisories", json=PUNE | {
            "question": "Will it rain over the next 3 days?", "language": "en",
        })
        self.assertEqual(response.status_code, 200)
        answer = response.json()
        self.assertIsNone(answer["requested_date"])
        self.assertIn("District forecast", answer["explanation"])

    def test_moisture_choices_preserve_context_and_allow_an_unsure_answer(self):
        for language, unsure, standing in (
            ("en", "I’m not sure about soil moisture", "Standing water"),
            ("te", "నేల తేమ గురించి నాకు తెలియదు", "పొలంలో నీరు నిలిచి ఉంది"),
            ("hi", "मुझे मिट्टी की नमी पता नहीं", "खेत में पानी भरा है"),
        ):
            with self.subTest(language=language):
                first = self.ask(KRISHNA, "Should I irrigate my paddy?", crop="paddy", crop_stage="grain-filling",
                                 requested_date="2026-11-24", language=language)
                self.assertEqual(first["follow_up_kind"], "soil_moisture")
                uncertain = self.client.post("/api/advisories", json={
                    "session_id": first["session_id"], "field_observations": unsure,
                }).json()
                self.assertEqual(uncertain["status"], "insufficient_evidence")
                self.assertIsNone(uncertain["follow_up_kind"])
                answered = self.client.post("/api/advisories", json={
                    "session_id": first["session_id"], "field_observations": standing,
                }).json()
                self.assertEqual(answered["decision_code"], "avoid_irrigation_while_standing")
                self.assertEqual(answered["requested_date"], first["requested_date"])


class ProviderIntegrationTests(unittest.TestCase):
    def test_multiday_weather_uses_one_call_and_skips_incomplete_days(self):
        days = [DAY + timedelta(days=offset) for offset in range(3)]
        payload = {"timezone": "Asia/Kolkata", "daily_units": DAILY_UNITS, "daily": {
            "time": [day.isoformat() for day in days],
            "rain_sum": [2, None, 3], "showers_sum": [1, 1, 0.25],
            "temperature_2m_min": [18, 19, 17], "temperature_2m_max": [30, 30, 29],
            "wind_speed_10m_max": [15, 14, 13],
        }}
        with patch.dict("os.environ", {"AGRIRAG_LIVE_WEATHER": "1", "OPEN_METEO_API_KEY": ""}):
            with patch("live_weather.httpx.get") as get:
                get.return_value = httpx.Response(200, json=payload, request=httpx.Request("GET", "https://example.com"))
                result = fetch_forecast_days(*PUNE.values(), days[0], days[-1], NOW)
                get.assert_called_once()
                self.assertEqual(get.call_args.kwargs["params"]["end_date"], days[-1].isoformat())
                self.assertEqual(list(result), [days[0], days[2]])
                self.assertEqual(result[days[2]].rainfall_mm, 3.25)

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
        with patch.dict("os.environ", {"GEMINI_API_KEY": "", "OPENAI_API_KEY": "test-key", "AGRIRAG_OPENAI_MODEL": "",
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

    def test_gemini_takes_priority_and_uses_native_structured_output(self):
        with patch.dict("os.environ", {"GEMINI_API_KEY": "gemini-test-key", "AGRIRAG_GEMINI_MODEL": "",
                                       "OPENAI_API_KEY": "openai-test-key"}):
            usage = []
            provider = replace(ChatProvider.configured(), record_usage=usage.append)
            self.assertNotIn("gemini-test-key", repr(provider))
            schema = ModelAdvisory.model_json_schema()
            with patch("advisory_generation.httpx.post") as post:
                post.return_value = httpx.Response(200, json={
                    "candidates": [{"finishReason": "STOP", "content": {"parts": [
                        {"text": "internal", "thought": True}, {"text": "{}"},
                    ]}}],
                    "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 4, "thoughtsTokenCount": 2},
                }, request=httpx.Request("POST", "https://example.com"))
                self.assertEqual(provider.complete("Use verified wording", {}, schema), "{}")
                self.assertEqual(post.call_args.args[0],
                                 "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent")
                self.assertEqual(post.call_args.kwargs["headers"], {"x-goog-api-key": "gemini-test-key"})
                self.assertEqual(post.call_args.kwargs["json"]["generationConfig"]["responseJsonSchema"], schema)
                self.assertEqual(usage, [{"prompt_tokens": 10, "completion_tokens": 6}])
