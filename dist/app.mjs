import { coverage, crops, example, stages, topics } from './coverage.mjs';
import { sources, weatherPortal } from './evidence.mjs';
import { retrieve } from './retrieval.mjs';
import { resultCopy } from './result-copy.mjs';

const icons = {
  sprout: '<path d="M12 21v-8m0 3C6 16 3 13 3 7c5 0 8 2 9 6m0 2c0-6 3-9 9-10 0 6-3 10-9 10"/>',
  pin: '<path d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0Z"/><circle cx="12" cy="10" r="2.4"/>',
  sliders: '<path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="2.5" fill="#e9f1e5"/><circle cx="15" cy="17" r="2.5" fill="#e9f1e5"/>',
  book: '<path d="M12 6C9 4 5 4 3 5v13c3-1 6-1 9 1 3-2 6-2 9-1V5c-2-1-6-1-9 1v13"/>',
  check: '<circle cx="12" cy="12" r="9"/><path d="m8 12 2.5 2.5L16 9"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4 4"/>',
};

function setIcon(node) {
  node.innerHTML = `<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[node.dataset.icon]}</svg>`;
}

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function link(text, url) {
  const anchor = element('a', text);
  anchor.href = url;
  anchor.target = '_blank';
  anchor.rel = 'noopener noreferrer';
  return anchor;
}

function formatDate(date, language = 'en') {
  return new Intl.DateTimeFormat(`${language}-IN`, { dateStyle: 'medium', timeZone: 'UTC' })
    .format(new Date(`${date}T00:00:00Z`));
}

function todayInIndia() {
  const parts = new Intl.DateTimeFormat('en-GB', { year: 'numeric', month: '2-digit', day: '2-digit', timeZone: 'Asia/Kolkata' })
    .formatToParts().filter(part => part.type !== 'literal');
  const { year, month, day } = Object.fromEntries(parts.map(part => [part.type, part.value]));
  return `${year}-${month}-${day}`;
}

const form = document.querySelector('#advisory-form');
const fields = form.elements;
const result = document.querySelector('#result');

function selectOptions(select, entries, prompt) {
  const options = entries.map(({ id, name }) => new Option(name.en, id));
  if (prompt) options.unshift(new Option(prompt, '', true, true));
  select.replaceChildren(...options);
  if (prompt) select.options[0].disabled = true;
}

function updateDistricts() {
  const state = coverage.find(entry => entry.id === fields.state.value);
  const districts = state?.districts.filter(entry => entry.enabled) ?? [];
  selectOptions(fields.district, districts, districts.length ? 'Select district' : 'No covered districts');
  fields.district.disabled = !districts.length;
}

function renderLibrary() {
  const library = document.querySelector('#source-library');
  for (const source of Object.values(sources)) {
    const card = element('article', '', 'card source-card');
    card.append(element('small', `${source.publisher} · ${formatDate(source.issued)}`), link(source.title, source.url));
    library.append(card);
  }
}

function renderCoverage() {
  const districts = coverage.flatMap(state => state.districts.filter(district => district.enabled).map(district => ({ state, district })));
  const stateCount = new Set(districts.map(entry => entry.state.id)).size;
  document.querySelector('#coverage-summary').textContent = `${districts.length} ${districts.length === 1 ? 'district' : 'districts'} across ${stateCount} ${stateCount === 1 ? 'state' : 'states'}`;
  document.querySelector('#archive-note').textContent = 'The pilot uses curated bulletins. Coverage varies by crop stage, topic, and date.';
  for (const { state, district } of districts) {
    const item = element('li');
    const icon = element('span');
    icon.dataset.icon = 'check';
    const name = stateCount === 1 ? district.name.en : `${district.name.en}, ${state.name.en}`;
    item.append(icon, name);
    document.querySelector('#district-list').append(item);
  }
  const sampleDistrict = districts.find(entry => entry.state.id === example.state && entry.district.id === example.district);
  document.querySelector('.example-card').hidden = !sampleDistrict || !retrieve({ ...example, language: 'en' }).advice;
  if (sampleDistrict) {
    document.querySelector('#example-description').textContent = `${sampleDistrict.district.name.en} · ${formatDate(example.date)} · Paddy drainage during rain`;
  }
}

