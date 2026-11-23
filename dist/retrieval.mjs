import { coverage, crops, stages, topics } from './coverage.mjs';
import { evidence, sources } from './evidence.mjs';

export function isDate(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(date.valueOf()) && date.toISOString().slice(0, 10) === value;
}

export function retrieve(request, records = evidence) {
  const { state, district, crop, stage, topic, date, language } = request;
  const area = coverage.find(entry => entry.id === state);
  if (!area?.districts.some(entry => entry.id === district && entry.enabled)) return { gap: 'district' };
  if (!Object.hasOwn(crops, crop) || !Object.hasOwn(stages, stage) || !Object.hasOwn(topics, topic) ||
      !isDate(date) || !['en', 'hi', 'te'].includes(language)) return { gap: 'selection' };

  const local = records.filter(record => {
    const source = Object.hasOwn(sources, record.source) && sources[record.source];
    return record.approval === 'approved' && record.state === state && record.districts.includes(district) &&
      source && isDate(source.issued) && source.issued <= date && isDate(record.from) && isDate(record.through) &&
      record.text[language]?.trim() && record.locator[district];
  });
  const scoped = local.filter(record => record.kind === 'advisory' && record.crop === crop && record.stage === stage && record.topic === topic);
  if (!scoped.length) return { gap: 'advisory' };

  const applies = record => record.from <= date && record.through >= date;
  const advice = scoped.filter(applies);
  const weather = local.filter(record => record.kind === 'weather' && applies(record));
  if (!advice.length) return { gap: 'date', weather };
  if (!weather.length) return { gap: 'weather' };

  const events = new Set(weather.flatMap(record => record.events));
  const applicable = advice.filter(record => events.has(record.weatherEvent));
  if (!applicable.length) return { gap: 'conditions', weather };

  const latest = applicable.map(record => sources[record.source].issued).sort().at(-1);
  const newest = applicable.filter(record => sources[record.source].issued === latest);
  if (new Set(newest.map(record => record.text[language])).size > 1) {
    return { gap: 'conflict', conflicting: newest, weather };
  }
  return { advice: newest[0], weather };
}
