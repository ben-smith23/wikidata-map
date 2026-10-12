import { geoEqualEarth } from 'd3-geo';
import { quadtree } from 'd3-quadtree';
import { select } from 'd3-selection';
import { zoom, zoomIdentity } from 'd3-zoom';
import { drawBasemap, loadBasemap, projectBasemap } from './basemap.js';
import { createDots } from './dots.js';
import { hideCard, showCard } from './card.js';
import { drawLabels, loadLabels, projectLabels } from './labels.js';
import { CATEGORIES, OTHER, THEMES, category } from './theme.js';
import { createTimeline, yearToT } from './timeline.js';

const PRECISE = new Set(['own', 'site']); // everything else is a region, country or continent
const DOT_RADIUS = 1.6;                   // CSS pixels for a 5-language event, at any zoom
const SHOW_LABELS = true;
// During a gesture the basemap and labels are moved with CSS transforms (done by the GPU compositor)
// and redrawn properly when it ends; on long drags they are also redrawn this often.
const GESTURE_REFRESH_MS = 400;
const ARRIVAL_SECONDS = 1.2; // play mode: how long an event's arrival animation lasts
const MAX_ZOOM = 400; // about street-district scale; the coastline data gets coarse beyond ~50x

const stage = document.getElementById('stage');
const baseCanvas = document.getElementById('base');
const labelCanvas = document.getElementById('labels');
const base = baseCanvas.getContext('2d');
const labelCtx = labelCanvas.getContext('2d');
const dots = createDots(document.getElementById('dots'));
const projection = geoEqualEarth();

let events = [];
let index = quadtree();
let theme = 'dark';
let transform = zoomIdentity;     // the current view
let rendered = zoomIdentity;      // the view the basemap and labels were last drawn for
let renderedAt = 0;
let gesturing = false;
let frame = 0;
let years = [-1e9, 1e9]; // visible year range, set by the timeline
let timeline = null;

/** "-0490-01-01" -> -490 */
function yearOf(iso) {
  return parseInt(iso, 10);
}

function spanOf(e) {
  const start = yearOf(e.date);
  return [start, e.end ? Math.max(start, yearOf(e.end)) : start];
}

/** Dot size grows with fame: 1x at 5 languages, about 2x at 200+. */
function radius(langs) {
  return DOT_RADIUS * (1 + 0.2 * Math.log2(Math.max(1, langs / 5)));
}

function resize() {
  const dpr = window.devicePixelRatio || 1;
  for (const c of stage.querySelectorAll('canvas')) {
    c.width = Math.round(window.innerWidth * dpr);
    c.height = Math.round(window.innerHeight * dpr);
  }
  projection.fitExtent([[20, 20], [window.innerWidth - 20, window.innerHeight - 20]], { type: 'Sphere' });
  projectBasemap(projection);
  projectLabels(projection);
  projectEvents();
}

function projectEvents() {
  const list = [];
  for (const e of events) {
    const [, , color] = category(e);
    const r = radius(e.langs);
    const [y0, y1] = spanOf(e);
    for (const [lon, lat, kind] of e.pts) {
      const xy = projection([lon, lat]);
      if (xy) list.push({ x: xy[0], y: xy[1], r, color, precise: PRECISE.has(kind), y0, y1, t: yearToT(y0), event: e });
    }
  }
  // approximate locations first, then precise ones; bigger (more famous) dots on top
  list.sort((a, b) => a.precise - b.precise || a.r - b.r);
  dots.setDots(list);
  index = quadtree().x((p) => p.x).y((p) => p.y).addAll(list);
}

// ?debug: time each layer of the basemap (forcing the canvas to finish each one, so only for measuring)
const DEBUG = new URLSearchParams(location.search).has('debug');
let marks = [];
function mark(name) {
  if (!DEBUG) return;
  base.getImageData(0, 0, 1, 1);
  marks.push([name, performance.now()]);
}