function citation(record, district, language) {
  const source = sources[record.source];
  const item = element('li');
  item.append(link(source.title, source.url), ` · ${record.locator[district]} · ${formatDate(source.issued, language)}`);
  return item;
}

function renderResult(request, moveFocus = true) {
  const { state, district, crop, stage, topic, date, language } = request;
  const match = retrieve(request);
  const copy = resultCopy[language];
  const area = coverage.find(entry => entry.id === state);
  const place = area?.districts.find(entry => entry.id === district);
  const archived = date < todayInIndia();
  const context = [place?.name[language], area?.name[language], crops[crop]?.[language], stages[stage]?.[language], topics[topic]?.[language], formatDate(date, language)];
  const body = element('div', '', 'result-body');
  const weather = match.weather ?? [];
  const citations = [match.advice, ...(match.conflicting ?? []), ...weather].filter(Boolean);

  if (match.gap) {
    body.append(element('p', copy[match.gap === 'weather' ? 'weatherGap' : match.gap]));
  } else {
    body.append(element('p', match.advice.text[language]));
    if (match.advice.limitation) body.append(element('p', match.advice.limitation[language]));
  }

  if (weather.length) {
    const list = element('ul');
    list.append(...weather.map(record => element('li', record.text[language])));
    body.append(element('h3', copy.weather), list);
    if (!archived && weather.some(record => record.events.includes('severe-wind'))) body.append(element('p', copy.severe));
  }
  if (citations.length) {
    const list = element('ul', '', 'result-citations');
    const uniqueCitations = new Map(citations.map(record => [`${record.source}:${record.locator[district]}`, record]));
    list.append(...Array.from(uniqueCitations.values(), record => citation(record, district, language)));
    body.append(element('h3', copy.citations), list);
  }
  if (match.gap || !archived) {
    const paragraph = element('p');
    paragraph.append(link(copy.portal, weatherPortal));
    body.append(paragraph);
  }

  result.lang = language;
  result.toggleAttribute('data-gap', Boolean(match.gap));
  result.replaceChildren(
    element('h2', match.gap ? copy.gap : archived ? copy.archive : copy.answer),
    element('p', context.filter(Boolean).join(' · '), 'result-summary'),
    body,
  );
  if (archived && !match.gap) body.prepend(element('p', copy.warning, 'side-note'));
  result.hidden = false;
  if (moveFocus) result.focus();
}

selectOptions(fields.state, coverage.map(({ id, name }) => ({ id, name })));
selectOptions(fields.crop, Object.entries(crops).map(([id, name]) => ({ id, name })));
selectOptions(fields.stage, Object.entries(stages).map(([id, name]) => ({ id, name })), 'Select crop stage');
selectOptions(fields.topic, Object.entries(topics).map(([id, name]) => ({ id, name })));
fields.date.value = todayInIndia();
updateDistricts();
renderCoverage();
renderLibrary();
document.querySelectorAll('[data-icon]').forEach(setIcon);

fields.state.addEventListener('change', updateDistricts);
form.addEventListener('input', event => {
  if (event.target.name === 'language' && !result.hidden) {
    renderResult(Object.fromEntries(new FormData(form)), false);
  } else {
    result.hidden = true;
  }
});
form.addEventListener('submit', event => {
  event.preventDefault();
  renderResult(Object.fromEntries(new FormData(form)));
});
document.querySelector('#example').addEventListener('click', () => {
  fields.state.value = example.state;
  updateDistricts();
  for (const [key, value] of Object.entries(example)) fields[key].value = value;
  form.requestSubmit();
});
document.querySelectorAll('nav a').forEach(anchor => {
  anchor.addEventListener('click', () => {
    document.querySelector('nav .active')?.classList.remove('active');
    anchor.classList.add('active');
  });
});
