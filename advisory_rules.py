import json
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from evidence_index import rank
from evidence_store import PUBLISHED_PASSAGES

INDIA = ZoneInfo("Asia/Kolkata")
TOPICS = {
    "grain-drying": ("grain dry", "dry grain", "dry harvested", "drying", "grain moisture", "अनाज सुख", "धान सुख", "దాన్యం ఆర", "ధాన్యం ఆర", "ధాన్యం తేమ"),
    "spraying": ("spray", "छिड़क", "छिडक", "పిచికార"),
    "harvest": ("harvest", "कटाई", "काट", "కోత", "కోయ"),
    "irrigation": ("irrigat", "drain", "waterlog", "watering", "water my", "water the", "standing water", "सिंचाई", "पानी", "जल निकासी", "సాగునీ", "నీరు", "నీటి", "నీళ్లు", "కాలువ"),
    "district-rainfall-forecast": ("rain", "forecast", "weather", "बारिश", "वर्षा", "मौसम", "వర్ష", "వాతావరణ"),
}
WEATHER_TOPIC = "district-rainfall-forecast"
WEATHER_TERMS = TOPICS[WEATHER_TOPIC]
TIMING_TOPICS = {"irrigation", "spraying", "harvest"}

# Only reviewer-coded actions are rendered automatically. Each value is a distinct
# decision for its topic, so equally applicable incompatible values cause abstention.
ACTIONS = {
    "irrigation": {
        "maintain_moisture": (
            "Maintain adequate soil moisture. Avoid excess irrigation and standing water.",
            "నేలలో తగినంత తేమ ఉండేలా చూసుకోండి. ఎక్కువగా నీరు పెట్టడం, పొలంలో నీరు నిలవడం నివారించండి.",
            "मिट्टी में पर्याप्त नमी बनाए रखें। अधिक सिंचाई और जलभराव से बचें।",
        ),
        "avoid_irrigation": ("Hold off on irrigation.", "ఇప్పుడు నీరు పెట్టడం వాయిదా వేయండి.", "फिलहाल सिंचाई टालें।"),
    },
    "harvest": {
        "harvest_at_maturity": (
            "Harvest at physiological maturity and dry the grain before storage. See the cited passage for the maturity and moisture thresholds.",
            "పంట పూర్తిగా పండిన తర్వాత కోయండి. నిల్వకు ముందు ధాన్యాన్ని ఆరబెట్టండి. పరిపక్వత, తేమ పరిమితుల కోసం మూలాన్ని చూడండి.",
            "फसल के पूरी तरह पकने पर कटाई करें और भंडारण से पहले धान सुखाएँ। पकने और नमी की सीमाएँ दिए गए स्रोत में देखें।",
        ),
        "delay_harvest": ("Wait before harvesting.", "కోతను వాయిదా వేయండి.", "कटाई टालें।"),
    },
    "spraying": {
        "wait_until_dry": (
            "If spraying is needed, wait until the rain has stopped and the leaves are dry.",
            "పిచికారీ అవసరమైతే వర్షం ఆగి ఆకులు ఆరే వరకు వేచి ఉండండి.",
            "छिड़काव ज़रूरी हो तो बारिश रुकने और पत्तियाँ सूखने तक इंतज़ार करें।",
        ),
        "avoid_spraying": ("Hold off on spraying.", "పిచికారీని వాయిదా వేయండి.", "छिड़काव टालें।"),
    },
    "grain-drying": {
        "dry_grain_to_14": (
            "Dry harvested paddy to 14% grain moisture before storage.",
            "నిల్వకు ముందు కోసిన వరి ధాన్యాన్ని 14% తేమకు ఆరబెట్టండి.",
            "भंडारण से पहले कटे हुए धान को 14% नमी तक सुखाएँ।",
        ),
    },
}

