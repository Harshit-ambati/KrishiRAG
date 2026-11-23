import { coverage, stages } from '../../archive/coverage.mjs';
import { mockAdvisories } from './mock-advisories.js';
import { translations } from './translations.js';

const byId = id => document.getElementById(id);
const form = byId('question-form');
const fields = form.elements;
const languageSelect = byId('language');
const scenarioSelect = byId('scenario');
const submit = byId('submit');
const announcement = byId('announcement');
const resultContent = byId('result-content');

let language = languageSelect.value;
let copy = translations[language];
let validationStarted = false;
let loadTimer;
let result;

const selectedState = () => coverage.find(state => state.id === fields.state.value);
const districtsFor = state => state?.districts.filter(district => district.enabled) ?? [];
const localName = names => names[language] ?? names.en;

function setOptions(select, choices, prompt) {
  const selected = select.value;
  const options = choices.map(({ value, label }) => new Option(label, value));
  if (prompt) {
    const placeholder = new Option(prompt, '');
    placeholder.disabled = true;
    options.unshift(placeholder);
  }
  select.replaceChildren(...options);
  select.value = options.some(option => option.value === selected) ? selected : options[0]?.value ?? '';
}

function renderDistricts() {
  const state = selectedState();
  const districts = districtsFor(state);
  const options = districts.map(district => ({
    value: district.id,
    label: district.placeholder ? `${localName(district.name)} (${copy.placeholderDistrict})` : localName(district.name),
  }));
  const prompt = state ? (districts.length ? copy.selectDistrict : copy.noDistricts) : copy.chooseStateFirst;
  setOptions(fields.district, options, prompt);
  fields.district.disabled = !districts.length;
}

function renderLanguage() {
  language = languageSelect.value;
  copy = translations[language];
  document.documentElement.lang = language;
  document.title = `AgriRAG · ${copy.heroTitle}`;
  document.querySelectorAll('[data-text]').forEach(node => { node.textContent = copy[node.dataset.text]; });
  document.querySelectorAll('[data-placeholder]').forEach(node => { node.placeholder = copy[node.dataset.placeholder]; });

  setOptions(fields.state, coverage.map(state => ({ value: state.id, label: localName(state.name) })), copy.selectState);
  renderDistricts();
  setOptions(fields.stage, [
    { value: 'unknown', label: copy.unknownStage },
    ...Object.entries(stages).map(([value, names]) => ({ value, label: localName(names) })),
  ], copy.selectStage);
  setOptions(scenarioSelect, Object.entries(copy.statuses).map(([value, label]) => ({ value, label })));
  fields.crop.value = copy.cropValue;

  if (validationStarted) validate();
  renderResult();
  if (loadTimer !== undefined) announce(copy.loadingTitle);
  else if (result) announceResult();
  else announce('');
}

function validate() {
  const state = selectedState();
  const district = districtsFor(state).find(entry => entry.id === fields.district.value);
  const validStage = fields.stage.value === 'unknown' || Object.hasOwn(stages, fields.stage.value);
  const errors = {
    state: state ? '' : copy.stateError,
    district: state && !district ? (fields.district.disabled ? copy.noDistricts : copy.districtError) : '',
    stage: validStage ? '' : copy.stageError,
    question: fields.question.value.length > fields.question.maxLength ? copy.questionLength : fields.question.value.trim() ? '' : copy.questionError,
    observation: fields.observation.value.length > fields.observation.maxLength ? copy.observationLength : '',
  };

  for (const [field, message] of Object.entries(errors)) {
    const error = byId(`${field}-error`);
    error.textContent = message;
    error.hidden = !message;
    if (message) fields[field].setAttribute('aria-invalid', 'true');
    else fields[field].removeAttribute('aria-invalid');
  }
  return Object.entries(errors).find(([, message]) => message);
}

function announce(message) {
  announcement.textContent = message;
}

function announceResult() {
  announce(`${copy.resultReady} ${copy.statuses[result.scenario]}.`);
}

function renderResult() {
  const loading = loadTimer !== undefined;
  resultContent.setAttribute('aria-busy', String(loading));
  submit.setAttribute('aria-disabled', String(loading));
  byId('submit-label').textContent = loading ? copy.loadingButton : copy.submit;
  byId('result-placeholder').hidden = Boolean(result);
  byId('advisory').hidden = !result;

  if (!result) {
    byId('placeholder-title').textContent = loading ? copy.loadingTitle : copy.emptyTitle;
    byId('placeholder-description').textContent = loading ? copy.loadingDescription : copy.emptyDescription;
    return;
  }

  const example = mockAdvisories[result.scenario];
  const info = example[language];
  const status = byId('result-status');
  status.textContent = copy.statuses[result.scenario];
  status.dataset.status = result.scenario;
  const stageName = result.stage === 'unknown' ? copy.unknownStage : localName(stages[result.stage]);
  const districtName = localName(result.district.name);
  const districtLabel = result.district.placeholder ? `${districtName} (${copy.placeholderDistrict})` : districtName;
  byId('result-location').textContent = [districtLabel, localName(result.state.name), stageName].join(' · ');
  byId('result-action').textContent = info.action;
  byId('result-explanation').textContent = info.explanation;

  const sources = byId('result-sources');
  sources.replaceChildren(...example.sources.map(source => {
    const item = document.createElement('li');
    item.textContent = localName(source);
    return item;
  }));
  sources.hidden = !example.sources.length;
  byId('no-sources').hidden = Boolean(example.sources.length);
  byId('validity').hidden = !example.validThrough;
  const date = byId('validity-date');
  if (example.validThrough) {
    date.dateTime = example.validThrough;
    date.textContent = new Intl.DateTimeFormat(`${language}-IN`, { dateStyle: 'medium', timeZone: 'UTC' })
      .format(new Date(`${example.validThrough}T00:00:00Z`));
  } else {
    date.removeAttribute('datetime');
    date.textContent = '';
  }
}

function clearResult() {
  if (!result && loadTimer === undefined) return;
  clearTimeout(loadTimer);
  loadTimer = undefined;
  result = undefined;
  renderResult();
  announce('');
}

function fieldChanged(event) {
  if (event.target === fields.state) {
    fields.district.value = '';
    renderDistricts();
  }
  clearResult();
  if (validationStarted) validate();
}

for (const field of [fields.state, fields.district, fields.stage]) field.addEventListener('change', fieldChanged);
for (const field of [fields.question, fields.observation]) field.addEventListener('input', fieldChanged);
languageSelect.addEventListener('change', renderLanguage);
scenarioSelect.addEventListener('change', clearResult);

form.addEventListener('submit', event => {
  event.preventDefault();
  if (loadTimer !== undefined) return;
  validationStarted = true;
  const error = validate();
  if (error) {
    const [field, message] = error;
    const control = fields[field].disabled ? fields.state : fields[field];
    if (document.activeElement === control || fields[field].disabled) announce(message);
    control.focus();
    return;
  }

  const state = selectedState();
  const requested = {
    state,
    district: districtsFor(state).find(district => district.id === fields.district.value),
    stage: fields.stage.value,
    scenario: scenarioSelect.value,
  };
  result = undefined;
  loadTimer = setTimeout(() => {
    loadTimer = undefined;
    result = requested;
    renderResult();
    announceResult();
  }, 400);
  renderResult();
  announce(copy.loadingTitle);
});

renderLanguage();
