"""Reproduce the dated pilot against a running FastAPI deployment."""

import argparse
import os

import httpx


BASE = {
    "state_id": "andhra-pradesh", "district_id": "krishna", "crop": "paddy",
    "crop_stage": "grain-filling", "requested_date": "2026-11-24", "language": "en",
    "field_observations": "The soil is drying.",
}


def run(client, smoke):
    def post(**values):
        response = client.post("/api/advisories", json=values)
        response.raise_for_status()
        return response.json()

    def source_ids(answer):
        return [ref["passage_id"] for ref in answer["evidence"]]

    def rate(answer, rating):
        response = client.post(f'/api/advisories/{answer["advisory_id"]}/feedback',
                               json={"session_id": answer["session_id"], "rating": rating})
        response.raise_for_status()

    assert client.get("/healthz").json()["status"] == "ok"
    client.get("/").raise_for_status()
    print("Archived replay · 24 November 2026")
    english = post(**BASE, question="Should I irrigate paddy if rain is expected on this date?")
    assert english["status"] == "supported" and english["forecast_rainfall_mm"] == 1.0
    print(f'1. Supported Krishna advisory · {english["suggested_action"]} · {source_ids(english)}')

    missing = post(**(BASE | {"crop_stage": "unknown"}), question="Should I irrigate my paddy?")
    assert missing["status"] == "clarification" and missing["follow_up_field"] == "crop_stage"
    resolved = post(session_id=missing["session_id"], crop_stage="grain-filling")
    assert resolved["status"] == "supported"
    print(f'2. Follow-up · {missing["follow_up_question"]} → {resolved["status"]}')

    rejected = post(**(BASE | {"requested_date": "2026-11-29"}), question="What is the rain forecast?")
    wrong = post(**(BASE | {"district_id": "eluru"}), question="What is the rain forecast?")
    assert rejected["status"] == wrong["status"] == "insufficient_evidence"
    print("3. Rejected · expired on 29 November and unsupported Eluru district")

    for language, question in (
        ("te", "వర్షం పడితే వరి పొలానికి నీరు పెట్టాలా?"),
        ("hi", "बारिश हो तो धान की सिंचाई करूँ?"),
    ):
        localized = post(**(BASE | {"language": language, "crop_stage": "unknown"}), question=question)
        assert localized["status"] == "clarification" and localized["follow_up_field"] == "crop_stage"
        localized = post(session_id=localized["session_id"], crop_stage="grain-filling", language=language)
        for field in ("decision_code", "forecast_rainfall_mm", "requested_date", "validity_window", "evidence"):
            assert localized[field] == english[field], field
        switched = post(session_id=english["session_id"], translate_advisory_id=english["advisory_id"], language=language)
        assert source_ids(switched) == source_ids(english) and switched["decision_code"] == english["decision_code"]
        if smoke:
            rate(localized, "unclear" if language == "te" else "potentially_incorrect")
        print(f'4. {language} equivalent · {localized["decision_code"]} · {source_ids(localized)}')

    west = post(**(BASE | {"district_id": "west-godavari"}), question="Should I irrigate paddy if rain is expected on this date?")
    assert west["status"] == "supported" and west["forecast_rainfall_mm"] == 1.9
    assert source_ids(west) != source_ids(english)
    print(f'  District comparison · Krishna {english["forecast_rainfall_mm"]:g} mm, West Godavari {west["forecast_rainfall_mm"]:g} mm · {source_ids(west)}')

    if smoke:
        rate(resolved, "useful")
        credentials = os.environ.get("AGRIRAG_ADMIN_USER", "admin"), os.environ["AGRIRAG_ADMIN_PASSWORD"]
        assert client.get("/admin").status_code == 401
        client.get("/admin", auth=credentials).raise_for_status()
        review = client.get("/api/admin/advisory-feedback", auth=credentials)
        review.raise_for_status()
        assert {"en", "te", "hi"} <= {row["response"]["language"] for row in review.json()}
        print("HTTP smoke passed · farmer, follow-up, feedback, and authenticated admin review")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--smoke", action="store_true", help="Submit demo feedback and also check the protected admin page.")
    args = parser.parse_args()
    with httpx.Client(base_url=args.url, timeout=60, trust_env=False) as client:
        run(client, args.smoke)