MESSAGES = {
    "withhold": ("No action is recommended.", "ఇప్పుడు నిర్దిష్ట చర్యను సూచించలేం.", "अभी किसी कार्रवाई की सलाह नहीं दी जा सकती।"),
    "location": ("There is no approved pilot coverage for this district.", "ఈ జిల్లాకు ఆమోదించిన పైలట్ ఆధారాలు లేవు.", "इस ज़िले के लिए स्वीकृत पायलट साक्ष्य उपलब्ध नहीं है।"),
    "topic": ("The question does not match a covered advisory topic.", "ఈ ప్రశ్నకు వర్తించే సలహా అంశం అందుబాటులో లేదు.", "इस सवाल के विषय पर सलाह उपलब्ध नहीं है।"),
    "date": ("The question contains an invalid date.", "ప్రశ్నలో ఇచ్చిన తేదీ చెల్లదు.", "सवाल में दी गई तारीख मान्य नहीं है।"),
    "weather": ("No approved district rainfall forecast covers the requested date.", "అడిగిన తేదీకి ఆమోదించిన జిల్లా వర్షపాత అంచనా లేదు.", "माँगी गई तारीख के लिए ज़िले का स्वीकृत वर्षा पूर्वानुमान उपलब्ध नहीं है।"),
    "crop": ("No approved passage supports this practice for the selected crop, stage, area and date.", "ఈ పంట, దశ, ప్రాంతం, తేదీకి సరిపోయే ఆమోదిత సూచన లేదు.", "इस फसल, अवस्था, स्थान और तारीख के लिए इस काम पर स्वीकृत मार्गदर्शन उपलब्ध नहीं है।"),
    "unencoded": ("The applicable passages do not establish one reviewed decision.", "వర్తించే ఆధారాల నుంచి సమీక్షించిన ఒక నిర్ణయం లభించలేదు.", "लागू स्रोतों से कोई एक सत्यापित निर्णय तय नहीं होता।"),
    "conflict": ("Equally applicable approved sources disagree. Review the cited passages before acting.", "సమానంగా వర్తించే ఆధారాల్లో భిన్నమైన సూచనలు ఉన్నాయి. చర్యకు ముందు చూపిన మూలాలను పరిశీలించండి.", "समान रूप से लागू स्वीकृत स्रोतों में मतभेद है। कार्रवाई से पहले दिए गए स्रोत देखें।"),
    "stage": ("What stage is your paddy at?", "మీ వరి ఏ దశలో ఉంది?", "आपका धान किस अवस्था में है?"),
    "stage_why": ("Applicable guidance depends on the crop stage.", "వర్తించే సూచన పంట దశను బట్టి మారుతుంది.", "लागू सलाह फसल की अवस्था पर निर्भर करती है।"),
    "observation": ("Is water standing in the field, or has the soil started to dry?", "పొలంలో నీరు నిలిచిందా, లేక నేల ఆరడం మొదలైందా?", "क्या खेत में पानी भरा है या मिट्टी सूखने लगी है?"),
    "observation_why": ("A district forecast cannot establish the current moisture in your field.", "జిల్లా వాతావరణ అంచనాతో మీ పొలంలోని ప్రస్తుత తేమను నిర్ధారించలేం.", "ज़िले के पूर्वानुमान से आपके खेत की मौजूदा नमी तय नहीं होती।"),
    "standing": ("Since you report standing water, hold off on adding irrigation while water is standing.", "పొలంలో నీరు నిలిచిందని మీరు చెప్పారు. నీరు నిలిచి ఉన్నంతవరకు అదనంగా నీరు పెట్టకండి.", "आपने खेत में पानी भरा होने की बात कही है। जब तक पानी भरा है, अतिरिक्त सिंचाई टालें।"),
    "practice": ("The cited crop guidance applies to the selected area and crop stage.", "చూపిన పంట సూచన ఎంచుకున్న ప్రాంతానికి, పంట దశకు వర్తిస్తుంది.", "दी गई कृषि सलाह चुने गए क्षेत्र और फसल की अवस्था पर लागू है।"),
    "rain": ("The district bulletin forecast {amount:g} mm of rain for {date}.", "{date} తేదీకి జిల్లా బులెటిన్ {amount:g} మి.మీ. వర్షపాతాన్ని అంచనా వేసింది.", "ज़िले के बुलेटिन में {date} के लिए {amount:g} मिमी बारिश का पूर्वानुमान था।"),
    "weather_action": ("Use the district forecast when planning field work and check conditions at the field.", "పొలం పనులు నిర్ణయించేటప్పుడు జిల్లా అంచనాతో పాటు పొలంలోని పరిస్థితిని చూడండి.", "खेत का काम तय करते समय ज़िले का पूर्वानुमान और खेत की स्थिति देखें।"),
}


