// Base map: ocean, relief, land, lakes, rivers and borders. Geometry is projected once (on load and
// resize) into Path2D objects; each frame only re-draws them under the current zoom transform.
import { geoPath } from 'd3-geo';
import { feature, mesh } from 'topojson-client';
import countries from 'world-atlas/countries-50m.json';

const geo = {
  sphere: { type: 'Sphere' },
  land: feature(countries, countries.objects.land),
  borders: mesh(countries, countries.objects.countries, (a, b) => a !== b),
};
let relief = null; // { image, x_max, y_max }
let shapes = {};
let haloCache = { key: null, canvas: null };

const HALO_SUPERSAMPLE = 2;  // halo bitmap resolution relative to the unzoomed map
const HALO_FADE = [2, 6];    // the coastal halo fades out between these zoom levels

// Rivers and lakes appear as you zoom: Natural Earth rank 0-3 always, then by zoom level.
const RIVER_TIERS = [[0, 3, 1, 0.9], [4, 6, 2.5, 0.6], [7, 99, 5, 0.45]]; // [min rank, max rank, min zoom, width]
const STATES_FADE = [1.5, 3];

function split(fc, lo, hi) {
  return { type: 'FeatureCollection', features: fc.features.filter((f) => f.properties.rank >= lo && f.properties.rank <= hi) };
}

/** Loads the vector layers; the relief image loads in the background and calls onRelief when ready. */
export async function loadBasemap(onRelief) {
  const get = (name) => fetch(`basemap/${name}`).then((r) => r.json());
  const [rivers, lakes, states, reliefMeta] = await Promise.all([get('rivers.json'), get('lakes.json'), get('states.json'), get('relief.json')]);
  geo.lakes = lakes;
  geo.states = states;
  RIVER_TIERS.forEach(([lo, hi], i) => { geo[`rivers${i}`] = split(rivers, lo, hi); });
  const image = new Image();
  image.onload = () => { relief = { image, ...reliefMeta }; onRelief(); };
  image.src = 'basemap/relief.webp';
}

export function projectBasemap(projection) {
  const toPath = geoPath(projection);
  shapes = Object.fromEntries(Object.entries(geo).map(([k, g]) => [k, new Path2D(toPath(g))]));
  shapes.scale = projection.scale();
  shapes.translate = projection.translate();
  haloCache.key = null;
}

/** The coastal halo (wide translucent strokes around all coastlines) is expensive to stroke, so it is
 *  drawn once per theme and window size into an off-screen bitmap that each frame just pastes. */
function haloBitmap(t) {
  const dpr = window.devicePixelRatio || 1;
  const scale = dpr * HALO_SUPERSAMPLE;
  const key = `${t.halo}|${window.innerWidth}x${window.innerHeight}|${scale}`;
  if (haloCache.key !== key) {
    const canvas = document.createElement('canvas');
    canvas.width = window.innerWidth * scale;
    canvas.height = window.innerHeight * scale;
    const c = canvas.getContext('2d');
    c.scale(scale, scale);
    c.strokeStyle = t.halo;
    c.lineJoin = 'round';
    for (const w of [7, 4, 2]) { c.lineWidth = w; c.stroke(shapes.land); }
    haloCache = { key, canvas };
  }
  return haloCache.canvas;
}

export function drawBasemap(ctx, k, t, mark = () => {}) {
  if (!shapes.sphere) return;
  const [tx, ty] = shapes.translate;
  const s = shapes.scale;

  // ocean: a gentle radial gradient
  const ocean = ctx.createRadialGradient(tx, ty, 0, tx, ty, s * 2.8);
  ocean.addColorStop(0, t.oceanInner);
  ocean.addColorStop(1, t.oceanOuter);
  ctx.fillStyle = ocean;
  ctx.fill(shapes.sphere);
  mark('ocean');

  // coastal halo: a soft glow off the coast, cached as a bitmap; it fades out when zoomed in
  const haloAlpha = Math.min(1, Math.max(0, (HALO_FADE[1] - k) / (HALO_FADE[1] - HALO_FADE[0])));
  if (haloAlpha > 0) {
    ctx.globalAlpha = haloAlpha;
    ctx.drawImage(haloBitmap(t), 0, 0, window.innerWidth, window.innerHeight);
    ctx.globalAlpha = 1;
  }
  mark('halo');

  ctx.fillStyle = t.land;
  ctx.fill(shapes.land);
  mark('land');

  // shaded relief, clipped to land
  if (relief) {
    ctx.save();
    ctx.clip(shapes.land);
    ctx.globalCompositeOperation = t.relief.mode;
    ctx.globalAlpha = t.relief.alpha;
    ctx.drawImage(relief.image, tx - s * relief.x_max, ty - s * relief.y_max, 2 * s * relief.x_max, 2 * s * relief.y_max);
    ctx.restore();
  }
  mark('relief');

  if (shapes.lakes) { ctx.fillStyle = t.lake; ctx.fill(shapes.lakes); }
  RIVER_TIERS.forEach(([, , minZoom, width], i) => {
    const p = shapes[`rivers${i}`];
    if (!p || k < minZoom) return;
    ctx.globalAlpha = minZoom <= 1 ? 1 : Math.min(1, (k - minZoom) / minZoom); // fade in over the next doubling
    ctx.lineWidth = width / k;
    ctx.strokeStyle = t.river;
    ctx.stroke(p);
  });
  ctx.globalAlpha = 1;
  mark('water');

  if (shapes.states && k > STATES_FADE[0]) {
    ctx.globalAlpha = Math.min(1, (k - STATES_FADE[0]) / (STATES_FADE[1] - STATES_FADE[0]));
    ctx.lineWidth = 0.5 / k; ctx.strokeStyle = t.states; ctx.stroke(shapes.states);
    ctx.globalAlpha = 1;
  }
  ctx.lineWidth = 0.7 / k; ctx.strokeStyle = t.borders; ctx.stroke(shapes.borders);
  ctx.lineWidth = 1 / k; ctx.strokeStyle = t.outline; ctx.stroke(shapes.sphere);
  mark('borders');
}
