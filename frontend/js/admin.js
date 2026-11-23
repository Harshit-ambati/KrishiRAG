const byId = id => document.getElementById(id);
const metadataFields = Array.from(document.querySelectorAll('#review-fields > .field-grid [name], #review-fields > .check [name]'));
const statusText = { draft: 'Draft', approved: 'Published', archived: 'Archived' };
const nullable = new Set(['original_url', 'state_id', 'district_id', 'crop', 'issue_date', 'valid_from', 'valid_until']);
let config;
let sources = [];
let selected;
let dirty = false;
let busy = false;

async function api(path = '', options = {}) {
  const response = await fetch('/api/admin/evidence' + path, {
    ...options,
    cache: 'no-store',
    headers: { 'X-Admin-Request': 'evidence-admin', ...options.headers },
  });
  if (response.ok) return response.json();
  const payload = await response.json().catch(() => ({}));
  const detail = payload.detail;
  const message = Array.isArray(detail) ? detail.map(item => item.loc.slice(1).join(' · ') + ' ' + item.msg).join(' ') : detail;
  throw new Error(message || 'The evidence service could not complete this request.');
}

function jsonRequest(method, body) {
  return { method, body: JSON.stringify(body), headers: { 'Content-Type': 'application/json' } };
}

async function work(message, action) {
  if (busy) return;
  busy = true;
  byId('admin-status').textContent = message;
  byId('admin-error').hidden = true;
  byId('editor').setAttribute('aria-busy', 'true');
  try {
    const success = await action();
    byId('admin-status').textContent = success || '';
  } catch (error) {
    byId('admin-status').textContent = '';
    byId('admin-error').textContent = error.message;
    byId('admin-error').hidden = false;
  } finally {
    busy = false;
    byId('editor').setAttribute('aria-busy', 'false');
  }
}

function setOptions(select, emptyLabel, choices, value = '') {
  select.replaceChildren(new Option(emptyLabel, ''), ...choices.map(({ label, id }) => new Option(label, id)));
  select.value = choices.some(choice => choice.id === value) ? value : '';
}

function readFields(controls) {
  return Object.fromEntries(Array.from(controls, field => {
    let value = field.value.trim();
    if (field.type === 'checkbox') value = field.checked;
    else if (field.type === 'number') value = value ? Number(value) : null;
    else if (!value && nullable.has(field.name)) value = null;
    return [field.name, value];
  }));
}

function fillFields(controls, values) {
  for (const field of controls) {
    if (field.type === 'checkbox') field.checked = Boolean(values[field.name]);
    else if (values[field.name] !== undefined) field.value = values[field.name] ?? '';
  }
}

function districtOptions(control, value) {
  const state = config.coverage.find(item => item.id === byId('source-state').value);
  const districts = (state?.districts ?? []).filter(district => district.enabled);
  setOptions(control, 'No district specified', districts.map(district => ({ id: district.id, label: district.name.en })), value);
}

function officialLink(value, page) {
  try {
    const url = new URL(value);
    if (url.protocol !== 'https:') return null;
    if (page) url.hash = 'page=' + page;
    return url.href;
  } catch {
    return null;
  }
}

function addPassage(passage = {}, expand = false) {
  const row = byId('passage-template').content.firstElementChild.cloneNode(true);
  const summary = row.querySelector('summary');
  const fields = row.querySelectorAll('[name]');
  row.dataset.id = passage.id ?? '';
  row.open = expand;
  fillFields(fields, { ...passage, kind: passage.kind ?? 'background' });
  districtOptions(row.querySelector('[name="district_id"]'), passage.district_id);
  setOptions(row.querySelector('[name="crop"]'), 'No crop specified',
    Object.entries(config.crops).map(([id, names]) => ({ id, label: names.en })), passage.crop);

  const page = passage.page_number ? 'PDF page ' + passage.page_number : 'Passage';
  summary.textContent = [page, passage.section, passage.status === 'approved' ? 'Published' : 'Draft'].filter(Boolean).join(' · ');
  const note = row.querySelector('.extraction-note');
  note.textContent = passage.extraction_note ?? 'Enter a locator and compare the reviewed text with the original.';
  if (passage.extracted_page && passage.extracted_page !== passage.page_number) {
    note.textContent += ' Preview provenance: PDF page ' + passage.extracted_page + '.';
  }
  const preview = row.querySelector('.raw-extraction');
  preview.hidden = passage.extracted_text == null;
  preview.querySelector('pre').textContent = passage.extracted_text || 'No text was extracted from this page.';
  const usePreview = row.querySelector('.use-extraction');
  usePreview.hidden = !passage.extracted_text || selected.status !== 'draft';
  usePreview.addEventListener('click', () => {
    const content = row.querySelector('[name="content"]');
    if (content.value && !window.confirm('Replace the current review text with the machine-extracted preview?')) return;
    content.value = passage.extracted_text;
    row.querySelector('[name="reviewed"]').checked = false;
    dirty = true;
    content.focus();
  });
  const pageLink = officialLink(selected.original_url, passage.page_number);
  if (pageLink && passage.page_number) {
    const link = document.createElement('a');
    link.href = pageLink;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = 'Open the publisher’s page';
    note.append(' ', link);
  }
  byId('passages').append(row);
  return row;
}

