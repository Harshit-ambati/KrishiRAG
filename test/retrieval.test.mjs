import assert from 'node:assert/strict';
import { test } from 'node:test';
import { example } from '../dist/coverage.mjs';
import { evidence } from '../dist/evidence.mjs';
import { isDate, retrieve } from '../dist/retrieval.mjs';

const query = { ...example, language: 'en' };

test('both pilot districts retrieve the same scoped record in all three languages', () => {
  for (const district of ['krishna', 'west-godavari']) {
    for (const language of ['en', 'hi', 'te']) {
      const result = retrieve({ ...query, district, language });
      assert.equal(result.advice.id, 'amfu-87-rice-drainage');
      assert.ok(result.advice.text[language]);
      assert.equal(result.weather.length, 2);
      assert.ok(result.advice.locator[district]);
    }
  }
});

test('validity is inclusive and expired or unrelated evidence is withheld', () => {
  assert.ok(retrieve({ ...query, date: '2026-10-31' }).advice);
  assert.ok(retrieve({ ...query, date: '2026-11-04' }).advice);
  assert.equal(retrieve({ ...query, date: '2026-11-05' }).gap, 'date');
  assert.equal(retrieve({ ...query, stage: 'nursery' }).gap, 'advisory');
  assert.equal(retrieve({ ...query, district: 'eluru' }).gap, 'district');
  assert.equal(retrieve({ ...query, state: 'telangana' }).gap, 'district');
  assert.equal(retrieve({ ...query, crop: 'maize' }).gap, 'selection');
  assert.equal(retrieve({ ...query, topic: 'harvest' }).gap, 'advisory');
  assert.ok(retrieve({ ...query, stage: 'mature', topic: 'harvest' }).advice);
  assert.ok(retrieve({ ...query, topic: 'spraying' }).advice);
});

test('weather, approval, publication date and translations are required', () => {
  const onlyAdvisories = evidence.filter(record => record.kind === 'advisory');
  assert.equal(retrieve(query, onlyAdvisories).gap, 'weather');
  assert.equal(retrieve(query, evidence.filter(record => !record.events?.includes('rain'))).gap, 'conditions');
  const draft = evidence.map(record => record.kind === 'advisory' ? { ...record, approval: 'draft' } : record);
  assert.equal(retrieve(query, draft).gap, 'advisory');
  const future = evidence.map(record => record.kind === 'advisory' ? { ...record, source: 'imd-murasu-2026-11-03' } : record);
  assert.equal(retrieve({ ...query, date: '2026-11-02' }, future).gap, 'advisory');
  const missingTelugu = evidence.map(record => record.kind === 'advisory' ? { ...record, text: { en: record.text.en } } : record);
  assert.equal(retrieve({ ...query, language: 'te' }, missingTelugu).gap, 'advisory');
});

test('conflicting latest records cause abstention', () => {
  const { advice } = retrieve(query);
  const contradictory = { ...advice, id: 'test-conflict', text: { ...advice.text, en: 'Conflicting advice' } };
  const match = retrieve(query, [...evidence, contradictory]);
  assert.equal(match.gap, 'conflict');
  assert.equal(match.conflicting.length, 2);
});

test('invalid calendar dates cannot match', () => {
  assert.equal(isDate('2026-02-29'), false);
  assert.equal(isDate('2028-02-29'), true);
  assert.equal(retrieve({ ...query, date: '2026-11-31' }).gap, 'selection');
});
