import { translations } from './translations.js';

const byId = id => document.getElementById(id);
const form = byId('question-form');
const fields = form.elements;
const languageSelect = byId('language');
const scenarioSelect = byId('scenario');
const submit = byId('submit');
const announcement = byId('announcement');
const resultContent = byId('result-content');

const config = await fetch('/api/farm-config')
  .then(response => {
    if (!response.ok) throw new Error('Farm configuration unavailable');
    return response.json();
  })
  .catch(() => null);
const { coverage, crops, stages, crop_stages: cropStages, demo_districts: demoDistricts } = config ?? {
  coverage: [], crops: {}, stages: {}, crop_stages: {}, demo_districts: [],
};
let language = languageSelect.value;
let copy = translations[language];
let validationStarted = false;
let pending = false;
let result;
let requestError;
let failedRequest;
let coverageRequest;
let coverageResult;
let coverageFailed = false;
const feedback = new Map();

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

function renderCrops() {
  const state = selectedState();
  const cropSelect = fields.crop;
  const current = cropSelect.value;
  const vegetables = state?.vegetable_ids ?? [];
  cropSelect.replaceChildren(new Option(state ? copy.noCrop : copy.chooseStateFirst, 'none'));
  if (state) {
    const fieldCrops = document.createElement('optgroup');
    fieldCrops.label = copy.fieldCrops;
    fieldCrops.append(new Option(localName(crops.paddy), 'paddy'));
    cropSelect.append(fieldCrops);
  }
  if (vegetables.length) {
    const group = document.createElement('optgroup');
    group.label = copy.stateVegetables;
    vegetables.map(value => new Option(localName(crops[value]), value))
      .sort((a, b) => a.text.localeCompare(b.text, language))
      .forEach(option => group.append(option));
    cropSelect.append(group);
  }
  cropSelect.value = Array.from(cropSelect.options).some(option => option.value === current) ? current : 'none';
  cropSelect.disabled = pending || !state;
  const note = byId('crop-availability');
  note.hidden = !state;
  note.textContent = vegetables.length ? copy.cultivationNote : copy.cultivationGap;
}

function renderCropStages() {
  setOptions(fields.stage, [
    { value: 'unknown', label: copy.unknownStage },
    ...(cropStages[fields.crop.value] ?? []).map(value => ({ value, label: localName(stages[value]) })),
  ]);
  fields.stage.disabled = pending || fields.crop.value === 'none';
}

function renderDemoAvailability() {
  const available = fields.state.value === 'andhra-pradesh' && demoDistricts.includes(fields.district.value)
    && fields.crop.value === 'paddy';
  byId('scenario-control').hidden = !available;
  if (!available) scenarioSelect.value = '';
}

function renderCoverage() {
  const node = byId('coverage-summary');
  node.hidden = !fields.district.value;
  if (node.hidden) return;
  if (!coverageResult) {
    node.textContent = coverageFailed ? copy.coverageError : copy.coverageLoading;
    return;
  }
  const weather = coverageResult.conflicting_forecasts ? 'weatherConflicting'
    : coverageResult.has_reviewed_forecast ? 'weatherReviewed'
    : coverageResult.live_forecast_configured ? 'weatherLive' : 'weatherUnavailable';
  const rows = [copy[weather]];
  if (fields.crop.value !== 'none') {
    const topics = coverageResult.crop_topics.map(({ topic, status }) =>
      copy.coverageTopics[topic] + (status === 'reviewed' ? '' : ' (' + copy.coverageStatuses[status] + ')'));
    rows.push(topics.length ? copy.coverageGuidance + ' ' + topics.join(' · ') : copy.coverageGap);
  }
  node.replaceChildren(...rows.map(text => {
    const line = document.createElement('p');
    line.textContent = text;
    return line;
  }));
}

async function checkCoverage() {
  coverageRequest?.abort();
  coverageResult = undefined;
  coverageFailed = false;
  renderCoverage();
  if (!fields.district.value) return;
  const request = new AbortController();
  coverageRequest = request;
  const params = new URLSearchParams({
    state_id: fields.state.value, district_id: fields.district.value,
    crop: fields.crop.value, crop_stage: fields.stage.value,
  });
  try {
    const response = await fetch('/api/coverage?' + params, {
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(8000)]),
    });
    if (!response.ok) throw new Error('Coverage unavailable');
    const result = await response.json();
    if (!request.signal.aborted) coverageResult = result;
  } catch {
    if (!request.signal.aborted) coverageFailed = true;
  } finally {
    if (!request.signal.aborted) renderCoverage();
  }
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
  renderCrops();
  renderCropStages();
  setOptions(scenarioSelect, [
    { value: '', label: copy.automatic },
    ...['supported', 'conditional', 'clarification', 'coverageGap', 'conflict'].map(value => ({ value, label: copy.statuses[value] })),
  ]);
  renderDemoAvailability();
  renderCoverage();

  if (validationStarted) validate();
  renderResult();
  if (pending) announce(copy.loadingTitle);
  else if (result) announceResult();
  else announce('');
}

