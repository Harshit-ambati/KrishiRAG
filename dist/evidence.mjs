export const weatherPortal = 'https://mausam.imd.gov.in/amaravati/';

export const sources = {
  'imd-87-2026': {
    title: 'Andhra Pradesh Agromet Advisory Service Bulletin No. 87/2026',
    publisher: 'IMD & AMFU Guntur', issued: '2026-10-30',
    url: 'https://mausam.imd.gov.in/visakhapatnam/mcdata/APAgromet.pdf',
  },
  'imd-district-2026-11-02': {
    title: 'District Level Forecast for Andhra Pradesh & Yanam',
    publisher: 'IMD Met Centre Amaravati', issued: '2026-11-02',
    url: 'https://mausam.imd.gov.in/amaravati/mcdata/District_Forecast.pdf',
  },
  'imd-murasu-2026-11-03': {
    title: 'IMD bulletin on Severe Cyclonic Storm Murasu',
    publisher: 'India Meteorological Department', issued: '2026-11-03',
    url: 'https://mausam.imd.gov.in/Forecast/marquee_data/Press%20Release%2003-11-2026.pdf',
  },
};

const pilotDistricts = ['krishna', 'west-godavari'];
const section = {
  krishna: 'Krishna & NTR districts · Rice',
  'west-godavari': 'West Godavari & Eluru districts · Rice',
};

const advisory = {
  kind: 'advisory', approval: 'approved', state: 'andhra-pradesh', districts: pilotDistricts,
  source: 'imd-87-2026', locator: section, crop: 'paddy',
  from: '2026-10-31', through: '2026-11-04', weatherEvent: 'rain',
};

const districtForecast = {
  kind: 'weather', approval: 'approved', state: 'andhra-pradesh', districts: pilotDistricts, events: ['rain'],
  locator: { krishna: 'District rainfall table · Krishna', 'west-godavari': 'District rainfall table · West Godavari' },
};

