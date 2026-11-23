import { coverage, stages } from '../../archive/coverage.mjs';
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
let pending = false;
let result;
let requestError;
let failedRequest;

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
  announcement.lang = language;
  document.title = `AgriRAG · ${copy.heroTitle}`;
  document.querySelectorAll('[data-text]').forEach(node => { node.textContent = copy[node.dataset.text]; });
  document.querySelectorAll('[data-placeholder]').forEach(node => { node.placeholder = copy[node.dataset.placeholder]; });

  setOptions(fields.state, coverage.map(state => ({ value: state.id, label: localName(state.name) })), copy.selectState);
  renderDistricts();
  setOptions(fields.stage, [
    { value: 'unknown', label: copy.unknownStage },
    ...Object.entries(stages).map(([value, names]) => ({ value, label: localName(names) })),
  ], copy.selectStage);
  setOptions(scenarioSelect, [
    { value: '', label: copy.automatic },
    ...['supported', 'conditional', 'clarification', 'coverageGap', 'conflict'].map(value => ({ value, label: copy.statuses[value] })),
  ]);
  fields.crop.value = copy.cropValue;

  if (validationStarted) validate();
  renderResult();
  if (pending) announce(copy.loadingTitle);
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
  const answerCopy = translations[result.answer.language];
  announcement.lang = result.answer.language;
  announce(`${answerCopy.resultReady} ${answerCopy.statuses[result.answer.status]}. ${result.answer.follow_up_question ?? ''}`.trim());
}

function renderResult() {
  resultContent.setAttribute('aria-busy', String(pending));
  submit.setAttribute('aria-disabled', String(pending));
  const buttonLabel = pending ? 'loadingButton' : requestError ? 'retry' : result?.answer.follow_up_field ? 'submitFollowUp' : 'submit';
  byId('submit-label').textContent = copy[buttonLabel];
  const error = byId('request-error');
  error.hidden = !requestError;
  error.textContent = requestError ? copy[requestError] : '';
  byId('result-placeholder').hidden = Boolean(result);
  byId('advisory').hidden = !result;
  byId('demo-badge').hidden = !(result ? result.answer.is_demo : scenarioSelect.value);

  if (!result) {
    byId('placeholder-title').textContent = pending ? copy.loadingTitle : copy.emptyTitle;
    byId('placeholder-description').textContent = pending ? copy.loadingDescription : copy.emptyDescription;
    return;
  }

  const { answer, state, district } = result;
  const answerCopy = translations[answer.language];
  const status = byId('result-status');
  status.textContent = answerCopy.statuses[answer.status];
  status.dataset.status = answer.status;
  const stageName = answer.crop_stage === 'unknown' ? copy.unknownStage : localName(stages[answer.crop_stage]);
  const districtName = localName(district.name);
  const districtLabel = district.placeholder ? `${districtName} (${copy.placeholderDistrict})` : districtName;
  byId('result-location').textContent = [districtLabel, localName(state.name), stageName].join(' · ');
  byId('result-action').textContent = answer.suggested_action;
  byId('result-explanation').textContent = answer.explanation;
  byId('follow-up').hidden = !answer.follow_up_question;
  byId('answer-follow-up').disabled = pending;
  byId('result-follow-up').textContent = answer.follow_up_question ?? '';
  byId('result-requested-date').hidden = !answer.requested_date;
  renderDate('advisory-date', answer.requested_date);
  for (const id of ['result-status', 'result-action', 'result-explanation', 'result-follow-up', 'result-sources']) {
    byId(id).lang = answer.language;
  }

  const sources = byId('result-sources');
  sources.replaceChildren(...answer.evidence.map(source => {
    const item = document.createElement('li');
    item.lang = source.language === 'mul' ? '' : source.language ?? answer.language;
    if (source.original_url?.startsWith('https://')) {
      const link = document.createElement('a');
      const url = new URL(source.original_url);
      if (source.page_number) url.hash = 'page=' + source.page_number;
      link.href = url.href;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.textContent = source.title;
      item.append(link);
      const locator = [source.publisher, source.version, source.page_number && copy.page + ' ' + source.page_number, source.section].filter(Boolean);
      if (locator.length) item.append(' · ' + locator.join(' · '));
    } else {
      item.textContent = source.title;
    }
    return item;
  }));
  sources.hidden = !answer.evidence.length;
  byId('no-sources').hidden = Boolean(answer.evidence.length);
  byId('validity').hidden = !answer.validity_window;
  renderDate('validity-start', answer.validity_window?.valid_from);
  renderDate('validity-date', answer.validity_window?.valid_until);
}