def localize(copy, language):
    return copy[{"en": 0, "te": 1, "hi": 2}[language]]


def requested_day(question, supplied=None, now=None):
    if supplied is not None:
        return supplied, True
    today = (now or datetime.now(INDIA)).astimezone(INDIA).date()
    text = question.casefold()
    match = re.search(r"\b\d{4}-\d{2}-\d{2}\b", text)
    if match:
        try:
            return date.fromisoformat(match[0]), True
        except ValueError:
            return None, True
    offsets = (
        (2, r"\bday after tomorrow\b|ఎల్లుండి|परसों"),
        (-1, r"\byesterday\b|నిన్న|बीता कल|पिछले कल"),
        (1, r"\btomorrow\b|రేపు|(?<!\w)कल(?!\w)"),
        (0, r"\btoday\b|ఈ రోజు|ఈరోజు|నేడు|आज"),
    )
    for offset, pattern in offsets:
        if re.search(pattern, text):
            return today + timedelta(days=offset), True
    return today, False


def applicable(connection, session, topic, day):
    rows = connection.execute(PUBLISHED_PASSAGES + """
        AND d.state_id = ? AND p.topic = ?
        AND (d.issue_date IS NULL OR d.issue_date <= ?)
        AND (COALESCE(p.valid_from, d.valid_from) IS NULL OR COALESCE(p.valid_from, d.valid_from) <= ?)
        AND (COALESCE(p.valid_until, d.valid_until) IS NULL OR COALESCE(p.valid_until, d.valid_until) >= ?)
        AND (
            (p.kind = 'weather' AND p.district_id = ? AND d.issue_date IS NOT NULL
                AND COALESCE(p.valid_from, d.valid_from) IS NOT NULL
                AND COALESCE(p.valid_until, d.valid_until) IS NOT NULL AND (p.crop IS NULL OR p.crop = ?))
            OR
            (p.kind IN ('advisory','background') AND p.crop = ?
                AND (p.district_id = ? OR (p.district_id IS NULL AND p.statewide = 1)))
        )
    """, (session.state_id, topic, day, day, day, session.district_id, session.crop, session.crop, session.district_id))
    return list(rows)


def preferred(rows):
    def specificity(row):
        return bool(row["district_id"]), bool(row["stage_id"])

    scopes = {specificity(row) for row in rows}
    # A district-only and a stage-only source can both apply without one
    # superseding the other. Discard a scope only when another is at least as specific on both axes.
    stronger = {scope for scope in scopes if not any(
        candidate != scope and all(a >= b for a, b in zip(candidate, scope)) for candidate in scopes
    )}
    rows = [row for row in rows if specificity(row) in stronger]

    def series(row):
        return row["publisher"], row["title"], row["original_url"]

    latest = {}
    for row in rows:
        key = series(row)
        latest[key] = max(latest.get(key, ""), row["issue_date"] or "")
    return [row for row in rows if (row["issue_date"] or "") == latest[series(row)]]


def rainfall_on(row, day):
    return json.loads(row["daily_rainfall"] or "{}").get(day)


def moisture_observation(value):
    text = (value or "").casefold()
    if any(term in text for term in ("no standing water", "no water is standing", "no water standing", "without standing water",
                                     "not waterlogged", "standing water is gone", "पानी नहीं भरा", "पानी भरा नहीं",
                                     "నీరు నిలవలేదు", "నీరు నిలిచి లేదు")):
        return "no_standing"
    if any(term in text for term in ("standing water", "water is standing", "waterlogged", "पानी भरा", "पानी जमा", "నీరు నిలి", "నీరు నిల్వ")):
        return "standing"
    if any(term in text for term in ("dry soil", "soil is dry", "soil is drying", "soil is moist", "मिट्टी सूख", "मिट्टी नम", "నేల ఆర", "నేల తేమ")):
        return "no_standing"
    return None