function validate() {
  const state = selectedState();
  const district = districtsFor(state).find(entry => entry.id === fields.district.value);
  const validStage = fields.stage.value === 'unknown' || cropStages[fields.crop.value]?.includes(fields.stage.value);
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
  const details = answer.answer_type === 'information' || fields.crop.value === 'none'
    ? [] : [localName(crops[fields.crop.value]), stageName];
  byId('result-location').textContent = [districtLabel, localName(state.name), ...details].join(' · ');
  byId('result-primary-label').textContent = copy[answer.answer_type === 'information' ? 'directAnswer' : 'action'];
  byId('result-action').textContent = answer.answer ?? answer.suggested_action;
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
  const sourceNumbers = new Map();
  sources.replaceChildren(...answer.evidence.map((source, index) => {
    const item = document.createElement('li');
    item.id = 'advisory-source-' + (index + 1);
    if (source.passage_id) sourceNumbers.set(source.passage_id, index + 1);
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
      const locator = [source.publisher, source.issue_date && copy.issued + ' ' + formattedDate(source.issue_date),
        source.version, source.page_number && copy.page + ' ' + source.page_number, source.section].filter(Boolean);
      if (locator.length) item.append(' · ' + locator.join(' · '));
    } else {
      item.textContent = source.title;
    }
    return item;
  }));
  const claimCitations = byId('claim-citations');
  const claims = answer.claims ?? [];
  claimCitations.hidden = !claims.length;
  claimCitations.setAttribute('aria-label', copy.claimCitations);
  claimCitations.replaceChildren(...claims.map(claim => {
    const item = document.createElement('li');
    const label = claim.kind === 'action' && answer.answer_type === 'information' ? copy.directAnswer : copy.claimNames[claim.kind];
    item.append(label + ' ');
    for (const id of claim.passage_ids) {
      const number = sourceNumbers.get(id);
      if (!number) continue;
      const reference = document.createElement('a');
      reference.href = '#advisory-source-' + number;
      reference.textContent = '[' + number + ']';
      reference.setAttribute('aria-label', copy.sources + ' ' + number);
      item.append(reference, ' ');
    }
    return item;
  }));
  sources.hidden = !answer.evidence.length;
  byId('no-sources').hidden = Boolean(answer.evidence.length);
  byId('validity').hidden = !answer.validity_window;
  renderDate('validity-start', answer.validity_window?.valid_from);
  renderDate('validity-date', answer.validity_window?.valid_until);
  renderFeedback();
}

function formattedDate(value) {
  return new Intl.DateTimeFormat(language + '-IN', { dateStyle: 'medium', timeZone: 'UTC' })
    .format(new Date(value + 'T00:00:00Z'));
}

function renderFeedback() {
  const current = feedback.get(result?.answer.advisory_id);
  for (const button of byId('feedback-actions').querySelectorAll('button')) {
    button.disabled = pending || Boolean(current?.pending);
    button.setAttribute('aria-pressed', String(current?.rating === button.dataset.rating));
  }
  byId('feedback-message').textContent = current?.message ? copy[current.message] : '';
}

byId('feedback-actions').addEventListener('click', async event => {
  const rating = event.target.closest('button')?.dataset.rating;
  if (!rating || !result || pending) return;
  const { advisory_id: advisoryId, session_id: sessionId } = result.answer;
  const saved = feedback.get(advisoryId);
  if (saved?.pending) return;
  const existing = saved?.rating;
  feedback.set(advisoryId, { rating: existing, pending: true, message: 'feedbackSaving' });
  renderFeedback();
  let message = 'feedbackSaved';
  try {
    const response = await fetch('/api/advisories/' + encodeURIComponent(advisoryId) + '/feedback', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, rating }), signal: AbortSignal.timeout(10000),
    });
    if (!response.ok) message = 'feedbackError';
  } catch {
    message = 'feedbackError';
  }
  feedback.set(advisoryId, { rating: message === 'feedbackSaved' ? rating : existing, message });
  if (result) renderFeedback();
});

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
    renderCrops();
    renderCropStages();
  }
  if (event.target === fields.crop) {
    fields.stage.value = 'unknown';
    renderCropStages();
  }
  renderDemoAvailability();
  if ([fields.state, fields.district, fields.crop, fields.stage].includes(event.target)) checkCoverage();
  if ([fields.state, fields.district, fields.crop, fields.question].includes(event.target)) resetSession();
  else if (requestError) {
    clearRequestError();
    renderResult();
  }
  if (validationStarted) validate();
}

for (const field of [fields.state, fields.district, fields.crop, fields.stage]) field.addEventListener('change', fieldChanged);
for (const field of [fields.question, fields.observation]) field.addEventListener('input', fieldChanged);
languageSelect.addEventListener('change', () => {
  failedRequest = undefined;
  renderLanguage();
  if (result && !requestError) {
    requestAdvisory({ session_id: result.answer.session_id, translate_advisory_id: result.answer.advisory_id, language }, result);
  }
});
scenarioSelect.addEventListener('change', resetSession);
byId('answer-follow-up').addEventListener('click', () => {
  const field = result.answer.follow_up_field === 'crop_stage' ? fields.stage : fields.observation;
  field.focus();
});

function setPending(value) {
  pending = value;
  for (const control of [fields.state, fields.question, fields.observation, scenarioSelect, languageSelect]) {
    control.disabled = value;
  }
  fields.crop.disabled = value || !selectedState();
  fields.stage.disabled = value || fields.crop.value === 'none';
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
      signal: AbortSignal.timeout(35000),
    });
    if (response.ok) {
      result = { answer: await response.json(), state, district };
    } else if (payload.translate_advisory_id && response.status === 409) {
      requestError = 'translationChanged';
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
    crop: fields.crop.value,
    question: fields.question.value.trim(),
    demo_scenario: scenarioSelect.value || null,
  };
  requestAdvisory(payload, { state, district });
});

if (!config) requestError = 'configError';
renderLanguage();
if (!config) submit.disabled = true;
