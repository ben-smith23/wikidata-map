// Hover card: shows the basics at once, then the Wikipedia thumbnail and opening paragraph, fetched
// from Wikipedia's public summary API only for events actually hovered (and cached).
import { dateRange } from './format.js';
import { category } from './theme.js';

const SUMMARY_API = 'https://en.wikipedia.org/api/rest_v1/page/summary/';
const FETCH_DELAY_MS = 120;   // only fetch once the pointer settles on a dot
const MAX_EXTRACT = 320;      // characters

const card = document.getElementById('tooltip');
const summaries = new Map();  // wiki title -> Promise<{extract, image}>
let current = null;           // the event the card shows
let timer = 0;
let anchor = [0, 0];
let sheet = false;            // touch: the card sits along the bottom of the screen, with a link

export const wikiUrl = (e) => `https://en.wikipedia.org/wiki/${encodeURIComponent(e.wiki.replaceAll(' ', '_'))}`;

function summary(title) {
  if (!summaries.has(title)) {
    summaries.set(title, fetch(SUMMARY_API + encodeURIComponent(title.replaceAll(' ', '_')), {
      headers: { 'Api-User-Agent': 'wikidata-map/0.1 (https://github.com/ben-smith23/wikidata-map)' },
    })
      .then((r) => (r.ok ? r.json() : {}))
      .then((s) => ({ extract: s.extract || '', image: s.thumbnail?.source || null }))
      .catch(() => ({ extract: '', image: null })));
  }
  return summaries.get(title);
}

/** Cut at a sentence end before the limit where possible. */
function shorten(text) {
  if (text.length <= MAX_EXTRACT) return text;
  const cut = text.slice(0, MAX_EXTRACT);
  const end = cut.lastIndexOf('. ');
  return end > MAX_EXTRACT / 2 ? cut.slice(0, end + 1) : `${cut.trimEnd()}…`;
}

function place() {
  if (sheet) { card.style.left = card.style.top = ''; return; } // positioned by CSS
  const pad = 14;
  const [x, y] = anchor;
  card.style.left = `${Math.min(x + pad, window.innerWidth - card.offsetWidth - pad)}px`;
  card.style.top = `${Math.max(pad, Math.min(y + pad, window.innerHeight - card.offsetHeight - pad))}px`;
}

function render(e, details) {
  const [, label] = category(e);
  card.innerHTML = '';
  if (details?.image) {
    const img = document.createElement('img');
    img.src = details.image;
    img.alt = '';
    img.addEventListener('load', place);
    card.append(img);
  }
  const name = document.createElement('div');
  name.className = 'name';
  name.textContent = e.name;
  const meta = document.createElement('div');
  meta.className = 'meta';
  meta.textContent = `${dateRange(e)} · ${label}`;
  const text = document.createElement('div');
  text.className = 'text';
  text.textContent = details?.extract ? shorten(details.extract) : e.desc;
  card.append(name, meta, text);
  if (sheet) {
    const link = document.createElement('a');
    link.href = wikiUrl(e);
    link.target = '_blank';
    link.rel = 'noopener';
    link.textContent = 'Read on Wikipedia →';
    card.append(link);
  }
  card.classList.toggle('sheet', sheet);
  card.hidden = false;
  place();
}

/** asSheet: show it as a tappable panel along the bottom (for touch) instead of following the pointer. */
export function showCard(event, clientX, clientY, asSheet = false) {
  anchor = [clientX, clientY];
  if (!event) { hideCard(); return; }
  if (event === current && asSheet === sheet) { place(); return; }
  sheet = asSheet;
  current = event;
  render(event, null);
  clearTimeout(timer);
  timer = setTimeout(() => {
    summary(event.wiki).then((details) => { if (current === event) render(event, details); });
  }, FETCH_DELAY_MS);
}

export function hideCard() {
  clearTimeout(timer);
  current = null;
  card.hidden = true;
}
