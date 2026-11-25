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
    "irrigation": ("irrigat", "drain", "waterlog", "watering", "water my", "water the", "how much water",
                   "standing water", "सिंचाई", "पानी", "जल निकासी", "సాగునీ", "నీరు", "నీటి", "నీళ్లు", "కాలువ"),
    "district-rainfall-forecast": ("rain", "forecast", "weather", "temperature", "wind", "बारिश", "वर्षा", "मौसम", "तापमान", "हवा", "వర్ష", "వాతావరణ", "ఉష్ణోగ్రత", "గాలి"),
}
WEATHER_TOPIC = "district-rainfall-forecast"
SOIL_MOISTURE_TERMS = ("soil moisture", "मिट्टी की नमी", "నేల తేమ")
RAIN_TERMS = ("rain", "forecast", "weather", "बारिश", "वर्षा", "मौसम", "వర్ష", "వాతావరణ")
OTHER_WEATHER_TERMS = ("temperature", "wind", "तापमान", "हवा", "ఉష్ణోగ్రత", "గాలి")
IRRIGATION_QUANTITY_TERMS = ("how much water", "how much irrigation", "irrigation depth", "water depth",
                            "litre", "liter", "कितना पानी", "पानी की गहराई", "ఎంత నీరు", "నీటి లోతు")
