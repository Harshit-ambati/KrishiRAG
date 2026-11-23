import config from './coverage.json' with { type: 'json' };

export const { coverage, crops, stages } = config;

export const topics = {
  irrigation: { en: 'Irrigation & drainage', hi: 'सिंचाई और जल निकासी', te: 'సాగునీరు, మురుగు నీటి పారుదల' },
  spraying: { en: 'Spraying after rain', hi: 'बारिश के बाद छिड़काव', te: 'వర్షం తర్వాత పిచికారీ' },
  harvest: { en: 'Harvest & storage', hi: 'कटाई और भंडारण', te: 'కోత మరియు నిల్వ' },
};

export const example = {
  state: 'andhra-pradesh', district: 'krishna', crop: 'paddy', stage: 'reproductive',
  topic: 'irrigation', date: '2026-11-03',
};
