// Place labels drawn in screen space (crisp at any zoom), in atlas style: italic serif for water and
// physical regions, spaced small caps for countries, plain sans for cities. Labels appear as you zoom
// in, by importance, and a label is skipped if it would overlap one already placed.
import { SANS, SERIF } from './theme.js';

let labels = []; // {name, kind, lon, lat, rank, x, y, minZoom, priority}

// Zoom level at which a label of a given kind and Natural Earth rank first appears. Zoom here is relative
// to the world filling a desktop screen, so on a phone (a much smaller world) labels wait for more zoom.
function minZoom(kind, rank) {
  switch (kind) {
    case 'ocean': return 0.5;
    case 'sea': return rank <= 2 ? 1.5 : rank <= 4 ? 3 : 6;
    case 'region': return rank <= 2 ? 1.8 : rank <= 4 ? 3.5 : 7;
    case 'country': return rank <= 2 ? 1.2 : rank <= 4 ? 2.2 : rank <= 6 ? 4 : 7;
    case 'city': return rank <= 1 ? 3 : rank <= 3 ? 5 : rank <= 5 ? 8 : 14;
    default: return 99;
  }
}

const STYLE = {
  ocean: { font: `italic 15px ${SERIF}`, spacing: '3px', upper: false },
  sea: { font: `italic 12px ${SERIF}`, spacing: '1px', upper: false },
  region: { font: `italic 11px ${SERIF}`, spacing: '1.5px', upper: true },
  country: { font: `600 11px ${SERIF}`, spacing: '2px', upper: true },
  city: { font: `12px ${SANS}`, spacing: '0px', upper: false },
};
const PRIORITY = { ocean: 0, country: 1, sea: 2, region: 3, city: 4 };

export async function loadLabels() {
  labels = (await fetch('basemap/labels.json').then((r) => r.json())).map((l) => ({
    ...l, minZoom: minZoom(l.kind, l.rank), text: STYLE[l.kind].upper ? l.name.toUpperCase() : l.name,
  }));
  labels.sort((a, b) => PRIORITY[a.kind] - PRIORITY[b.kind] || a.rank - b.rank);
}

export function projectLabels(projection) {
  for (const l of labels) [l.x, l.y] = projection([l.lon, l.lat]) ?? [NaN, NaN];
}

/** screenScale: how big the world is on screen compared with a desktop screen (1 = desktop, ~0.3 = phone). */
export function drawLabels(ctx, transform, t, width, height, screenScale = 1) {
  const placed = [];
  const overlaps = (b) => placed.some((p) => b.x0 < p.x1 && b.x1 > p.x0 && b.y0 < p.y1 && b.y1 > p.y0);
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.lineJoin = 'round';
  for (const l of labels) {
    if (transform.k * screenScale < l.minZoom || Number.isNaN(l.x)) continue;
    const [x, y] = transform.apply([l.x, l.y]);
    if (x < -100 || x > width + 100 || y < -20 || y > height + 20) continue;
    const style = STYLE[l.kind];
    ctx.font = style.font;
    ctx.letterSpacing = style.spacing;
    l.w ??= {};
    const w = (l.w[style.font] ??= ctx.measureText(l.text).width);
    const ty = l.kind === 'city' ? y - 9 : y; // city names sit above their dot
    const box = { x0: x - w / 2 - 3, x1: x + w / 2 + 3, y0: ty - 8, y1: ty + 8 };
    if (overlaps(box)) continue;
    placed.push(box);
    ctx.lineWidth = 3;
    ctx.strokeStyle = t.label.halo;
    if (l.kind === 'city') {
      ctx.fillStyle = t.label.city;
      ctx.beginPath(); ctx.arc(x, y, 1.8, 0, 2 * Math.PI); ctx.fill();
    }
    ctx.strokeText(l.text, x, ty);
    ctx.fillStyle = t.label[l.kind === 'sea' ? 'ocean' : l.kind];
    ctx.fillText(l.text, x, ty);
  }
  ctx.letterSpacing = '0px';
}
