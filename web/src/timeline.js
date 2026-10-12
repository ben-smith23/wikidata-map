// Year timeline: a histogram of events over time with a draggable range window.
// The scale is stretched (piecewise linear) so each era gets room: most events are after 1500, and a
// straight scale from 3500 BC would squeeze them into the last few percent of the bar.

const BREAKS = [[-1500, 0], [0, 0.1], [1000, 0.22], [1500, 0.34], [1800, 0.5], [1900, 0.66], [2000, 0.9], [2030, 1]];
const TICKS = [-1500, -1000, -500, 0, 500, 1000, 1500, 1700, 1800, 1900, 1950, 2000];
const BINS = 240;
const HANDLE_GRAB = 7; // px either side of an edge that grabs it

function interpolate(v, from, to) {
  for (let i = 1; i < BREAKS.length; i++) {
    const [a0, b0] = [BREAKS[i - 1][from], BREAKS[i][from]];
    if (v <= b0 || i === BREAKS.length - 1) {
      const f = Math.min(1, Math.max(0, (v - a0) / (b0 - a0)));
      return BREAKS[i - 1][to] + f * (BREAKS[i][to] - BREAKS[i - 1][to]);
    }
  }
  return BREAKS.at(-1)[to];
}
const yearToT = (y) => interpolate(y, 0, 1);
const tToYear = (t) => Math.round(interpolate(t, 1, 0));

export function formatYear(y) {
  return y < 0 ? `${-y} BC` : String(y);
}

/**
 * spans: [[startYear, endYear]] per event. onChange(lo, hi) is called whenever the range changes.
 * Returns { range } with the current [lo, hi].
 */
export function createTimeline(container, spans, onChange, initial = null) {
  const canvas = document.createElement('canvas');
  const readout = document.createElement('div');
  readout.className = 'readout';
  container.append(readout, canvas);
  const ctx = canvas.getContext('2d');
  const full = [Math.min(...spans.map((s) => s[0])), new Date().getFullYear()];
  let range = initial ? [Math.max(full[0], initial[0]), Math.min(full[1], initial[1])] : [...full];

  // histogram of event start years, in scale space so each bar is the same width on screen
  const counts = new Array(BINS).fill(0);
  for (const [y0] of spans) counts[Math.min(BINS - 1, Math.floor(yearToT(y0) * BINS))]++;
  const peak = Math.max(...counts);

  const pad = 14;
  const width = () => canvas.clientWidth - 2 * pad;
  const xOf = (year) => pad + yearToT(year) * width();
  const yearAt = (x) => tToYear((x - pad) / width());

  function visibleCount() {
    return spans.filter(([a, b]) => b >= range[0] && a <= range[1]).length;
  }

  function draw() {
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (canvas.width !== w * dpr || canvas.height !== h * dpr) { canvas.width = w * dpr; canvas.height = h * dpr; }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const css = getComputedStyle(document.documentElement);
    const text = css.getPropertyValue('--text').trim();
    const muted = css.getPropertyValue('--muted').trim();
    const accent = css.getPropertyValue('--accent').trim();
    const barTop = 4, barBottom = h - 18;
    const x0 = xOf(range[0]), x1 = xOf(range[1]);

    // histogram (square-root scaled so quiet eras are still visible)
    const bw = width() / BINS;
    counts.forEach((c, i) => {
      if (!c) return;
      const bh = Math.sqrt(c / peak) * (barBottom - barTop);
      const x = pad + i * bw;
      ctx.fillStyle = x + bw >= x0 && x <= x1 ? accent : muted;
      ctx.globalAlpha = x + bw >= x0 && x <= x1 ? 0.85 : 0.3;
      ctx.fillRect(x, barBottom - bh, Math.max(1, bw - 0.5), bh);
    });
    ctx.globalAlpha = 1;

    // selected window and its handles
    ctx.strokeStyle = accent;
    ctx.lineWidth = 1.5;
    ctx.strokeRect(x0, barTop - 2, Math.max(1, x1 - x0), barBottom - barTop + 4);
    ctx.fillStyle = accent;
    for (const x of [x0, x1]) ctx.fillRect(x - 2, (barTop + barBottom) / 2 - 8, 4, 16);

    // ticks
    ctx.fillStyle = muted;
    ctx.font = '11px system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    for (const y of TICKS) {
      const x = xOf(y);
      ctx.fillRect(x, barBottom + 1, 1, 3);
      ctx.fillText(formatYear(y), x, barBottom + 5);
    }
    readout.textContent = `${formatYear(range[0])} – ${formatYear(range[1])} · ${visibleCount().toLocaleString()} of ${spans.length.toLocaleString()} events`;
    readout.style.color = text;
  }

  function set(lo, hi) {
    lo = Math.max(full[0], Math.min(lo, full[1]));
    hi = Math.max(full[0], Math.min(hi, full[1]));
    if (lo > hi) [lo, hi] = [hi, lo];
    if (lo === range[0] && hi === range[1]) return;
    range = [lo, hi];
    draw();
    onChange(lo, hi);
  }

  // dragging: an edge resizes, inside moves the window (in scale space, so it keeps its on-screen width),
  // anywhere else starts a new selection
  let drag = null;
  canvas.addEventListener('pointerdown', (ev) => {
    const x = ev.offsetX, x0 = xOf(range[0]), x1 = xOf(range[1]);
    if (Math.abs(x - x0) <= HANDLE_GRAB) drag = { mode: 'lo' };
    else if (Math.abs(x - x1) <= HANDLE_GRAB) drag = { mode: 'hi' };
    else if (x > x0 && x < x1) drag = { mode: 'move', start: x, t0: yearToT(range[0]), t1: yearToT(range[1]) };
    else { drag = { mode: 'new', start: x }; set(yearAt(x), yearAt(x)); }
    canvas.setPointerCapture(ev.pointerId);
  });
  canvas.addEventListener('pointermove', (ev) => {
    const x = ev.offsetX;
    if (!drag) {
      const near = [range[0], range[1]].some((y) => Math.abs(x - xOf(y)) <= HANDLE_GRAB);
      canvas.style.cursor = near ? 'ew-resize' : x > xOf(range[0]) && x < xOf(range[1]) ? 'grab' : 'crosshair';
      return;
    }
    if (drag.mode === 'lo') set(yearAt(x), range[1]);
    else if (drag.mode === 'hi') set(range[0], yearAt(x));
    else if (drag.mode === 'new') set(yearAt(drag.start), yearAt(x));
    else {
      const span = drag.t1 - drag.t0;
      const t0 = Math.min(1 - span, Math.max(0, drag.t0 + (x - drag.start) / width()));
      set(tToYear(t0), tToYear(t0 + span));
    }
  });
  canvas.addEventListener('pointerup', () => { drag = null; });
  canvas.addEventListener('dblclick', () => set(...full));
  window.addEventListener('resize', draw);

  draw();
  return { get range() { return range; }, get full() { return full; }, redraw: draw };
}
