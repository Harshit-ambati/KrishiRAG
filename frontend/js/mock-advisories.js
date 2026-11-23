const mockRain = {
  en: 'Mock source · District rainfall bulletin',
  te: 'నమూనా మూలం · జిల్లా వర్షపాత బులెటిన్',
  hi: 'नमूना स्रोत · ज़िले का वर्षा बुलेटिन',
};

const mockPaddy = {
  en: 'Mock source · Paddy field operations note',
  te: 'నమూనా మూలం · వరి పొలం పనుల గమనిక',
  hi: 'नमूना स्रोत · धान के खेत में काम की सूचना',
};

export const mockAdvisories = {
  supported: {
    sources: [mockRain, mockPaddy],
    validThrough: '2026-11-04',
    en: {
      action: 'In this example, clear the drainage channels so excess rainwater can leave the field.',
      explanation: 'The sample bulletin forecasts rain, and the sample paddy note covers drainage at this crop stage.',
    },
    te: {
      action: 'ఈ ఉదాహరణలో అదనపు వర్షపు నీరు బయటకు వెళ్లేలా పొలం కాలువలను శుభ్రం చేయండి.',
      explanation: 'నమూనా బులెటిన్ వర్షం పడుతుందని చెబుతోంది. ఈ పంట దశలో నీటి పారుదల గురించి నమూనా వరి గమనికలో ఉంది.',
    },
    hi: {
      action: 'इस उदाहरण में नालियाँ साफ करें ताकि बारिश का अतिरिक्त पानी खेत से निकल सके।',
      explanation: 'नमूना बुलेटिन में बारिश की संभावना है और धान की नमूना सूचना इसी अवस्था में जल निकासी पर लागू होती है।',
    },
  },
  conditional: {
    sources: [mockRain, mockPaddy],
    en: {
      action: 'In this example, wait until rain has stopped and the leaves are dry before any needed spraying.',
      explanation: 'The sample evidence gives conditions for spraying. It cannot confirm whether your field meets them.',
    },
    te: {
      action: 'ఈ ఉదాహరణలో పిచికారీ అవసరమైతే వర్షం ఆగి, ఆకులు ఆరే వరకు వేచి ఉండండి.',
      explanation: 'పిచికారీకి అవసరమైన పరిస్థితులను నమూనా ఆధారాలు చెబుతున్నాయి. మీ పొలంలో ఆ పరిస్థితులు ఉన్నాయో అవి నిర్ధారించలేవు.',
    },
    hi: {
      action: 'इस उदाहरण में ज़रूरी छिड़काव से पहले बारिश रुकने और पत्तियाँ सूखने तक इंतज़ार करें।',
      explanation: 'नमूना स्रोत छिड़काव की शर्तें बताते हैं। उनसे आपके खेत की मौजूदा स्थिति की पुष्टि नहीं हो सकती।',
    },
  },
  clarification: {
    sources: [],
    en: {
      action: 'Tell us whether the paddy is newly transplanted, has started tillering, or has begun forming grain.',
      explanation: 'In this scenario the crop stage is unclear, so there is no field recommendation yet.',
    },
    te: {
      action: 'వరి నాట్లు వేశారా, పిలకలు వస్తున్నాయా, గింజ ఏర్పడటం మొదలైందా అనేది చెప్పండి.',
      explanation: 'ఈ పరిస్థితిలో పంట దశ స్పష్టంగా లేదు. అందువల్ల పొలం పనికి ఇంకా సూచన ఇవ్వలేం.',
    },
    hi: {
      action: 'बताएँ कि धान की रोपाई अभी हुई है, कल्ले निकल रहे हैं या दाने बनने लगे हैं।',
      explanation: 'इस स्थिति में फसल की अवस्था स्पष्ट नहीं है। इसलिए अभी खेत के लिए कोई सलाह नहीं दी गई है।',
    },
  },
  coverageGap: {
    sources: [],
    en: {
      action: 'Check for a current district bulletin or ask your local agricultural extension office.',
      explanation: 'This mock case has no matching district weather evidence for the requested operation.',
    },
    te: {
      action: 'తాజా జిల్లా బులెటిన్ చూడండి లేదా స్థానిక వ్యవసాయ అధికారిని అడగండి.',
      explanation: 'ఈ నమూనాలో అడిగిన పొలం పనికి సరిపోయే జిల్లా వాతావరణ ఆధారం లేదు.',
    },
    hi: {
      action: 'ज़िले का नवीनतम बुलेटिन देखें या स्थानीय कृषि विस्तार कार्यालय से पूछें।',
      explanation: 'इस नमूने में पूछे गए खेत के काम के लिए ज़िले के मौसम का कोई लागू साक्ष्य नहीं है।',
    },
  },
  conflict: {
    sources: [mockPaddy, {
      en: 'Mock source · Local field operations update',
      te: 'నమూనా మూలం · స్థానిక పొలం పనుల తాజా సమాచారం',
      hi: 'नमूना स्रोत · स्थानीय खेत के काम की नई सूचना',
    }],
    en: {
      action: 'Confirm the timing with your local agricultural extension office before acting.',
      explanation: 'The two sample sources give different timings for the same operation, so the demo withholds a recommendation.',
    },
    te: {
      action: 'పని మొదలుపెట్టే ముందు సరైన సమయాన్ని స్థానిక వ్యవసాయ అధికారితో నిర్ధారించుకోండి.',
      explanation: 'ఒకే పనికి రెండు నమూనా మూలాలు వేర్వేరు సమయాలు చెబుతున్నాయి. అందువల్ల ఈ నమూనా నిర్దిష్ట సూచన ఇవ్వదు.',
    },
    hi: {
      action: 'काम करने से पहले स्थानीय कृषि विस्तार कार्यालय से सही समय की पुष्टि करें।',
      explanation: 'दोनों नमूना स्रोत एक ही काम के लिए अलग-अलग समय बताते हैं। इसलिए डेमो कोई निश्चित सलाह नहीं देता।',
    },
  },
};
