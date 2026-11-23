export const coverage = [
  {
    id: 'andhra-pradesh',
    name: { en: 'Andhra Pradesh', hi: 'आंध्र प्रदेश', te: 'ఆంధ్ర ప్రదేశ్' },
    districts: [
      { id: 'krishna', name: { en: 'Krishna', hi: 'कृष्णा', te: 'కృష్ణా' }, enabled: true },
      { id: 'west-godavari', name: { en: 'West Godavari', hi: 'पश्चिम गोदावरी', te: 'పశ్చిమ గోదావరి' }, enabled: true },
    ],
  },
];

export const crops = { paddy: { en: 'Paddy (rice)', hi: 'धान', te: 'వరి' } };

export const stages = {
  nursery: { en: 'Nursery & transplanting', hi: 'नर्सरी और रोपाई', te: 'నారు మరియు నాట్లు' },
  tillering: { en: 'Tillering', hi: 'कल्ले निकलना', te: 'పిలకలు వేసే దశ' },
  reproductive: { en: 'Booting to milk stage', hi: 'बाली बनने से दूधिया दाने तक', te: 'పొట్ట దశ నుంచి పాల దశ వరకు' },
  mature: { en: 'Mature & ready to harvest', hi: 'पकी फसल, कटाई के लिए तैयार', te: 'పండిన పంట, కోతకు సిద్ధం' },
};

export const topics = {
  irrigation: { en: 'Irrigation & drainage', hi: 'सिंचाई और जल निकासी', te: 'సాగునీరు, మురుగు నీటి పారుదల' },
  spraying: { en: 'Spraying after rain', hi: 'बारिश के बाद छिड़काव', te: 'వర్షం తర్వాత పిచికారీ' },
  harvest: { en: 'Harvest & storage', hi: 'कटाई और भंडारण', te: 'కోత మరియు నిల్వ' },
};

export const example = {
  state: 'andhra-pradesh', district: 'krishna', crop: 'paddy', stage: 'reproductive',
  topic: 'irrigation', date: '2026-11-03',
};
