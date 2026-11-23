"""The selectable district directory is independent of published evidence."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PILOT_CONFIG = json.loads((ROOT / "dist" / "coverage.json").read_text(encoding="utf-8"))
DIRECTORY = json.loads((ROOT / "india_districts.json").read_text(encoding="utf-8"))
CULTIVATION = json.loads((ROOT / "state_vegetables.json").read_text(encoding="utf-8"))
STATE_IDS = {1: "jammu-and-kashmir", 35: "andaman-and-nicobar-islands",
             38: "dadra-and-nagar-haveli-and-daman-and-diu"}
STATE_NAMES = {
    1: ("జమ్మూ మరియు కశ్మీర్", "जम्मू और कश्मीर"), 2: ("హిమాచల్ ప్రదేశ్", "हिमाचल प्रदेश"),
    3: ("పంజాబ్", "पंजाब"), 4: ("చండీగఢ్", "चंडीगढ़"), 5: ("ఉత్తరాఖండ్", "उत्तराखंड"),
    6: ("హర్యానా", "हरियाणा"), 7: ("ఢిల్లీ", "दिल्ली"), 8: ("రాజస్థాన్", "राजस्थान"),
    9: ("ఉత్తర ప్రదేశ్", "उत्तर प्रदेश"), 10: ("బీహార్", "बिहार"), 11: ("సిక్కిం", "सिक्किम"),
    12: ("అరుణాచల్ ప్రదేశ్", "अरुणाचल प्रदेश"), 13: ("నాగాలాండ్", "नागालैंड"),
    14: ("మణిపూర్", "मणिपुर"), 15: ("మిజోరాం", "मिज़ोरम"), 16: ("త్రిపుర", "त्रिपुरा"),
    17: ("మేఘాలయ", "मेघालय"), 18: ("అస్సాం", "असम"), 19: ("పశ్చిమ బెంగాల్", "पश्चिम बंगाल"),
    20: ("ఝార్ఖండ్", "झारखंड"), 21: ("ఒడిశా", "ओडिशा"), 22: ("ఛత్తీస్‌గఢ్", "छत्तीसगढ़"),
    23: ("మధ్య ప్రదేశ్", "मध्य प्रदेश"), 24: ("గుజరాత్", "गुजरात"), 27: ("మహారాష్ట్ర", "महाराष्ट्र"),
    28: ("ఆంధ్ర ప్రదేశ్", "आंध्र प्रदेश"), 29: ("కర్ణాటక", "कर्नाटक"), 30: ("గోవా", "गोवा"),
    31: ("లక్షద్వీప్", "लक्षद्वीप"), 32: ("కేరళ", "केरल"), 33: ("తమిళనాడు", "तमिलनाडु"),
    34: ("పుదుచ్చేరి", "पुदुचेरी"), 35: ("అండమాన్ మరియు నికోబార్ దీవులు", "अंडमान और निकोबार द्वीपसमूह"),
    36: ("తెలంగాణ", "तेलंगाना"), 37: ("లద్దాఖ్", "लद्दाख"),
    38: ("దాద్రా మరియు నగర్ హవేలీ మరియు దమన్ మరియు దీయూ", "दादरा और नगर हवेली और दमन और दीव"),
}
DISTRICT_IDS = {510: "krishna", 523: "west-godavari", 748: "eluru"}
PILOT = PILOT_CONFIG["coverage"][0]
PILOT_NAMES = {district["id"]: district["name"] for district in PILOT["districts"]}
DEMO_DISTRICTS = set(PILOT_NAMES)


def build_directory():
    coverage = []
    locations = {}
    vegetables = {int(code): set() for code in DIRECTORY["states"]}
    for crop, record in CULTIVATION["crops"].items():
        for code in record["states"]:
            vegetables[code].add(crop)
    for record in CULTIVATION["supplements"]:
        vegetables[record["state"]].update(record["crops"])
    for code, state in DIRECTORY["states"].items():
        code = int(code)
        state_id = STATE_IDS.get(code, re.sub(r"[^a-z]+", "-", state["name"].lower()).strip("-"))
        te, hi = STATE_NAMES.get(code, (state["name"], state["name"]))
        name = {"en": state["name"], "te": te, "hi": hi}
        districts = []
        for lgd, district, *point in state["districts"]:
            district_id = DISTRICT_IDS.get(lgd, f"lgd-{lgd}")
            districts.append({
                "id": district_id, "name": PILOT_NAMES.get(district_id, {"en": district}),
                "enabled": True, "lgd_code": lgd, "live_weather": bool(point),
            })
            locations[state_id, district_id] = tuple(point) if point else None
        coverage.append({
            "id": state_id, "name": name, "lgd_code": code, "districts": districts,
            "vegetable_ids": sorted(vegetables[code]),
        })
    return sorted(coverage, key=lambda state: state["name"]["en"]), locations


COVERAGE, LOCATIONS = build_directory()
ADDITIONAL_STAGES = {
    "germination": {"en": "Germination", "te": "మొలకెత్తే దశ", "hi": "अंकुरण"},
    "seedling": {"en": "Seedling / transplanting", "te": "మొక్క / నాటే దశ", "hi": "पौध / रोपाई"},
    "establishment": {"en": "Plant establishment", "te": "మొక్క వేరు పట్టే దశ", "hi": "पौध जमने की अवस्था"},
    "vegetative": {"en": "Leaf growth", "te": "ఆకుల పెరుగుదల", "hi": "पत्तियों की बढ़वार"},
    "panicle-initiation": {"en": "Panicle initiation", "te": "కంకి ఏర్పడటం మొదలయ్యే దశ", "hi": "बाली बनना शुरू"},
    "flower-buds": {"en": "Flower buds forming", "te": "పూల మొగ్గలు ఏర్పడే దశ", "hi": "फूल की कलियाँ बनना"},
    "flowering": {"en": "Flowering", "te": "పూత", "hi": "फूल आना"},
    "fruiting": {"en": "Fruit development", "te": "కాయ పెరుగుదల", "hi": "फल की बढ़वार"},
    "bulb-initiation": {"en": "Bulb formation begins", "te": "ఉల్లి గడ్డ ఏర్పడటం మొదలు", "hi": "कंद बनना शुरू"},
    "bulb-development": {"en": "Bulb development", "te": "ఉల్లి గడ్డ పెరుగుదల", "hi": "कंद का विकास"},
    "tuber-initiation": {"en": "Tubers forming", "te": "దుంపలు ఏర్పడే దశ", "hi": "आलू के कंद बनना"},
    "tuber-bulking": {"en": "Tubers enlarging", "te": "దుంపలు పెరిగే దశ", "hi": "आलू के कंद बढ़ना"},
    "head-formation": {"en": "Head formation", "te": "క్యాబేజీ తల ఏర్పడే దశ", "hi": "पत्तागोभी का सिर बनना"},
    "curd-formation": {"en": "Curd formation", "te": "కాలీఫ్లవర్ పువ్వు ఏర్పడే దశ", "hi": "फूलगोभी का फूल बनना"},
    "pod-formation": {"en": "Pod formation", "te": "పొట్లకాయలు ఏర్పడే దశ", "hi": "फलियाँ बनना"},
    "pod-filling": {"en": "Pod filling", "te": "పొట్లకాయల్లో గింజలు నిండే దశ", "hi": "फलियों में दाने भरना"},
    "harvesting": {"en": "Harvesting / picking", "te": "కోత / కాయలు కోసే దశ", "hi": "कटाई / तुड़ाई"},
}
VEGETABLE_START = ["germination", "seedling", "establishment", "vegetative"]
HARVEST_STAGES = ["mature", "harvesting", "post-harvest"]
FRUITING_STAGES = [*VEGETABLE_START, "flower-buds", "flowering", "fruiting", *HARVEST_STAGES]
CONFIG = {
    "coverage": COVERAGE,
    "crops": {
        **PILOT_CONFIG["crops"],
        "tomato": {"en": "Tomato", "te": "టమాటా", "hi": "टमाटर"},
        "chilli": {"en": "Chilli", "te": "మిరప", "hi": "मिर्च"},
        "onion": {"en": "Onion", "te": "ఉల్లి", "hi": "प्याज़"},
        "okra": {"en": "Okra (bhindi)", "te": "బెండకాయ", "hi": "भिंडी"},
        "brinjal": {"en": "Brinjal (eggplant)", "te": "వంకాయ", "hi": "बैंगन"},
        "bottle-gourd": {"en": "Bottle gourd", "te": "సొరకాయ", "hi": "लौकी"},
        "cabbage": {"en": "Cabbage", "te": "క్యాబేజీ", "hi": "पत्तागोभी"},
        "cauliflower": {"en": "Cauliflower", "te": "కాలీఫ్లవర్", "hi": "फूलगोभी"},
        "peas": {"en": "Peas", "te": "పచ్చి బఠాణీలు", "hi": "मटर"},
        "potato": {"en": "Potato", "te": "బంగాళాదుంప", "hi": "आलू"},
    },
    "stages": {**PILOT_CONFIG["stages"], **ADDITIONAL_STAGES},
    "crop_stages": {
        "paddy": ["germination", "nursery", "establishment", "tillering", "panicle-initiation",
                  "reproductive", "grain-filling", *HARVEST_STAGES],
        "tomato": FRUITING_STAGES,
        "chilli": FRUITING_STAGES,
        "onion": [*VEGETABLE_START, "bulb-initiation", "bulb-development", *HARVEST_STAGES],
        "okra": FRUITING_STAGES,
        "brinjal": FRUITING_STAGES,
        "bottle-gourd": FRUITING_STAGES,
        "cabbage": [*VEGETABLE_START, "head-formation", *HARVEST_STAGES],
        "cauliflower": [*VEGETABLE_START, "curd-formation", *HARVEST_STAGES],
        "peas": [*VEGETABLE_START, "flowering", "pod-formation", "pod-filling", *HARVEST_STAGES],
        "potato": ["establishment", "vegetative", "tuber-initiation", "tuber-bulking", *HARVEST_STAGES],
        "none": [],
    },
    "demo_districts": sorted(DEMO_DISTRICTS),
}
DISTRICTS = {state["id"]: {district["id"] for district in state["districts"]} for state in COVERAGE}
