// Categories in priority order: an event takes the colour of the first one it has.
export const CATEGORIES = [
  ['war', 'War', '#e4572e'],
  ['attack', 'Attack', '#c33c8a'],
  ['disaster', 'Disaster', '#f3a712'],
  ['politics', 'Politics', '#3a86ff'],
  ['sport', 'Sport', '#2ec4b6'],
  ['entertainment', 'Entertainment', '#ff8fab'],
];
export const OTHER = ['other', 'Other', '#9aa5b1'];

export const SERIF = '"Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif';
export const SANS = 'system-ui, -apple-system, "Segoe UI", sans-serif';

export const THEMES = {
  dark: {
    page: '#0e1116', oceanInner: '#1a2433', oceanOuter: '#0d131c', outline: 'rgba(255,255,255,0.18)',
    land: '#2b313a', halo: 'rgba(120,170,220,0.06)',
    relief: { mode: 'overlay', alpha: 0.45 },
    lake: '#172131', river: 'rgba(110,160,210,0.35)',
    borders: 'rgba(255,255,255,0.16)', states: 'rgba(255,255,255,0.11)',
    dots: { glow: true, alpha: 0.95, outline: [0.04, 0.06, 0.09, 0.75] },
    label: { ocean: 'rgba(140,175,215,0.55)', region: 'rgba(200,185,160,0.55)', country: 'rgba(230,232,235,0.55)',
             city: 'rgba(230,232,235,0.8)', halo: 'rgba(14,17,22,0.85)' },
  },
  light: {
    page: '#f4f1ea', oceanInner: '#dfeaf1', oceanOuter: '#c8d9e4', outline: 'rgba(0,0,0,0.25)',
    land: '#f4efe4', halo: 'rgba(60,100,140,0.07)',
    relief: { mode: 'multiply', alpha: 0.55 },
    lake: '#d3e2ec', river: 'rgba(70,120,170,0.45)',
    borders: 'rgba(0,0,0,0.22)', states: 'rgba(0,0,0,0.15)',
    dots: { glow: false, alpha: 0.9, outline: [1, 1, 1, 0.9] },
    label: { ocean: 'rgba(60,100,140,0.6)', region: 'rgba(120,95,60,0.6)', country: 'rgba(40,45,50,0.55)',
             city: 'rgba(30,34,40,0.85)', halo: 'rgba(250,247,240,0.85)' },
  },
};

// Elections are shown as politics. The pipeline still keeps them separate, for their stricter language cut.
const SHOWN_AS = { election: 'politics' };

export function category(e) {
  const cats = e.cats.map((c) => SHOWN_AS[c] ?? c);
  return CATEGORIES.find(([key]) => cats.includes(key)) ?? OTHER;
}