function renderSources() {
  const items = sources.map(source => {
    const li = document.createElement('li');
    const button = document.createElement('button');
    const subtext = document.createElement('small');
    button.type = 'button';
    button.className = 'secondary';
    button.textContent = source.title || 'Untitled draft';
    subtext.textContent = [statusText[source.status], source.version, source.issue_date].filter(Boolean).join(' · ');
    button.append(subtext);
    if (source.id === selected?.id) button.setAttribute('aria-current', 'true');
    button.addEventListener('click', () => {
      if (dirty && !window.confirm('Leave this draft without saving your edits?')) return;
      work('Opening source…', async () => showSource(await api('/' + encodeURIComponent(source.id)), true));
    });
    li.append(button);
    return li;
  });
  byId('source-list').replaceChildren(...items);
  setOptions(byId('replacement'), 'No replacement selected', sources
    .filter(source => source.status === 'approved' && source.id !== selected?.id && source.state_id === selected?.state_id)
    .map(source => ({ id: source.id, label: [source.title, source.version].join(' · ') })));
}

function showSource(source, focus = false) {
  selected = source;
  dirty = false;
  byId('editor').hidden = false;
  byId('editor-title').textContent = source.title || 'Untitled source';
  byId('source-status').textContent = statusText[source.status];
  const original = byId('original-link');
  const url = officialLink(source.original_url);
  original.hidden = !url;
  if (url) original.href = url;
  const snapshot = byId('snapshot-link');
  snapshot.hidden = !source.has_snapshot;
  snapshot.href = '/api/admin/evidence/' + encodeURIComponent(source.id) + '/original';
  byId('source-hash').textContent = source.sha256 ? 'SHA-256 ' + source.sha256 : '';
  const replacement = sources.find(item => item.id === source.superseded_by);
  byId('replacement-note').textContent = replacement ? 'Superseded by ' + replacement.title + ' · ' + replacement.version : '';
  byId('replacement-note').hidden = !replacement;
  const isDraft = source.status === 'draft';
  byId('review-fields').disabled = !isDraft;
  byId('draft-actions').hidden = !isDraft;
  byId('add-passage').hidden = !isDraft;
  byId('archive-form').hidden = source.status !== 'approved';
  setOptions(byId('source-state'), 'Choose a state', config.coverage.map(state => ({ id: state.id, label: state.name.en })), source.state_id);
  fillFields(metadataFields, { ...source, language: source.language ?? 'en' });
  byId('passages').replaceChildren();
  source.passages.forEach(passage => addPassage(passage));
  renderSources();
  if (focus) byId('editor-title').focus();
}

function reviewPayload() {
  const passages = Array.from(document.querySelectorAll('#passages > details'), row => ({
    id: row.dataset.id || null,
    ...readFields(row.querySelectorAll('[name]')),
  }));
  for (const passage of passages) passage.language ||= null;
  return { revision: selected.revision, metadata: readFields(metadataFields), passages };
}

byId('source-state').addEventListener('change', () => {
  for (const select of byId('passages').querySelectorAll('[name="district_id"]')) districtOptions(select, select.value);
});
byId('review-form').addEventListener('input', event => {
  dirty = true;
  if (metadataFields.includes(event.target) && event.target.name !== 'source_verified') {
    byId('review-form').elements.source_verified.checked = false;
  }
  const passage = event.target.closest('.passage');
  if (passage && !['reviewed', 'include'].includes(event.target.name)) {
    passage.querySelector('[name="reviewed"]').checked = false;
  }
  if (event.target.id === 'original-url') {
    const url = officialLink(event.target.value);
    byId('original-link').hidden = !url;
    if (url) byId('original-link').href = url;
  }
});
byId('add-passage').addEventListener('click', () => {
  if (busy) return;
  dirty = true;
  addPassage({}, true).querySelector('input').focus();
});

byId('upload-form').addEventListener('submit', event => {
  event.preventDefault();
  if (dirty && !window.confirm('Open a new upload without saving this draft?')) return;
  work('Extracting document pages…', async () => {
    const source = await api('', { method: 'POST', body: new FormData(event.target) });
    sources = await api();
    showSource(source, true);
    event.target.reset();
    return 'Draft uploaded. Open a passage to review its extracted text.';
  });
});

byId('review-form').addEventListener('submit', event => {
  event.preventDefault();
  const publish = event.submitter?.id === 'publish-button';
  work(publish ? 'Publishing selected passages…' : 'Saving draft…', async () => {
    const path = '/' + encodeURIComponent(selected.id);
    const saved = await api(path, jsonRequest('PUT', reviewPayload()));
    showSource(saved);
    const updated = publish ? await api(path + '/publish', jsonRequest('POST', { revision: saved.revision })) : saved;
    sources = await api();
    showSource(updated);
    return publish ? 'Reviewed passages published.' : 'Draft saved.';
  });
});

byId('archive-form').addEventListener('submit', event => {
  event.preventDefault();
  if (!window.confirm('Archive this source and remove its passages from the published evidence lookup?')) return;
  work('Archiving source…', async () => {
    const body = { revision: selected.revision, superseded_by: byId('replacement').value || null };
    const archived = await api('/' + encodeURIComponent(selected.id) + '/archive', jsonRequest('POST', body));
    sources = await api();
    showSource(archived);
    return 'Source archived. The original and its review history are retained.';
  });
});

work('Loading sources…', async () => {
  [config, sources] = await Promise.all([api('/config'), api()]);
  renderSources();
  return sources.length ? '' : 'Upload a source to begin.';
});