function renderDate(id, value) {
  const date = byId(id);
  if (!value) {
    date.removeAttribute('datetime');
    date.textContent = '';
    return;
  }
  date.dateTime = value;
  date.textContent = new Intl.DateTimeFormat(`${language}-IN`, { dateStyle: 'medium', timeZone: 'UTC' })
    .format(new Date(`${value}T00:00:00Z`));
}

function clearRequestError() {
  requestError = undefined;
  failedRequest = undefined;
}

function resetSession() {
  result = undefined;
  clearRequestError();
  renderResult();
  announce('');
}

function fieldChanged(event) {
  if (event.target === fields.state) {
    fields.district.value = '';
    renderDistricts();
  }
  if ([fields.state, fields.district, fields.question].includes(event.target)) resetSession();
  else if (requestError) {
    clearRequestError();
    renderResult();
  }
  if (validationStarted) validate();
}

for (const field of [fields.state, fields.district, fields.stage]) field.addEventListener('change', fieldChanged);
for (const field of [fields.question, fields.observation]) field.addEventListener('input', fieldChanged);
languageSelect.addEventListener('change', () => {
  failedRequest = undefined;
  renderLanguage();
  if (result && !requestError) {
    requestAdvisory({ session_id: result.answer.session_id, language }, result);
  }
});
scenarioSelect.addEventListener('change', resetSession);
byId('answer-follow-up').addEventListener('click', () => {
  const field = result.answer.follow_up_field === 'crop_stage' ? fields.stage : fields.observation;
  field.focus();
});

function setPending(value) {
  pending = value;
  for (const control of [fields.state, fields.stage, fields.question, fields.observation, scenarioSelect, languageSelect]) {
    control.disabled = value;
  }
  fields.district.disabled = value || !districtsFor(selectedState()).length;
}

function requestKey() {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
}

async function requestAdvisory(payload, { state, district }, key = requestKey()) {
  clearRequestError();
  setPending(true);
  renderResult();
  announcement.lang = language;
  announce(copy.loadingTitle);

  try {
    const response = await fetch('/api/advisories', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key },
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(15000),
    });
    if (response.ok) {
      result = { answer: await response.json(), state, district };
    } else if (payload.session_id && [404, 409].includes(response.status)) {
      result = undefined;
      requestError = 'sessionError';
    } else if (response.status === 422) {
      requestError = 'invalidRequest';
    } else {
      requestError = 'requestError';
      if (response.status !== 409) failedRequest = { payload, state, district, key };
    }
  } catch {
    requestError = 'requestError';
    failedRequest = { payload, state, district, key };
  } finally {
    setPending(false);
    renderResult();
    if (requestError) announce('');
    else announceResult();
  }
}

form.addEventListener('submit', event => {
  event.preventDefault();
  if (pending) return;
  validationStarted = true;
  const error = validate();
  if (error) {
    const [field, message] = error;
    const control = fields[field].disabled ? fields.state : fields[field];
    if (document.activeElement === control || fields[field].disabled) announce(message);
    control.focus();
    return;
  }

  if (failedRequest) {
    requestAdvisory(failedRequest.payload, failedRequest, failedRequest.key);
    return;
  }

  const state = selectedState();
  const district = districtsFor(state).find(entry => entry.id === fields.district.value);
  const updates = {
    crop_stage: fields.stage.value,
    field_observations: fields.observation.value.trim() || null,
    language,
  };
  const payload = result ? { ...updates, session_id: result.answer.session_id } : {
    ...updates,
    state_id: state.id,
    district_id: district.id,
    crop: 'paddy',
    question: fields.question.value.trim(),
    demo_scenario: scenarioSelect.value || null,
  };
  requestAdvisory(payload, { state, district });
});

renderLanguage();