/** Full redraw of the 2D layers (basemap, labels) for the current view. */
function drawStatic() {
  const t = THEMES[theme];
  const { k } = transform;
  const dpr = window.devicePixelRatio || 1;
  marks = [];
  mark('start');
  base.setTransform(dpr, 0, 0, dpr, 0, 0);
  base.clearRect(0, 0, window.innerWidth, window.innerHeight);
  base.setTransform(dpr * k, 0, 0, dpr * k, dpr * transform.x, dpr * transform.y);
  drawBasemap(base, k, t, mark);
  labelCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
  labelCtx.clearRect(0, 0, window.innerWidth, window.innerHeight);
  if (SHOW_LABELS) drawLabels(labelCtx, transform, t, window.innerWidth, window.innerHeight);
  mark('labels');
  baseCanvas.style.transform = labelCanvas.style.transform = '';
  rendered = transform;
  renderedAt = performance.now();
}

/** Moves the last-drawn basemap and labels to match the current view, without redrawing them. */
function moveStatic() {
  const s = transform.k / rendered.k;
  const css = `translate(${transform.x - rendered.x * s}px, ${transform.y - rendered.y * s}px) scale(${s})`;
  baseCanvas.style.transform = labelCanvas.style.transform = css;
}

function render() {
  if (!gesturing || performance.now() - renderedAt > GESTURE_REFRESH_MS) drawStatic();
  else moveStatic();
  const play = timeline?.playing ? { now: timeline.playhead, flash: timeline.tPerSecond * ARRIVAL_SECONDS } : null;
  dots.draw(transform, THEMES[theme].dots, years, play);
  if (play) requestDraw(); // keep animating arrivals while playing
}

function requestDraw() {
  if (!frame) frame = requestAnimationFrame(() => { frame = 0; render(); });
}

/** The nearest dot within reach of the pointer that is inside the timeline's year range. */
function pointAt(clientX, clientY) {
  const [x, y] = transform.invert([clientX, clientY]);
  const reach = 8 / transform.k;
  let best = null, bestDist = reach * reach;
  index.visit((node, x0, y0, x1, y1) => {
    if (!node.length) {
      for (let p = node; p; p = p.next) {
        const d = (p.data.x - x) ** 2 + (p.data.y - y) ** 2;
        if (d < bestDist && p.data.y1 >= years[0] && p.data.y0 <= years[1]) { best = p.data; bestDist = d; }
      }
    }
    return x0 > x + reach || x1 < x - reach || y0 > y + reach || y1 < y - reach;
  });
  return best;
}

function legend() {
  const ul = document.getElementById('legend');
  for (const [, label, color] of [...CATEGORIES, OTHER]) {
    const li = document.createElement('li');
    li.innerHTML = `<span class="swatch" style="background:${color}"></span>${label}`;
    ul.append(li);
  }
}

