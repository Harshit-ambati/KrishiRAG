import json
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from evidence_index import rank
from evidence_store import PUBLISHED_PASSAGES
from live_weather import forecast_passage

INDIA = ZoneInfo("Asia/Kolkata")
TOPICS = {
    "grain-drying": ("grain dry", "dry grain", "dry harvested", "drying", "grain moisture", "अनाज सुख", "धान सुख", "దాన్యం ఆర", "ధాన్యం ఆర", "ధాన్యం తేమ"),
    "spraying": ("spray", "छिड़क", "छिडक", "పిచికార"),
    "harvest": ("harvest", "कटाई", "काट", "కోత", "కోయ"),
    "irrigation": ("irrigat", "drain", "waterlog", "watering", "water my", "water the", "standing water", "सिंचाई", "पानी", "जल निकासी", "సాగునీ", "నీరు", "నీటి", "నీళ్లు", "కాలువ"),
    "district-rainfall-forecast": ("rain", "forecast", "weather", "temperature", "wind", "बारिश", "वर्षा", "मौसम", "तापमान", "हवा", "వర్ష", "వాతావరణ", "ఉష్ణోగ్రత", "గాలి"),
}
WEATHER_TOPIC = "district-rainfall-forecast"
RAIN_TERMS = ("rain", "forecast", "weather", "बारिश", "वर्षा", "मौसम", "వర్ష", "వాతావరణ")
OTHER_WEATHER_TERMS = ("temperature", "wind", "तापमान", "हवा", "ఉష్ణోగ్రత", "గాలి")
TIMING_TOPICS = {"irrigation", "spraying", "harvest"}
GENERAL_VEGETABLE_IRRIGATION = {
    "tomato_even_water", "chilli_avoid_stagnation", "onion_good_drainage",
    "okra_moisture_at_fruit_set", "brinjal_rainy_season_drainage",
}
DEFINITIONS = {
    "drip-irrigation-definition": ("define_drip_irrigation", "drip", {
        "what is drip irrigation", "define drip irrigation", "how does drip irrigation work", "ड्रिप सिंचाई क्या है",
        "बूंद-बूंद सिंचाई क्या है", "బిందు సేద్యం అంటే ఏమిటి", "డ్రిప్ ఇరిగేషన్ అంటే ఏమిటి",
        "బిందు సేద్యం అంటే ఏంటి", "డ్రిప్ సాగు అంటే ఏమిటి",
    }),
    "sprinkler-irrigation-definition": ("define_sprinkler_irrigation", "sprinkler", {
        "what is sprinkler irrigation", "define sprinkler irrigation", "how does sprinkler irrigation work", "स्प्रिंकलर सिंचाई क्या है",
        "फव्वारा सिंचाई क्या है", "స్ప్రింక్లర్ సేద్యం అంటే ఏమిటి", "తుంపర సేద్యం అంటే ఏమిటి",
    }),
}

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
        "tomato_even_water": (
            "For organic tomatoes, keep the water supply even around fruit set. A dry spell followed by sudden irrigation can crack the fruit.",
            "సేంద్రియ టమాటాలో కాయలు పట్టే సమయంలో నీటి సరఫరా సమంగా ఉంచండి. నేల ఎండిపోయిన తర్వాత ఒక్కసారిగా నీరు పెడితే కాయలు పగిలే అవకాశం ఉంది.",
            "जैविक टमाटर में फल लगने के समय पानी की आपूर्ति समान रखें। सूखे के बाद अचानक सिंचाई करने से फल फट सकते हैं।",
        ),
        "chilli_avoid_stagnation": (
            "For organic chilli, irrigate carefully and avoid standing water in nursery beds and fields.",
            "సేంద్రియ మిరప నారుమడుల్లో, పొలాల్లో నీరు నిలవకుండా జాగ్రత్తగా సాగునీరు పెట్టండి.",
            "जैविक मिर्च की नर्सरी और खेत में सावधानी से सिंचाई करें और पानी जमा न होने दें।",
        ),
        "onion_good_drainage": (
            "For Bellary (large) onion, use soil that drains well.",
            "బెల్లారి (పెద్ద రకం) ఉల్లికి నీరు బాగా ఇంకిపోయే నేలను ఎంచుకోండి.",
            "बेल्लारी (बड़े आकार वाली) प्याज़ के लिए अच्छी जल निकासी वाली मिट्टी चुनें।",
        ),
        "okra_moisture_at_fruit_set": (
            "For organic okra, keep the soil moist during flowering and fruit set and avoid waterlogging.",
            "సేంద్రియ బెండలో పూత, కాయ పట్టే దశల్లో నేల తేమగా ఉంచండి. నీరు నిలవకుండా చూసుకోండి.",
            "जैविक भिंडी में फूल आने और फल लगने के दौरान मिट्टी नम रखें और जलभराव से बचें।",
        ),
        "brinjal_rainy_season_drainage": (
            "During the rainy season, keep water from standing in the brinjal field.",
            "వర్షాకాలంలో వంకాయ పొలంలో నీరు నిలవకుండా చూసుకోండి.",
            "बरसात के मौसम में बैंगन के खेत में पानी जमा न होने दें।",
        ),
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
    "answer_unavailable": ("A verified answer is unavailable.", "ధృవీకరించిన సమాధానం అందుబాటులో లేదు.", "सत्यापित जवाब उपलब्ध नहीं है।"),
    "sprinkler_definition": ("Sprinkler irrigation sprays water through the air using nozzles on pressurised pipes.",
                            "తుంపర సేద్యంలో ఒత్తిడితో గొట్టాల్లోకి పంపిన నీటిని నాజిళ్ల ద్వారా గాల్లోకి చల్లుతారు.",
                            "फव्वारा सिंचाई में दबाव वाली पाइपों के नोज़ल से पानी हवा में छिड़का जाता है।"),
    "sprinkler_explanation": ("The spray falls on the field like rain.", "నీటి తుంపర్లు వర్షంలా పొలంపై పడతాయి.", "पानी बारिश की तरह खेत पर गिरता है।"),
    "weather_gap": ("No applicable forecast is available for this location and date.", "ఈ ప్రాంతానికి, తేదీకి వర్తించే వాతావరణ అంచనా అందుబాటులో లేదు.", "इस स्थान और तारीख के लिए लागू मौसम पूर्वानुमान उपलब्ध नहीं है।"),
    "point_forecast": ("Forecast for {date}: {rain:g} mm of rain, {low:g}–{high:g} °C, and maximum wind {wind:g} km/h.",
                       "{date} తేదీ అంచనా: {rain:g} మి.మీ. వర్షం, {low:g}–{high:g} °C, గరిష్ఠ గాలి వేగం గంటకు {wind:g} కి.మీ.",
                       "{date} का पूर्वानुमान: {rain:g} मिमी बारिश, {low:g}–{high:g} °C और अधिकतम हवा {wind:g} किमी/घंटा।"),
    "point_scope": ("This is a forecast for a representative point in the district. Conditions can vary across fields.",
                    "ఇది జిల్లాలోని ఒక ప్రతినిధి ప్రదేశానికి ఇచ్చిన అంచనా. పొలాల పరిస్థితులు మారవచ్చు.",
                    "यह ज़िले के एक प्रतिनिधि स्थान का पूर्वानुमान है। अलग-अलग खेतों की स्थिति बदल सकती है।"),
    "bulletin_scope": ("The cited IMD bulletin gives a district-level forecast.",
                       "చూపిన IMD బులెటిన్ జిల్లా స్థాయి అంచనాను ఇస్తుంది.",
                       "दिए गए IMD बुलेटिन में ज़िला स्तर का पूर्वानुमान है।"),
    "drip_definition": ("Drip irrigation delivers water slowly near plant roots through small outlets on pipes or tubes.",
                        "బిందు సేద్యంలో గొట్టాలకు అమర్చిన చిన్న రంధ్రాల ద్వారా మొక్కల వేర్ల దగ్గర నెమ్మదిగా నీరు అందుతుంది.",
                        "ड्रिप सिंचाई में पाइप या नलियों पर लगे छोटे आउटलेट से पानी धीरे-धीरे पौधों की जड़ों के पास पहुँचता है।"),
    "drip_explanation": ("These outlets are called emitters.", "ఈ రంధ్రాలను ఎమిటర్లు అంటారు।", "इन आउटलेट को एमिटर कहते हैं।"),
    "vegetable_timing_gap": ("The crop source supports a general practice. It does not determine whether to irrigate on this date.",
                             "పంట మూలం సాధారణ పద్ధతిని సూచిస్తుంది. ఈ తేదీన నీరు పెట్టాలా అనేది అది నిర్ధారించదు.",
                             "फसल का स्रोत सामान्य तरीका बताता है। उससे तय नहीं होता कि इस तारीख को सिंचाई करनी चाहिए या नहीं।"),
    "withhold": ("No action is recommended.", "ఇప్పుడు నిర్దిష్ట చర్యను సూచించలేం.", "अभी किसी कार्रवाई की सलाह नहीं दी जा सकती।"),
    "location": ("The district is unavailable for the selected state or Union Territory.", "ఎంచుకున్న రాష్ట్రం లేదా కేంద్రపాలిత ప్రాంతంలో ఈ జిల్లా అందుబాటులో లేదు.", "चुने हुए राज्य या केंद्रशासित प्रदेश में यह ज़िला उपलब्ध नहीं है।"),
    "topic": ("The question does not match a covered advisory topic.", "ఈ ప్రశ్నకు వర్తించే సలహా అంశం అందుబాటులో లేదు.", "इस सवाल के विषय पर सलाह उपलब्ध नहीं है।"),
    "date": ("Ask about one day, such as tomorrow or a date in YYYY-MM-DD format.", "రేపు లేదా YYYY-MM-DD రూపంలో ఒక తేదీ వంటి ఒక రోజు గురించి అడగండి.", "एक दिन के बारे में पूछें, जैसे कल या YYYY-MM-DD प्रारूप में कोई तारीख।"),
    "weather": ("No approved district rainfall forecast covers the requested date.", "అడిగిన తేదీకి ఆమోదించిన జిల్లా వర్షపాత అంచనా లేదు.", "माँगी गई तारीख के लिए ज़िले का स्वीकृत वर्षा पूर्वानुमान उपलब्ध नहीं है।"),
    "crop": ("No approved passage supports this practice for the selected crop, stage, area and date.", "ఈ పంట, దశ, ప్రాంతం, తేదీకి సరిపోయే ఆమోదిత సూచన లేదు.", "इस फसल, अवस्था, स्थान और तारीख के लिए इस काम पर स्वीकृत मार्गदर्शन उपलब्ध नहीं है।"),
    "unencoded": ("The applicable passages do not establish one reviewed decision.", "వర్తించే ఆధారాల నుంచి సమీక్షించిన ఒక నిర్ణయం లభించలేదు.", "लागू स्रोतों से कोई एक सत्यापित निर्णय तय नहीं होता।"),
    "conflict": ("Equally applicable approved sources disagree. Review the cited passages before acting.", "సమానంగా వర్తించే ఆధారాల్లో భిన్నమైన సూచనలు ఉన్నాయి. చర్యకు ముందు చూపిన మూలాలను పరిశీలించండి.", "समान रूप से लागू स्वीकृत स्रोतों में मतभेद है। कार्रवाई से पहले दिए गए स्रोत देखें।"),
    "stage": ("What stage is your crop at?", "మీ పంట ఏ దశలో ఉంది?", "आपकी फसल किस अवस्था में है?"),
    "stage_why": ("Applicable guidance depends on the crop stage.", "వర్తించే సూచన పంట దశను బట్టి మారుతుంది.", "लागू सलाह फसल की अवस्था पर निर्भर करती है।"),
    "observation": ("Is water standing in the field, or has the soil started to dry?", "పొలంలో నీరు నిలిచిందా, లేక నేల ఆరడం మొదలైందా?", "क्या खेत में पानी भरा है या मिट्टी सूखने लगी है?"),
    "observation_why": ("A district forecast cannot establish the current moisture in your field.", "జిల్లా వాతావరణ అంచనాతో మీ పొలంలోని ప్రస్తుత తేమను నిర్ధారించలేం.", "ज़िले के पूर्वानुमान से आपके खेत की मौजूदा नमी तय नहीं होती।"),
    "standing": ("Since you report standing water, hold off on adding irrigation while water is standing.", "పొలంలో నీరు నిలిచిందని మీరు చెప్పారు. నీరు నిలిచి ఉన్నంతవరకు అదనంగా నీరు పెట్టకండి.", "आपने खेत में पानी भरा होने की बात कही है। जब तक पानी भरा है, अतिरिक्त सिंचाई टालें।"),
    "practice": ("The cited crop guidance applies to the selected area and crop stage.", "చూపిన పంట సూచన ఎంచుకున్న ప్రాంతానికి, పంట దశకు వర్తిస్తుంది.", "दी गई कृषि सलाह चुने गए क्षेत्र और फसल की अवस्था पर लागू है।"),
    "practice_short": ("This guidance applies to your selected area and crop stage.", "ఈ సూచన ఎంచుకున్న ప్రాంతానికి, పంట దశకు వర్తిస్తుంది.", "यह सलाह चुने गए क्षेत्र और फसल की अवस्था पर लागू है।"),
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
    dates = set(re.findall(r"\b\d{4}-\d{2}-\d{2}\b", text))
    if len(dates) > 1 or re.search(r"\b(next week|next month|this week|this weekend|today and tomorrow)\b|अगले हफ्ते|अगले सप्ताह|వచ్చే వారం", text):
        return None, True
    if dates:
        try:
            return date.fromisoformat(dates.pop()), True
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


