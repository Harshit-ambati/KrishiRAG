from collections import defaultdict

from advisory_rules import ACTIONS, WEATHER_TOPIC, preferred, rainfall_on
from evidence_store import PUBLISHED_PASSAGES
from locations import CONFIG, DISTRICTS


def published_on(connection, condition, day=None):
    sql = PUBLISHED_PASSAGES + condition
    if day is None:
        return connection.execute(sql)
    sql += """
        AND (d.issue_date IS NULL OR d.issue_date <= :day)
        AND (COALESCE(p.valid_from, d.valid_from) IS NULL OR COALESCE(p.valid_from, d.valid_from) <= :day)
        AND (COALESCE(p.valid_until, d.valid_until) IS NULL OR COALESCE(p.valid_until, d.valid_until) >= :day)
    """
    return connection.execute(sql, {"day": day})


def reviewed_crops(connection, day=None):
    rows = published_on(connection, """
        AND p.kind IN ('advisory', 'background') AND p.crop IS NOT NULL
        AND (p.stage_id IS NOT NULL OR COALESCE(p.crop_stage, '') = '')
    """, day)
    scopes = defaultdict(set)
    for row in rows:
        state, district, crop = row["state_id"], row["district_id"], row["crop"]
        if crop not in CONFIG["crops"] or row["decision_code"] not in ACTIONS.get(row["topic"], {}):
            continue
        if row["stage_id"] and row["stage_id"] not in CONFIG["crop_stages"][crop]:
            continue
        if district in DISTRICTS.get(state, ()) or (district is None and row["statewide"]):
            scopes[state, district].add(crop)
    return scopes


def national_coverage_inventory(connection, day):
    day = day.isoformat()
    crops = reviewed_crops(connection, day)
    forecasts = defaultdict(set)
    rows = published_on(connection, """
        AND p.kind = 'weather' AND p.crop IS NULL AND p.stage_id IS NULL
        AND COALESCE(p.crop_stage, '') = '' AND d.issue_date IS NOT NULL
        AND COALESCE(p.valid_from, d.valid_from) IS NOT NULL
        AND COALESCE(p.valid_until, d.valid_until) IS NOT NULL
    """, day)
    rows_by_district = defaultdict(list)
    for row in rows:
        if row["topic"] == WEATHER_TOPIC:
            rows_by_district[row["state_id"], row["district_id"]].append(row)
    for location, local_rows in rows_by_district.items():
        forecasts[location] = {rainfall_on(row, day) for row in preferred(local_rows)}

    states = []
    for state in CONFIG["coverage"]:
        state_id = state["id"]
        statewide = crops[state_id, None]
        districts = []
        for district in state["districts"]:
            if not district["enabled"]:
                continue
            location = state_id, district["id"]
            local = crops[location]
            amounts = forecasts[location]
            weather = "conflicting" if len(amounts - {None}) > 1 else (
                "reviewed" if len(amounts) == 1 and None not in amounts else "missing"
            )
            districts.append({
                "district_id": district["id"], "district": district["name"]["en"],
                "local_crop_ids": sorted(local), "usable_crop_ids": sorted(statewide | local),
                "reviewed_rainfall": weather, "has_weather_reference_point": district["live_weather"],
            })
        states.append({"state_id": state_id, "state": state["name"]["en"],
                       "statewide_crop_ids": sorted(statewide), "districts": districts})

    districts = [district for state in states for district in state["districts"]]
    return {
        "states": states,
        "summary": {
            "state_count": len(states), "district_count": len(districts),
            "districts_with_crop_guidance": sum(bool(district["usable_crop_ids"]) for district in districts),
            "districts_with_local_crop_guidance": sum(bool(district["local_crop_ids"]) for district in districts),
            "districts_with_reviewed_rainfall": sum(district["reviewed_rainfall"] == "reviewed" for district in districts),
            "districts_with_weather_reference_point": sum(district["has_weather_reference_point"] for district in districts),
        },
    }