async function main() {
  legend();
  resize();
  requestDraw();

  const [eventData] = await Promise.all([
    fetch('events.json').then((r) => r.json()),
    loadBasemap(() => { drawStatic(); }),
    loadLabels(),
  ]);
  events = eventData;
  resize();
  requestDraw();
  // the year range lives in the URL too (?years=1789,1815)
  const params = new URLSearchParams(location.search);
  const initial = params.get('years')?.split(',').map(Number);
  timeline = createTimeline(document.getElementById('timeline'), events.map(spanOf), (lo, hi) => {
    years = [lo, hi];
    hideCard();
    requestDraw();
    if (timeline?.playing) return; // the URL is updated when playback stops
    const q = new URLSearchParams(location.search);
    if (lo === timeline.full[0] && hi === timeline.full[1]) q.delete('years'); else q.set('years', `${lo},${hi}`);
    history.replaceState(null, '', `${q.size ? '?' + q : location.pathname}${location.hash}`);
  }, initial?.length === 2 && initial.every(Number.isFinite) ? initial : null);
  years = timeline.range;

  // The view lives in the URL (#zoom/lon/lat), so any view can be bookmarked or shared.
  const zoomer = zoom()
    .scaleExtent([1, MAX_ZOOM])
    .on('start', () => { gesturing = true; })
    .on('zoom', (ev) => { transform = ev.transform; hideCard(); requestDraw(); })
    .on('end', () => {
      gesturing = false;
      requestDraw();
      const [lon, lat] = projection.invert(transform.invert([window.innerWidth / 2, window.innerHeight / 2]));
      history.replaceState(null, '', `${location.search}#${transform.k.toFixed(2)}/${lon.toFixed(2)}/${lat.toFixed(2)}`);
    });
  select(stage).call(zoomer);
  // views are stored as geography (zoom + centre lon/lat), so they survive the map being re-fitted
  const center = () => projection.invert(transform.invert([window.innerWidth / 2, window.innerHeight / 2]));
  const setView = (k, [lon, lat]) => {
    const [x, y] = projection([lon, lat]);
    select(stage).call(zoomer.transform,
      zoomIdentity.translate(window.innerWidth / 2, window.innerHeight / 2).scale(k).translate(-x, -y));
  };
  const [k, lon, lat] = location.hash.slice(1).split('/').map(Number);
  if (k && Number.isFinite(lon) && Number.isFinite(lat)) setView(k, [lon, lat]);

  stage.addEventListener('mousemove', (ev) => showCard(pointAt(ev.clientX, ev.clientY)?.event, ev.clientX, ev.clientY));
  stage.addEventListener('mouseleave', hideCard);
  stage.addEventListener('click', (ev) => {
    const p = pointAt(ev.clientX, ev.clientY);
    if (p) window.open(`https://en.wikipedia.org/wiki/${encodeURIComponent(p.event.wiki.replaceAll(' ', '_'))}`, '_blank', 'noopener');
  });

  const themeButton = document.getElementById('theme');
  const setTheme = (name) => {
    theme = name;
    document.documentElement.dataset.theme = theme;
    themeButton.textContent = theme === 'dark' ? 'Light' : 'Dark';
    timeline.redraw();
    drawStatic();
    requestDraw();
  };
  themeButton.addEventListener('click', () => setTheme(theme === 'dark' ? 'light' : 'dark'));
  if (new URLSearchParams(location.search).get('theme') === 'light') setTheme('light');

  window.addEventListener('resize', () => {
    const [k0, c0] = [transform.k, center()];
    resize();
    setView(k0, c0); // keep the same place in view when the window changes size
    drawStatic();
    requestDraw();
  });
  if (DEBUG) setTimeout(benchmark, 1500); // let the relief image load first
}

/** ?debug: time a full redraw at several zoom levels, and what a gesture frame costs. */
function benchmark() {
  const saved = transform;
  for (const k of [1, 3, 8]) {
    const totals = {};
    transform = zoomIdentity.translate(window.innerWidth / 2 * (1 - k), window.innerHeight / 2 * (1 - k)).scale(k);
    drawStatic(); // warm-up: builds caches for this zoom level
    for (let i = 0; i < 5; i++) {
      transform = transform.translate(10, 5);
      drawStatic();
      marks.slice(1).forEach(([n, ms], j) => { totals[n] = (totals[n] ?? 0) + (ms - marks[j][1]) / 5; });
    }
    const total = Object.values(totals).reduce((a, b) => a + b, 0);
    console.log(`bench full redraw k=${k}: ` + Object.entries(totals).map(([n, ms]) => `${n} ${ms.toFixed(1)}`).join(' | ') + ` | TOTAL ${total.toFixed(1)} ms`);
  }
  // a gesture frame: move the static layers with CSS and redraw the dots with WebGL
  const gl = document.getElementById('dots').getContext('webgl');
  const pixel = new Uint8Array(4);
  const t0 = performance.now();
  for (let i = 0; i < 20; i++) {
    transform = transform.translate(3, 2).scale(1.01);
    moveStatic();
    dots.draw(transform, THEMES[theme].dots, years);
    gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, pixel); // wait for the GPU
  }
  console.log(`bench gesture frame: ${((performance.now() - t0) / 20).toFixed(2)} ms (dots + CSS move)`);
  transform = saved;
  drawStatic();
  requestDraw();
}

main();