def citation(row):
    fields = ("title", "publisher", "original_url", "version", "issue_date", "sha256", "state_id", "district_id",
              "crop", "crop_stage", "topic", "page_number", "section")
    return {
        **{field: row[field] for field in fields},
        "passage_id": row["id"], "source_id": row["source_id"], "excerpt": row["content"],
        "language": row["evidence_language"], "valid_from": row["effective_from"], "valid_until": row["effective_until"],
        "is_demo": False,
    }


def decision(session, connection, covered_location):
    def message(key, **values):
        return localize(MESSAGES[key], session.language).format(**values)

    def result(status, reason, rows=(), action=None, field=None, follow_up=None):
        windows = [(row["effective_from"], row["effective_until"]) for row in rows if row["effective_from"] and row["effective_until"]]
        return {
            "status": status, "suggested_action": action or message("withhold"), "explanation": reason,
            "follow_up_question": message(follow_up) if follow_up else None, "follow_up_field": field,
            "evidence": [citation(row) for row in rows],
            "validity_window": {"valid_from": max(start for start, _ in windows), "valid_until": min(end for _, end in windows)} if windows else None,
        }

    if not covered_location:
        return result("insufficient_evidence", message("location"))
    if session.requested_date is None:
        return result("insufficient_evidence", message("date"))
    day = session.requested_date.isoformat()
    question = session.question.casefold()
    topic = next((name for name, terms in TOPICS.items() if any(term in question for term in terms)), None)
    if topic is None:
        return result("insufficient_evidence", message("topic"))

    needs_weather = topic == WEATHER_TOPIC or topic in TIMING_TOPICS and (
        session.date_explicit or any(term in question for term in WEATHER_TERMS)
    )
    weather = []
    amount = None
    if needs_weather:
        local = [row for row in applicable(connection, session, WEATHER_TOPIC, day)
                 if row["kind"] == "weather" and (row["stage_id"] == session.crop_stage
                                                    or (row["stage_id"] is None and not row["crop_stage"]))]
        weather = preferred(rank(session.question, local))
        amounts = {rainfall_on(row, day) for row in weather}
        if len(amounts - {None}) > 1:
            return result("conflicting_evidence", message("conflict"), weather)
        if not amounts or None in amounts:
            return result("insufficient_evidence", message("weather"))
        amount = next(iter(amounts))
        weather = weather[:1]
        if topic == WEATHER_TOPIC:
            return result("supported", message("rain", date=day, amount=amount), weather, action=message("weather_action"))

    candidates = [row for row in applicable(connection, session, topic, day) if row["kind"] != "weather"
                  and (row["stage_id"] or not row["crop_stage"])]
    if session.crop_stage == "unknown":
        generic = preferred([row for row in candidates if row["stage_id"] is None])
        specific = [row for row in candidates if row["stage_id"]]
        generic_codes = {row["decision_code"] for row in generic}
        stage_can_change_decision = (generic_codes | {row["decision_code"] for row in specific}) & ACTIONS[topic].keys()
        if stage_can_change_decision and specific and (
            len(generic_codes) != 1 or any(row["decision_code"] not in generic_codes for row in specific)
        ):
            return result("clarification", message("stage_why"), field="crop_stage", follow_up="stage")
    candidates = [row for row in candidates if row["stage_id"] in (None, session.crop_stage)]
    practices = preferred(rank(session.question, candidates))
    if not practices:
        return result("insufficient_evidence", message("crop"))
    codes = {row["decision_code"] for row in practices}
    supported_codes = codes & ACTIONS[topic].keys()
    if len(supported_codes) > 1:
        return result("conflicting_evidence", message("conflict"), practices)
    if len(codes) != 1 or not supported_codes:
        return result("insufficient_evidence", message("unencoded"), practices)
    code = next(iter(supported_codes))
    action = localize(ACTIONS[topic][code], session.language)
    if topic == "irrigation" and needs_weather and code == "maintain_moisture":
        moisture = moisture_observation(session.field_observations)
        if moisture is None:
            return result("clarification", message("observation_why"), field="field_observations", follow_up="observation")
        if moisture == "standing":
            action = message("standing")

    explanation = message("practice")
    if amount is not None:
        explanation += " " + message("rain", date=day, amount=amount)
    return result("supported", explanation, practices[:1] + weather, action=action)