def has_terms(text, terms):
    for term in terms:
        if not term.isascii() or term in {"irrigat", "waterlog", "drain", "harvest", "spray", "drying"}:
            if term in text:
                return True
        elif re.search(r"\b" + re.escape(term) + r"(?:s|y|ing)?\b", text):
            return True
    return False


def question_topic(question):
    text = question.casefold().strip().rstrip("?？।").strip()
    for topic, (_, _, questions) in DEFINITIONS.items():
        if text in questions:
            return topic
    return next((name for name, terms in TOPICS.items() if has_terms(text, terms)), None)


def needs_forecast(question, topic, explicit):
    return topic == WEATHER_TOPIC or topic in TIMING_TOPICS and (
        explicit or has_terms(question.casefold(), RAIN_TERMS)
    )


def applicable(connection, session, topic, day):
    rows = connection.execute(PUBLISHED_PASSAGES + """
        AND d.state_id = ? AND (? IS NULL OR p.topic = ?)
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
    """, (session.state_id, topic, topic, day, day, day, session.district_id, session.crop, session.crop, session.district_id))
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


def decision(session, connection, covered_location, forecast=None):
    topic = question_topic(session.question)
    informational = topic == WEATHER_TOPIC or topic in DEFINITIONS

    def message(key, **values):
        return localize(MESSAGES[key], session.language).format(**values)

    def result(status, reason, rows=(), action=None, field=None, follow_up=None):
        windows = [(row["effective_from"], row["effective_until"]) for row in rows if row["effective_from"] and row["effective_until"]]
        primary = action or message("answer_unavailable" if informational else "withhold")
        return {
            "status": status, "suggested_action": primary, "answer": primary if informational else None,
            "explanation": reason, "answer_type": "information" if informational else "advice",
            "follow_up_question": message(follow_up) if follow_up else None, "follow_up_field": field,
            "evidence": [citation(row) for row in rows],
            "validity_window": {"valid_from": max(start for start, _ in windows), "valid_until": min(end for _, end in windows)} if windows else None,
        }

    def support(code, action, action_rows, *, practice_rows=(), weather_rows=(), amount=None,
                practice_copy=None, weather_copy=None, snapshot=None, status="supported"):
        claims = [{
            "kind": "action", "text": action, "passage_ids": [row["id"] for row in action_rows],
        }]
        wording = {"action": [action]}
        if practice_rows:
            explanation = practice_copy or message("practice")
            claims.append({"kind": "practice", "text": explanation, "passage_ids": [row["id"] for row in practice_rows]})
            wording["practice"] = [explanation] if practice_copy else [explanation, message("practice_short")]
        if weather_rows:
            explanation = weather_copy or message("rain", date=day, amount=amount)
            claims.append({"kind": "weather", "text": explanation, "passage_ids": [row["id"] for row in weather_rows]})
            wording["weather"] = [explanation]
        return {
            **result(status, " ".join(claim["text"] for claim in claims[1:]),
                     [*practice_rows, *weather_rows], action=action),
            "claims": claims, "claim_wording": wording, "decision_code": code, "forecast_rainfall_mm": amount,
            "weather_snapshot": snapshot,
        }

    if not covered_location:
        return result("insufficient_evidence", message("location"))
    if session.requested_date is None:
        return result("insufficient_evidence", message("date"))
    day = session.requested_date.isoformat()
    if topic is None:
        return result("insufficient_evidence", message("topic"))
    if topic in DEFINITIONS:
        code, copy, _ = DEFINITIONS[topic]
        rows = list(connection.execute(PUBLISHED_PASSAGES + """
            AND d.state_id = 'india' AND p.topic = ? AND p.kind = 'background'
            AND p.crop IS NULL AND p.district_id IS NULL AND p.decision_code = ?
            AND (d.issue_date IS NULL OR d.issue_date <= ?)
            AND (COALESCE(p.valid_from, d.valid_from) IS NULL OR COALESCE(p.valid_from, d.valid_from) <= ?)
            AND (COALESCE(p.valid_until, d.valid_until) IS NULL OR COALESCE(p.valid_until, d.valid_until) >= ?)
        """, (topic, code, day, day, day)))
        sources = preferred(rank(session.question, rows))[:1]
        if not sources:
            return result("insufficient_evidence", message("topic"))
        return support(code, message(f"{copy}_definition"), sources, practice_rows=sources,
                       practice_copy=message(f"{copy}_explanation"))

    needs_weather = needs_forecast(session.question, topic, session.date_explicit)
    weather = []
    amount = None
    point_copy = None
    snapshot = None
    if needs_weather:
        local = [row for row in applicable(connection, session, WEATHER_TOPIC, day)
                 if row["kind"] == "weather" and (row["stage_id"] == session.crop_stage
                                                    or (row["stage_id"] is None and not row["crop_stage"]))]
        weather = preferred(rank(session.question, local))
        amounts = {rainfall_on(row, day) for row in weather}
        if len(amounts - {None}) > 1:
            return result("conflicting_evidence", message("conflict"), weather)
        only_missing_metrics = topic == WEATHER_TOPIC and has_terms(session.question.casefold(), OTHER_WEATHER_TERMS)
        if amounts and None not in amounts and not only_missing_metrics:
            amount = next(iter(amounts))
            weather = weather[:1]
        elif forecast and forecast.day == session.requested_date:
            snapshot = forecast
            amount = forecast.rainfall_mm
            weather = [forecast_passage(forecast, session.state_id, session.district_id)]
            point_copy = message("point_forecast", date=day, rain=amount, low=forecast.low_c,
                                 high=forecast.high_c, wind=forecast.wind_kmh)
        else:
            reason = "weather_gap" if only_missing_metrics or session.crop != "paddy" else "weather"
            return result("insufficient_evidence", message(reason))
        if topic == WEATHER_TOPIC:
            return support("plan_with_district_forecast", point_copy or message("rain", date=day, amount=amount),
                           weather, weather_rows=weather, amount=amount,
                           weather_copy=message("point_scope" if snapshot else "bulletin_scope"), snapshot=snapshot)

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
            code = "avoid_irrigation_while_standing"

    general_vegetable_practice = code in GENERAL_VEGETABLE_IRRIGATION and needs_weather
    practice_copy = message("vegetable_timing_gap") if general_vegetable_practice else None
    weather_copy = f'{point_copy} {message("point_scope")}' if point_copy else None
    return support(code, action, practices[:1], practice_rows=practices[:1], weather_rows=weather,
                   amount=amount, practice_copy=practice_copy, weather_copy=weather_copy, snapshot=snapshot,
                   status="conditional" if general_vegetable_practice else "supported")