export const evidence = [
  {
    ...advisory, id: 'amfu-87-rice-drainage', stage: 'reproductive', topic: 'irrigation',
    text: {
      en: 'Keep the field drains clear so excess rainwater can leave the paddy field. This helps prevent prolonged standing water and submergence.',
      hi: 'खेत की नालियाँ साफ रखें ताकि बारिश का अतिरिक्त पानी धान के खेत से निकल सके। इससे खेत में लंबे समय तक पानी भरने और पौधों के डूबे रहने का खतरा कम होता है।',
      te: 'వరి పొలంలో వర్షపు అదనపు నీరు బయటకు వెళ్లేలా కాలువలను శుభ్రంగా ఉంచండి. దీనివల్ల నీరు ఎక్కువసేపు నిల్వ ఉండటం, మొక్కలు మునిగిపోవడం తగ్గుతుంది.',
    },
    limitation: {
      en: 'This advisory covers drainage during rain. The approved evidence leaves irrigation timing and water depth unspecified.',
      hi: 'यह सलाह बारिश के दौरान जल निकासी के लिए है। स्वीकृत स्रोतों में सिंचाई का समय और पानी की गहराई नहीं दी गई है।',
      te: 'ఈ సూచన వర్షం సమయంలో నీటి పారుదలకు సంబంధించినది. ఆమోదించిన ఆధారాల్లో నీరు పెట్టే సమయం, నీటి లోతు పేర్కొనలేదు.',
    },
  },
  {
    ...advisory, id: 'amfu-87-rice-spraying', stage: 'reproductive', topic: 'spraying',
    text: {
      en: 'Wait until the rain has stopped and the rice leaves are dry before taking up any needed crop-protection spraying.',
      hi: 'ज़रूरत होने पर फसल सुरक्षा के लिए छिड़काव तभी करें जब बारिश रुक जाए और धान की पत्तियाँ सूख जाएँ।',
      te: 'పంట రక్షణకు పిచికారీ అవసరమైతే వర్షం ఆగి, వరి ఆకులు ఆరిన తర్వాతే చేయండి.',
    },
  },
  {
    ...advisory, id: 'amfu-87-rice-harvest', stage: 'mature', topic: 'harvest',
    text: {
      en: 'The bulletin advises protecting harvested rice from rain by moving it to a dry, sheltered storage area when conditions allow.',
      hi: 'बुलेटिन के अनुसार, हालात अनुकूल होने पर कटे हुए धान को बारिश से बचाने के लिए सूखी और ढकी जगह पर ले जाएँ।',
      te: 'పరిస్థితులు అనుకూలించినప్పుడు కోసిన వరిని వర్షం నుంచి కాపాడేందుకు పొడిగా, కప్పు ఉన్న నిల్వ ప్రదేశానికి తరలించాలని బులెటిన్ సూచిస్తుంది.',
    },
  },
  {
    ...districtForecast, id: 'imd-district-rain-2026-10-31', source: 'imd-87-2026',
    from: '2026-10-31', through: '2026-10-31',
    text: {
      en: 'Light rain was likely in isolated parts of the district during the forecast period beginning at 8:30 a.m. IST on 31 October.',
      hi: '31 अक्टूबर को सुबह 8:30 बजे (भारतीय समय) से शुरू हुई पूर्वानुमान अवधि में जिले में कहीं-कहीं हल्की बारिश की संभावना थी।',
      te: 'అక్టోబర్ 31 ఉదయం 8:30 (భారత కాలమానం) నుంచి ప్రారంభమైన అంచనా కాలంలో జిల్లాలో అక్కడక్కడా తేలికపాటి వర్షం కురిసే అవకాశం ఉంది.',
    },
  },
  {
    ...districtForecast, id: 'imd-district-rain-2026-11-01', source: 'imd-87-2026',
    from: '2026-11-01', through: '2026-11-01',
    text: {
      en: 'Scattered light to moderate rain or thunderstorms were likely during the forecast period beginning at 8:30 a.m. IST on 1 November.',
      hi: '1 नवंबर को सुबह 8:30 बजे (भारतीय समय) से शुरू हुई पूर्वानुमान अवधि में जिले के कुछ हिस्सों में हल्की से मध्यम बारिश या गरज के साथ बौछारों की संभावना थी।',
      te: 'నవంబర్ 1 ఉదయం 8:30 (భారత కాలమానం) నుంచి ప్రారంభమైన అంచనా కాలంలో జిల్లాలో కొన్ని చోట్ల తేలికపాటి నుంచి మోస్తరు వర్షం లేదా ఉరుములతో కూడిన జల్లులు కురిసే అవకాశం ఉంది.',
    },
  },
  {
    ...districtForecast, id: 'imd-district-rain-2026-11-02', source: 'imd-district-2026-11-02',
    from: '2026-11-02', through: '2026-11-02',
    text: {
      en: 'The district forecast indicated widespread light to moderate rain or thunderstorms for the period beginning at 1:30 p.m. IST on 2 November.',
      hi: '2 नवंबर को दोपहर 1:30 बजे (भारतीय समय) से शुरू हुई अवधि में जिले के कई हिस्सों में हल्की से मध्यम बारिश या गरज के साथ बौछारों की संभावना थी।',
      te: 'నవంబర్ 2 మధ్యాహ్నం 1:30 (భారత కాలమానం) నుంచి ప్రారంభమైన కాలంలో జిల్లా వ్యాప్తంగా తేలికపాటి నుంచి మోస్తరు వర్షం లేదా ఉరుములతో కూడిన జల్లులు కురిసే అవకాశం ఉంది.',
    },
  },
  {
    ...districtForecast, id: 'imd-district-rain-2026-11-03', source: 'imd-district-2026-11-02',
    from: '2026-11-03', through: '2026-11-03',
    text: {
      en: 'The district forecast indicated widespread light to moderate rain or thunderstorms for the forecast period beginning on 3 November.',
      hi: '3 नवंबर से शुरू होने वाली पूर्वानुमान अवधि में जिले के कई हिस्सों में हल्की से मध्यम बारिश या गरज के साथ बौछारों की संभावना थी।',
      te: 'నవంబర్ 3న ప్రారంభమైన అంచనా కాలంలో జిల్లా వ్యాప్తంగా తేలికపాటి నుంచి మోస్తరు వర్షం లేదా ఉరుములతో కూడిన జల్లులు కురిసే అవకాశం ఉందని పేర్కొంది.',
    },
  },
  {
    ...districtForecast, id: 'imd-district-rain-2026-11-04', source: 'imd-district-2026-11-02',
    from: '2026-11-04', through: '2026-11-04',
    text: {
      en: 'Fairly widespread light to moderate rain or thunderstorms were likely during the forecast period beginning at 8:30 a.m. IST on 4 November.',
      hi: '4 नवंबर को सुबह 8:30 बजे (भारतीय समय) से शुरू हुई पूर्वानुमान अवधि में जिले के कई हिस्सों में हल्की से मध्यम बारिश या गरज के साथ बौछारों की संभावना थी।',
      te: 'నవంబర్ 4 ఉదయం 8:30 (భారత కాలమానం) నుంచి ప్రారంభమైన అంచనా కాలంలో జిల్లాలో చాలా చోట్ల తేలికపాటి నుంచి మోస్తరు వర్షం లేదా ఉరుములతో కూడిన జల్లులు కురిసే అవకాశం ఉంది.',
    },
  },
  {
    id: 'imd-murasu-winds-2026-11-03', kind: 'weather', approval: 'approved',
    state: 'andhra-pradesh', districts: pilotDistricts, source: 'imd-murasu-2026-11-03',
    locator: { krishna: 'Wind warnings · Coastal Andhra Pradesh', 'west-godavari': 'Wind warnings · Coastal Andhra Pradesh' },
    from: '2026-11-03', through: '2026-11-03', events: ['severe-wind'],
    text: {
      en: 'The Murasu bulletin also included this district in a gale and squally-wind warning on 3 November.',
      hi: 'मुरासु बुलेटिन ने 3 नवंबर को इस जिले के लिए भी आंधी और तेज़ झोंकों की चेतावनी दी थी।',
      te: 'నవంబర్ 3న మురాసు బులెటిన్ ఈ జిల్లాను తీవ్ర గాలులు, బలమైన ఈదురు గాలుల హెచ్చరికలో చేర్చింది.',
    },
  },
];
