// Data loading, indexing and formatting shared by every panel.
import { t, getLang } from './i18n.js';

const BASE = 'data/';

export const state = {
  scope: 'frontier',           // frontier | all
  catalog: null, summary: null, scores: null, status: null,
  benchById: new Map(), modelById: new Map(),
  byBench: new Map(), byModel: new Map(),
  rankCache: new Map(),
};

export async function fetchJSON(path, opts = {}) {
  const r = await fetch(BASE + path, opts);
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  return r.json();
}

export async function loadCore() {
  const [catalog, summary] = await Promise.all([fetchJSON('catalog.json'), fetchJSON('summary.json')]);
  state.catalog = catalog;
  state.summary = summary;
  state.benchById = new Map(catalog.benchmarks.map(b => [b.id, b]));
  state.modelById = new Map(catalog.models.map(m => [m.id, m]));
}

function push(map, key, value) {
  const arr = map.get(key);
  if (arr) arr.push(value); else map.set(key, [value]);
}

export async function loadScores() {
  if (state.scores) return state.scores;
  const s = await fetchJSON('scores.json');
  const idx = Object.fromEntries(s.cols.map((c, i) => [c, i]));
  const recs = s.rows.map(r => ({
    m: r[idx.m], b: r[idx.b], v: r[idx.v] || '', s: r[idx.s], lo: r[idx.lo], hi: r[idx.hi], d: r[idx.d] || '',
    t: r[idx.t], src: s.srcs[r[idx.src]] || '', url: s.urls[r[idx.url]] || '', sc: r[idx.sc] || '',
    n: s.notes[r[idx.n]] || '', a: r[idx.a] === 1, mb: r[idx.mb] || '', sid: r[idx.sid], raw: r[idx.raw] || '',
  }));
  state.scores = recs;
  state.byBench = new Map();
  state.byModel = new Map();
  for (const r of recs) { push(state.byBench, r.b, r); push(state.byModel, r.m, r); }
  state.rankCache = new Map();
  return recs;
}

export const isExt = id => typeof id === 'string' && id.startsWith('ext:');
export function isFrontier(mid) { const m = state.modelById.get(mid); return !!(m && m.frontier); }
export function bench(id) { return state.benchById.get(id); }
export function model(id) { return state.modelById.get(id); }
export function direction(bid) { const b = bench(bid); return (b && b.direction) || 'higher'; }
export function better(a, b, bid) { return direction(bid) === 'lower' ? a < b : a > b; }

/** Authoritative records of registry models for a benchmark, ranked. */
export function ranking(bid, scope = state.scope) {
  const key = bid + '|' + scope;
  let r = state.rankCache.get(key);
  if (r) return r;
  const dir = direction(bid);
  const list = (state.byBench.get(bid) || [])
    .filter(x => x.a && !isExt(x.m) && (scope === 'all' || isFrontier(x.m)))
    .sort((p, q) => dir === 'lower' ? p.s - q.s : q.s - p.s);
  const rankOf = new Map();
  list.forEach((x, i) => rankOf.set(x.m, i + 1));
  r = { list, rankOf, n: list.length };
  state.rankCache.set(key, r);
  return r;
}

export function authoritative(mid, bid) {
  return (state.byModel.get(mid) || []).find(x => x.b === bid && x.a) || null;
}

/** Rank percentile (0-100) of a model within the frontier set for a benchmark. */
export function percentile(mid, bid) {
  const rec = authoritative(mid, bid);
  if (!rec) return null;
  const others = ranking(bid, 'frontier').list.filter(x => x.m !== mid);
  if (!others.length) return 100;
  const beaten = others.filter(x => better(x.s, rec.s, bid)).length;
  return 100 * (1 - beaten / others.length);
}

// ---------------- formatting ----------------
export function fmtNum(v, digits = 1) {
  if (v === null || v === undefined || Number.isNaN(v)) return '–';
  const abs = Math.abs(v);
  const d = abs >= 1000 ? 0 : digits;
  return v.toLocaleString(getLang() === 'zh' ? 'zh-CN' : 'en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
}

export function fmtScore(v, unit, { withUnit = true } = {}) {
  if (v === null || v === undefined || Number.isNaN(v)) return '–';
  switch (unit) {
    case 'pct': return fmtNum(v, 1) + (withUnit ? '%' : '');
    case 'elo': return fmtNum(v, 0);
    case 'hours':
      if (v < 1) return t('time.min', { n: fmtNum(v * 60, 0) });
      return withUnit ? t('time.h', { n: fmtNum(v, v < 10 ? 2 : 1) }) : fmtNum(v, v < 10 ? 2 : 1);
    default: return fmtNum(v, Math.abs(v) >= 100 ? 0 : 2);
  }
}

export function fmtAxis(v, unit) {
  if (unit === 'pct') return fmtNum(v, 0) + '%';
  if (unit === 'hours') return fmtNum(v, v < 10 ? 1 : 0) + 'h';
  return fmtNum(v, 0);
}

export function fmtCI(rec, unit) {
  if (rec.lo === null || rec.lo === undefined || rec.hi === null || rec.hi === undefined) return '';
  return `${fmtScore(rec.lo, unit, { withUnit: false })} – ${fmtScore(rec.hi, unit, { withUnit: false })}`;
}

export function fmtCST(iso) {
  if (!iso) return '–';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(getLang() === 'zh' ? 'zh-CN' : 'en-GB', {
    timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
  });
}

export function benchLabel(bOrId) {
  const b = typeof bOrId === 'string' ? bench(bOrId) : bOrId;
  if (!b) return String(bOrId);
  return getLang() === 'zh' ? (b.name_zh || b.name) : b.name;
}
export function benchDesc(b) { return getLang() === 'zh' ? (b.description_zh || b.description_en || '') : (b.description_en || ''); }
export function catLabel(cat) {
  const c = state.catalog && state.catalog.categories[cat];
  return c ? (c[getLang()] || c.en) : cat;
}
export function modelLabel(mid) {
  const m = model(mid);
  if (m) return m.name;
  if (isExt(mid)) return mid.split(':').slice(2).join(':');
  return mid;
}
export function unitLabel(unit) { return t('unit.' + unit); }
export function matchedLabel(mb) { return t('mb.' + (mb || 'ext')); }

/** Category order used by radar / sidebars: featured-bearing categories first. */
export function categoryOrder() {
  const order = Object.keys(state.catalog.categories);
  const has = new Set(state.catalog.benchmarks.map(b => b.category));
  return order.filter(c => has.has(c));
}