UNKNOWN_MOISTURE = (
    "I’m not sure about soil moisture", "నేల తేమ గురించి నాకు తెలియదు", "मुझे मिट्टी की नमी पता नहीं",
)
REVIEWED_HARVEST_TEXT = (
    "Harvest at physiological maturity, when roughly 80–85% of grains in a panicle are mature. "
    "Dry grain to 12–14% moisture before storage."
)
MULTI_DAY_REQUEST = re.compile(
    r"\b(next week|next month|this week|this weekend|today and tomorrow)\b"
    r"|\b(?:next|coming|following)\s+(?:\d+|two|three|four|five|six|seven|few)\s+days\b"
    r"|अगले हफ्ते|अगले सप्ताह|(?:अगले|आने वाले)\s+(?:\d+|दो|तीन|चार|पाँच|छह|सात|कुछ)\s+दिन"
    r"|వచ్చే వారం|(?:వచ్చే|రాబోయే)\s+(?:\d+|రెండు|మూడు|నాలుగు|ఐదు|ఆరు|ఏడు|కొన్ని)\s+రోజు"
)
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
    "tomato-leaf-yellowing": ("screen_tomato_yellowing", "tomato_yellowing", ()),
    "tomato-blossom-end-rot": ("screen_tomato_blossom_end_rot", "tomato_blossom_end_rot", ()),
    "tomato-leaf-spot-precautions": ("prevent_tomato_leaf_spot_spread", "tomato_precautions", ()),
    "potato-harvest-duration": ("explain_potato_harvest_duration", "potato_harvest_duration", ()),
}
DEFINITION_CROPS = {
    "tomato-leaf-yellowing": "tomato",
    "tomato-blossom-end-rot": "tomato",
    "tomato-leaf-spot-precautions": "tomato",
    "potato-harvest-duration": "potato",
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
        "harvest_mature_paddy_in_dry_weather": (
            "Harvest and thresh mature paddy while field conditions are dry.",
            "పొలం పరిస్థితులు పొడిగా ఉన్నప్పుడు పండిన వరిని కోసి, నూర్పిడి చేయండి.",
            "खेत की स्थिति सूखी होने पर पके धान की कटाई और मड़ाई करें।",
        ),
        "delay_harvest": ("Wait before harvesting.", "కోతను వాయిదా వేయండి.", "कटाई टालें।"),
        "okra_harvest_tender": (
            "Pick organic okra while the pods are tender. Around 7–10 cm is typical. The right size varies by variety and market.",
            "సేంద్రియ బెండకాయలు లేతగా ఉన్నప్పుడే కోయండి. సాధారణంగా 7–10 సెం.మీ. పొడవు ఉంటుంది. రకం, మార్కెట్‌ను బట్టి తగిన పరిమాణం మారుతుంది.",
            "जैविक भिंडी की फलियाँ कोमल होने पर तोड़ें। आम तौर पर 7–10 सेमी लंबाई ठीक होती है। सही आकार किस्म और बाज़ार पर निर्भर करता है।",
        ),
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
    "paddy_grain_filling": (
        "The bulletin covers paddy from grain filling to grain hardening. Its guidance is to keep enough moisture in the soil while avoiding excess irrigation and standing water.",
        "ఈ బులెటిన్ వరి గింజలు నిండే దశ నుంచి గట్టిపడే దశ వరకు వర్తిస్తుంది. నేలలో తగినంత తేమ ఉంచుతూ, ఎక్కువగా నీరు పెట్టకుండా, నీరు నిలవకుండా చూడాలని సూచిస్తుంది.",
        "बुलेटिन धान में दाना भरने से दाना सख्त होने तक की अवस्था पर लागू है। इसमें मिट्टी में पर्याप्त नमी रखने और अधिक सिंचाई व जलभराव से बचने की सलाह है।",
    ),
    "paddy_no_standing": (
        "Your field observation indicates no standing water. Check soil moisture at the field before deciding how much water, if any, to add.",
        "మీ పరిశీలన ప్రకారం పొలంలో నీరు నిలవలేదు. నీరు పెట్టాల్సి ఉందా, ఎంత పెట్టాలి అనేది నిర్ణయించే ముందు పొలంలో నేల తేమను చూడండి.",
        "आपके खेत के विवरण से पानी खड़ा होने का संकेत नहीं मिलता। पानी देना है या नहीं और कितना देना है, यह तय करने से पहले खेत की मिट्टी में नमी देखें।",
    ),
    "paddy_standing_reason": (
        "The standing water you observed is the reason to pause irrigation. Use the field condition when deciding whether to resume.",
        "పొలంలో నీరు నిలిచి ఉండటంతో సాగునీరు పెట్టడం వాయిదా వేయాలి. మళ్లీ నీరు ఎప్పుడు పెట్టాలో పొలం పరిస్థితిని బట్టి నిర్ణయించండి.",
        "खेत में खड़ा पानी सिंचाई टालने का कारण है। सिंचाई फिर कब शुरू करनी है, यह खेत की स्थिति देखकर तय करें।",
    ),
    "forecast_field_limit": (
        "This is a forecast for planning. Check conditions at your field before making a field-work decision.",
        "ఇది పనుల ప్రణాళిక కోసం ఇచ్చిన అంచనా. పొలం పనులపై నిర్ణయం తీసుకునే ముందు మీ పొలంలోని పరిస్థితిని చూడండి.",
        "यह पूर्वानुमान काम की योजना बनाने के लिए है। खेत के काम पर फैसला लेने से पहले अपने खेत की स्थिति देखें।",
    ),
    "paddy_harvest_reason": (
        "The maturity percentage refers to grains on the panicle before cutting. The moisture percentage refers to the harvested grain before storage. The bulletin gives these checks for different steps.",
        "పరిపక్వత శాతం కోతకు ముందు కంకిలోని గింజలకు వర్తిస్తుంది. తేమ శాతం నిల్వకు ముందు కోసిన ధాన్యానికి వర్తిస్తుంది. బులెటిన్ ఈ రెండు దశలకు వేర్వేరు ప్రమాణాలు ఇస్తుంది.",
        "पकने का प्रतिशत कटाई से पहले बाली के दानों पर लागू है। नमी का प्रतिशत भंडारण से पहले काटे गए धान पर लागू है। बुलेटिन में दोनों चरणों की अलग-अलग जाँच दी गई है।",
    ),
    "okra_harvest_reason": (
        "Use tenderness as the readiness check for picking. The length range is a guide for organic okra, and the suitable size can vary across varieties and markets.",
        "కోతకు కాయ లేతగా ఉందో చూడండి. ఈ పొడవు సేంద్రియ బెండకు ఒక సూచన. సరైన పరిమాణం రకం, మార్కెట్‌ను బట్టి మారవచ్చు.",
        "तुड़ाई के लिए फलियों की कोमलता देखें। लंबाई की सीमा जैविक भिंडी के लिए एक संकेत है। सही आकार किस्म और बाज़ार के अनुसार बदल सकता है।",
    ),
    "okra_moisture_reason": (
        "The guide identifies flowering and the start of pod formation as sensitive to moisture stress. Keeping the soil moist at this stage also means preventing water from pooling.",
        "పూత, కాయలు పట్టడం మొదలయ్యే దశల్లో తేమ కొరత ప్రభావం చూపుతుందని సూచన చెబుతుంది. ఈ దశలో నేల తేమగా ఉండడంతో పాటు నీరు నిలవకుండా చూడాలి.",
        "मार्गदर्शिका के अनुसार फूल आने और फलियाँ बनना शुरू होने के समय नमी की कमी का असर पड़ता है। इस अवस्था में मिट्टी नम रखें और पानी जमा होने से बचाएँ।",
    ),
    "crop_selection": ("Select the crop to check what guidance applies to your field.",
                       "మీ పొలానికి వర్తించే సూచన కోసం పంటను ఎంచుకోండి.",
                       "अपने खेत पर लागू मार्गदर्शन देखने के लिए फसल चुनें।"),
    "crop_stage_gap": ("Reviewed guidance exists for this crop and location, but none applies to the selected crop stage on that date.",
                       "ఈ పంటకు, ప్రాంతానికి సమీక్షించిన సూచనలు ఉన్నాయి. అడిగిన తేదీన ఎంచుకున్న పంట దశకు వర్తించే సూచన లేదు.",
                       "इस फसल और स्थान के लिए समीक्षा की गई सलाह है, लेकिन उस तारीख पर चुनी गई फसल अवस्था के लिए सलाह उपलब्ध नहीं है।"),
    "weather_available": ("A forecast is available for the requested date.", "అడిగిన తేదీకి వాతావరణ అంచనా అందుబాటులో ఉంది.",
                          "पूछी गई तारीख का मौसम पूर्वानुमान उपलब्ध है।"),
    "weather_needed": ("A forecast for that date is needed for a weather-sensitive decision.",
                       "వాతావరణంపై ఆధారపడే నిర్ణయానికి ఆ తేదీ అంచనా అవసరం.",
                       "मौसम पर निर्भर फैसले के लिए उस तारीख का पूर्वानुमान चाहिए।"),
    "forecast_range": ("Open District forecast to compare the next 3, 5, or 7 days.",
                       "రాబోయే 3, 5 లేదా 7 రోజులను పోల్చడానికి జిల్లా వాతావరణ అంచనా తెరవండి.",
                       "अगले 3, 5 या 7 दिनों की तुलना के लिए ज़िले का मौसम पूर्वानुमान खोलें।"),
    "moisture_unknown": ("Check whether water is standing or the soil has begun to dry, then update your field observation.",
                         "పొలంలో నీరు నిలిచిందా లేక నేల ఆరడం మొదలైందా చూసి, మీరు గమనించిన వివరాన్ని జోడించండి.",
                         "देखें कि खेत में पानी खड़ा है या मिट्टी सूखने लगी है, फिर खेत का विवरण अपडेट करें।"),
    "water_quantity_gap": ("The cited crop guidance does not specify how much water to apply.",
                           "చూపిన పంట సూచనలో ఎంత నీరు పెట్టాలో పేర్కొనలేదు.",
                           "दिए गए फसल स्रोत में सिंचाई के लिए पानी की मात्रा नहीं बताई गई है।"),
    "harvest_thresholds": (
        "Harvest when roughly 80–85% of the grains in a panicle are mature. Before storage, dry the grain to 12–14% moisture.",
        "ఒక కంకిలో దాదాపు 80–85% గింజలు పండినప్పుడు కోయండి. నిల్వకు ముందు ధాన్యాన్ని 12–14% తేమ వరకు ఆరబెట్టండి.",
        "बाली के करीब 80–85% दाने पकने पर कटाई करें। भंडारण से पहले दानों को 12–14% नमी तक सुखाएँ।",
    ),
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
    "potato_harvest_duration_definition": (
        "If you mean after planting seed potatoes, allow roughly 70–100 days for the varieties covered in this ICAR guide. The time depends on the variety.",
        "విత్తన బంగాళాదుంపలు నాటిన తర్వాత ఎంత కాలం అని అడుగుతుంటే, ఈ ICAR మార్గదర్శకంలోని రకాలకు సుమారు 70–100 రోజులు పడుతుంది. కాలవ్యవధి రకాన్ని బట్టి మారుతుంది.",
        "अगर आपका मतलब बीज आलू लगाने के बाद से है, तो इस ICAR मार्गदर्शिका की किस्मों में लगभग 70–100 दिन लगते हैं। समय किस्म पर निर्भर करता है।",
    ),
    "potato_harvest_duration_explanation": (
        "ICAR lists 70–90 days for Kufri Pukhraj, 75–80 days for Kufri Ashoka, and 90–100 days for Kufri Surya. Count from the planting date and check which variety you planted.",
        "ICAR ప్రకారం కుఫ్రి పుఖ్‌రాజ్‌కు 70–90 రోజులు, కుఫ్రి అశోకకు 75–80 రోజులు, కుఫ్రి సూర్యకు 90–100 రోజులు. నాటిన తేదీ నుంచి లెక్కించి, మీరు నాటిన రకాన్ని చూసుకోండి.",
        "ICAR के अनुसार कुफरी पुखराज में 70–90 दिन, कुफरी अशोका में 75–80 दिन और कुफरी सूर्या में 90–100 दिन लगते हैं। रोपाई की तारीख से गिनें और अपनी किस्म की पुष्टि करें।",
    ),
    "tomato_yellowing_definition": (
        "Yellow tomato leaves can have several causes. Check where it began and what else you see. Dark spots with yellow margins suggest a leaf-spot problem. Yellowing between veins can point to a nutrient problem. Lower leaves turning yellow together with wilting can point to a wilt disease. The pattern helps narrow the cause.",
        "టమాటా ఆకులు పసుపు రంగులోకి మారడానికి అనేక కారణాలు ఉండవచ్చు. మొదట ఏ ఆకుల్లో మొదలైందో, ఇతర లక్షణాలు ఏమిటో చూడండి. పసుపు అంచులతో నల్లటి మచ్చలు ఆకుమచ్చ సమస్యను సూచించవచ్చు. ఈనెల మధ్య పసుపుదనం పోషక సమస్యను సూచించవచ్చు. కింది ఆకులు పసుపు రంగులోకి మారి మొక్క వాడిపోతే వాడుదల వ్యాధి ఒక అవకాశం.",
        "टमाटर की पत्तियाँ कई कारणों से पीली हो सकती हैं। देखें कि पीलापन कहाँ शुरू हुआ और साथ में क्या दिख रहा है। पीले घेरों वाले गहरे धब्बे पत्ती धब्बा रोग का संकेत हो सकते हैं। नसों के बीच पीलापन पोषक तत्वों की समस्या का संकेत हो सकता है। निचली पत्तियाँ पीली हों और पौधा मुरझाए तो मुरझान रोग की संभावना है।",
    ),
    "tomato_precautions_explanation": (
        "If you see leaf spots, water at the base and keep foliage dry. Mulch to reduce soil splash, support the plants so air can circulate, and wait until leaves are dry before pruning or handling them.",
        "ఆకులపై మచ్చలు ఉంటే మొక్క అడుగున నీరు పెట్టి ఆకులు పొడిగా ఉండేలా చూడండి. నేల చిమ్మకుండా మల్చింగ్ చేయండి. గాలి ఆడేలా మొక్కలకు ఆధారం ఇవ్వండి. ఆకులు ఆరిన తర్వాతే కత్తిరించండి లేదా తాకండి.",
        "पत्तियों पर धब्बे हों तो पौधे की जड़ के पास पानी दें और पत्तियाँ सूखी रखें। मिट्टी के छींटे रोकने के लिए मल्च बिछाएँ, हवा आने-जाने के लिए पौधों को सहारा दें और पत्तियाँ सूखने के बाद ही छँटाई करें या उन्हें छुएँ।",
    ),
    "symptom_uncertainty": (
        "Compare the leaf pattern and check for wilting before drawing a conclusion.",
        "కారణాన్ని నిర్ణయించే ముందు ఆకులపై లక్షణాలను సరిపోల్చి, మొక్క వాడుతోందో చూడండి.",
        "कारण तय करने से पहले पत्तियों के लक्षणों की तुलना करें और देखें कि पौधा मुरझा रहा है या नहीं।",
    ),
    "tomato_blossom_end_rot_definition": (
        "A dark, sunken, leathery patch at the end opposite the stem may be blossom-end rot. It happens when the growing fruit gets too little calcium. Uneven or shallow watering can contribute.",
        "కాడకు ఎదురుగా ఉన్న చివర ముదురు రంగులో లోపలికి కుంగిన గట్టి మచ్చ ఉంటే అది కాయ చివర కుళ్లు కావచ్చు. పెరుగుతున్న కాయకు తగినంత కాల్షియం అందకపోతే ఇది వస్తుంది. నీరు సక్రమంగా పెట్టకపోవడం లేదా పైపైన మాత్రమే తడపడం ఇందుకు దోహదపడవచ్చు.",
        "डंठल के विपरीत सिरे पर गहरा, धँसा और सख्त धब्बा ब्लॉसम-एंड रॉट हो सकता है। बढ़ते फल को पर्याप्त कैल्शियम न मिलने पर यह होता है। अनियमित या उथली सिंचाई इसकी वजह बन सकती है।",
    ),
    "tomato_blossom_end_rot_explanation": (
        "Keep soil moisture steady and use mulch to slow drying. Check soil pH before deciding whether to add a soil amendment.",
        "నేల తేమ స్థిరంగా ఉంచండి. నేల త్వరగా ఆరకుండా మల్చింగ్ చేయండి. నేల సవరణ పదార్థం వేయాలా అని నిర్ణయించే ముందు పీహెచ్ పరీక్షించండి.",
        "मिट्टी की नमी स्थिर रखें और मिट्टी को जल्दी सूखने से बचाने के लिए मल्च बिछाएँ। मिट्टी में सुधार के लिए कुछ डालने से पहले उसका पीएच जाँचें।",
    ),
    "general_topic": (
        "This question needs a reviewed general farming source. For a decision about your field or its weather, use Local crop & weather.",
        "ఈ ప్రశ్నకు సమీక్షించిన సాధారణ వ్యవసాయ మూలం అవసరం. మీ పొలం లేదా స్థానిక వాతావరణం గురించి అడగాలంటే స్థానిక పంట, వాతావరణ విభాగాన్ని ఎంచుకోండి.",
        "इस सवाल के लिए खेती का समीक्षा किया हुआ सामान्य स्रोत चाहिए। अपने खेत या वहाँ के मौसम के बारे में पूछने के लिए स्थानीय फसल और मौसम चुनें।",
    ),
    "point_soil": (
        "Estimated daily mean surface soil moisture (0–1 cm) at the reference point is {value:g}%. Check your field before irrigating.",
        "జిల్లా నమూనా స్థానం వద్ద పైనేల (0–1 సెం.మీ.) సగటు తేమ అంచనా {value:g}%. నీరు పెట్టే ముందు మీ పొలాన్ని పరిశీలించండి.",
        "ज़िले के संदर्भ बिंदु पर सतही मिट्टी (0–1 सेमी) की अनुमानित दैनिक औसत नमी {value:g}% है। सिंचाई से पहले अपने खेत की स्थिति देखें।",
    ),
    "point_soil_missing": (
        "The surface soil moisture estimate is unavailable for this location and date.",
        "ఈ ప్రాంతం, తేదీకి పైనేల తేమ అంచనా అందుబాటులో లేదు.",
        "इस स्थान और तारीख के लिए सतही मिट्टी की नमी का अनुमान उपलब्ध नहीं है।",
    ),
    "vegetable_timing_gap": ("The crop source supports a general practice. It does not determine whether to irrigate on this date.",
                             "పంట మూలం సాధారణ పద్ధతిని సూచిస్తుంది. ఈ తేదీన నీరు పెట్టాలా అనేది అది నిర్ధారించదు.",
                             "फसल का स्रोत सामान्य तरीका बताता है। उससे तय नहीं होता कि इस तारीख को सिंचाई करनी चाहिए या नहीं।"),
    "harvest_timing_gap": ("The crop source describes when pods are ready to pick. It does not establish whether the weather is suitable for picking on this date.",
                           "పంట మూలం కాయలు ఎప్పుడు కోతకు సిద్ధంగా ఉంటాయో చెబుతుంది. ఈ తేదీన కోతకు వాతావరణం అనుకూలమో నిర్ధారించదు.",
                           "फसल का स्रोत बताता है कि फलियाँ कब तोड़ने लायक होती हैं। उससे यह तय नहीं होता कि इस तारीख को तुड़ाई के लिए मौसम अनुकूल है।"),
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
    if len(dates) > 1 or MULTI_DAY_REQUEST.search(text):
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
    if has_terms(text, ("potato", "potatoes", "आलू", "బంగాళాదుంప", "ఆలుగడ్డ")) and not has_terms(
        text, ("sweet potato", "sweet potatoes", "chinese potato", "chinese potatoes", "शकरकंद", "చిలగడ")
    ) and has_terms(text, (
        "how many days", "how long", "days", "duration", "कितने दिन", "कितना समय", "ఎన్ని రోజులు", "ఎంత కాలం",
    )) and has_terms(text, (
        "harvest", "mature", "maturity", "cultivate", "grow", "कटाई", "खुदाई", "पकने", "खेती", "కోత", "తవ్వ", "పరిపక్వ", "సాగు",
    )):
        return "potato-harvest-duration"
    if has_terms(text, ("tomato", "tomatoes", "टमाटर", "టమాటా", "టమోటా")):
        if has_terms(text, ("leaf", "leaves", "foliage", "पत्त", "ఆకు", "ఆకుల")) and has_terms(
            text, ("yellow", "yellowing", "पील", "పసుపు")
        ):
            return "tomato-leaf-yellowing"
        if has_terms(text, ("blossom-end rot", "blossom end rot", "ब्लॉसम-एंड रॉट", "కాయ చివర కుళ్లు")) or all(
            has_terms(text, terms) for terms in (
                ("bottom", "blossom end", "opposite the stem", "नीचे", "सिरे", "చివర", "అడుగున"),
                ("black", "dark", "sunken", "rot", "काल", "धब्ब", "निचल", "నల్ల", "ముదురు", "కుళ్లు"),
            )
        ):
            return "tomato-blossom-end-rot"
    if has_terms(text, SOIL_MOISTURE_TERMS) and not any(
        has_terms(text, terms) for name, terms in TOPICS.items() if name != WEATHER_TOPIC
    ):
        return WEATHER_TOPIC
    return next((name for name, terms in TOPICS.items() if has_terms(text, terms)), None)


def needs_forecast(question, topic, explicit):
    return topic == WEATHER_TOPIC or topic in TIMING_TOPICS and (
        explicit or has_terms(question.casefold(), (*RAIN_TERMS, *SOIL_MOISTURE_TERMS))
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
    informational = session.question_type == "general" or topic == WEATHER_TOPIC or topic in DEFINITIONS

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
        evidence = list({row["id"]: row for row in (*action_rows, *practice_rows, *weather_rows)}.values())
        return {
            **result(status, " ".join(claim["text"] for claim in claims[1:]),
                     evidence, action=action),
            "claims": claims, "claim_wording": wording, "decision_code": code, "forecast_rainfall_mm": amount,
            "weather_snapshot": snapshot,
        }

    if session.question_type == "general" and topic not in DEFINITIONS:
        return result("insufficient_evidence", message("general_topic"), action=message("answer_unavailable"))
    if not covered_location and session.question_type != "general":
        return result("insufficient_evidence", message("location"))
    if session.requested_date is None:
        reason = "forecast_range" if topic == WEATHER_TOPIC and MULTI_DAY_REQUEST.search(session.question.casefold()) else "date"
        return result("insufficient_evidence", message(reason))
    day = session.requested_date.isoformat()
    if topic is None:
        return result("insufficient_evidence", message("topic"))
    if topic in DEFINITIONS:
        code, copy, _ = DEFINITIONS[topic]
        def national_sources(topic_id, decision_code, crop=None):
            rows = list(connection.execute(PUBLISHED_PASSAGES + """
                AND d.state_id = 'india' AND p.topic = ? AND p.kind = 'background'
                AND p.district_id IS NULL AND p.decision_code = ? AND COALESCE(p.crop, ?) IS ?
                AND (d.issue_date IS NULL OR d.issue_date <= ?)
                AND (COALESCE(p.valid_from, d.valid_from) IS NULL OR COALESCE(p.valid_from, d.valid_from) <= ?)
                AND (COALESCE(p.valid_until, d.valid_until) IS NULL OR COALESCE(p.valid_until, d.valid_until) >= ?)
            """, (topic_id, decision_code, crop, crop, day, day, day)))
            return preferred(rank(session.question, rows))[:1]

        sources = national_sources(topic, code, DEFINITION_CROPS.get(topic))
        if not sources:
            return result("insufficient_evidence", message("topic"))
        if topic == "tomato-leaf-yellowing":
            precautions = national_sources("tomato-leaf-spot-precautions", "prevent_tomato_leaf_spot_spread", "tomato")
            return support(code, message("tomato_yellowing_definition"), sources,
                           practice_rows=precautions or sources, practice_copy=message(
                               "tomato_precautions_explanation" if precautions else "symptom_uncertainty"))
        return support(code, message(f"{copy}_definition"), sources, practice_rows=sources, practice_copy=message(f"{copy}_explanation"))

    needs_weather = needs_forecast(session.question, topic, session.date_explicit)
    candidates = [row for row in applicable(connection, session, topic, day) if row["kind"] != "weather"
                  and (row["stage_id"] or not row["crop_stage"])] if topic != WEATHER_TOPIC else []
    stage_candidates = [row for row in candidates if row["stage_id"] in (None, session.crop_stage)]

    def crop_gap():
        reason = "crop_selection" if session.crop == "none" else "crop_stage_gap" if candidates else "crop"
        return message(reason)

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
        soil_requested = topic == WEATHER_TOPIC and has_terms(session.question.casefold(), SOIL_MOISTURE_TERMS)
        only_missing_metrics = soil_requested or (topic == WEATHER_TOPIC and has_terms(session.question.casefold(), OTHER_WEATHER_TERMS))
        if amounts and None not in amounts and not only_missing_metrics:
            amount = next(iter(amounts))
            weather = weather[:1]
        elif forecast and forecast.day == session.requested_date:
            snapshot = forecast
            amount = forecast.rainfall_mm
            weather = [forecast_passage(forecast, session.state_id, session.district_id)]
            point_copy = message("point_forecast", date=day, rain=amount, low=forecast.low_c,
                                 high=forecast.high_c, wind=forecast.wind_kmh)
            if forecast.soil_moisture_m3_m3 is not None:
                point_copy += " " + message("point_soil", value=round(forecast.soil_moisture_m3_m3 * 100, 1))
            elif soil_requested:
                point_copy += " " + message("point_soil_missing")
        else:
            reason = "weather_gap" if only_missing_metrics or session.crop != "paddy" else "weather"
            explanation = message("point_soil_missing" if soil_requested else reason)
            if topic != WEATHER_TOPIC:
                explanation = (" ".join((crop_gap(), explanation)) if not stage_candidates and not (
                    candidates and session.crop_stage == "unknown") else " ".join((explanation, message("weather_needed"))))
            return result("insufficient_evidence", explanation)
        if topic == WEATHER_TOPIC:
            return support("plan_with_district_forecast", point_copy or message("rain", date=day, amount=amount),
                           weather, weather_rows=weather, amount=amount,
                           weather_copy=message("point_scope" if snapshot else "bulletin_scope"), snapshot=snapshot,
                           status="conditional" if soil_requested and snapshot.soil_moisture_m3_m3 is None else "supported")

    if session.crop_stage == "unknown":
        generic = preferred([row for row in candidates if row["stage_id"] is None])
        specific = [row for row in candidates if row["stage_id"]]
        generic_codes = {row["decision_code"] for row in generic}
        stage_can_change_decision = (generic_codes | {row["decision_code"] for row in specific}) & ACTIONS[topic].keys()
        if stage_can_change_decision and specific and (
            len(generic_codes) != 1 or any(row["decision_code"] not in generic_codes for row in specific)
        ):
            return result("clarification", message("stage_why"), field="crop_stage", follow_up="stage")
    practices = preferred(rank(session.question, stage_candidates))
    if not practices:
        explanation = " ".join((message("weather_available"), crop_gap())) if weather else crop_gap()
        return result("insufficient_evidence", explanation, weather)
    codes = {row["decision_code"] for row in practices}
    supported_codes = codes & ACTIONS[topic].keys()
    if len(supported_codes) > 1:
        return result("conflicting_evidence", message("conflict"), practices)
    if len(codes) != 1 or not supported_codes:
        return result("insufficient_evidence", message("unencoded"), practices)
    code = next(iter(supported_codes))
    action = localize(ACTIONS[topic][code], session.language)
    practice_detail = []
    if code == "harvest_at_maturity" and practices[0]["content"] == REVIEWED_HARVEST_TEXT:
        action = message("harvest_thresholds")
        practice_detail.append(message("paddy_harvest_reason"))
    if code == "maintain_moisture" and session.crop == "paddy" and practices[0]["stage_id"] == "grain-filling":
        practice_detail.append(message("paddy_grain_filling"))
    if code == "okra_harvest_tender":
        practice_detail.append(message("okra_harvest_reason"))
    if code == "okra_moisture_at_fruit_set":
        practice_detail.append(message("okra_moisture_reason"))
    if topic == "irrigation" and needs_weather and code == "maintain_moisture":
        if (session.field_observations or "").casefold() in {text.casefold() for text in UNKNOWN_MOISTURE}:
            return result("insufficient_evidence", message("moisture_unknown"), weather)
        moisture = moisture_observation(session.field_observations)
        if moisture is None:
            return result("clarification", message("observation_why"), field="field_observations",
                          follow_up="observation") | {"follow_up_kind": "soil_moisture"}
        if moisture == "standing":
            action = message("standing")
            code = "avoid_irrigation_while_standing"
            practice_detail.append(message("paddy_standing_reason"))
        else:
            practice_detail.append(message("paddy_no_standing"))

    general_vegetable_practice = code in GENERAL_VEGETABLE_IRRIGATION and needs_weather
    general_okra_harvest = code == "okra_harvest_tender" and needs_weather
    quantity_requested = topic == "irrigation" and has_terms(session.question.casefold(), IRRIGATION_QUANTITY_TERMS)
    if general_vegetable_practice:
        practice_detail.append(message("vegetable_timing_gap"))
    if general_okra_harvest:
        practice_detail.append(message("harvest_timing_gap"))
    if quantity_requested:
        practice_detail.append(message("water_quantity_gap"))
    weather_copy = None
    if weather:
        forecast_description = f'{point_copy} {message("point_scope")}' if point_copy else message("rain", date=day, amount=amount)
        weather_copy = " ".join((forecast_description, message("forecast_field_limit")))
    return support(code, action, practices[:1], practice_rows=practices[:1], weather_rows=weather,
                   amount=amount, practice_copy=" ".join(practice_detail) or None, weather_copy=weather_copy, snapshot=snapshot,
                   status="conditional" if general_vegetable_practice or general_okra_harvest or quantity_requested else "supported")
