// Boot, routing, language/theme toggles and near-real-time refresh.
import { t, setLang, getLang, applyStatic } from './i18n.js';
import { state, loadCore, fetchJSON, fmtCST } from './data.js';
import { el } from './ui.js';
import { disposeAll } from './charts.js';
import * as overview from './panels/overview.js';
import * as leaderboards from './panels/leaderboards.js';
import * as scorecard from './panels/scorecard.js';
import * as matrix from './panels/matrix.js';
import * as sources from './panels/sources.js';
import * as radar from './panels/radar.js';

const PANELS = { overview, benchmarks: leaderboards, models: scorecard, matrix, radar, sources };
const main = document.getElementById('main');
const errBox = document.getElementById('js-errors');

window.addEventListener('error', e => { errBox.hidden = false; errBox.textContent += `${e.message} (${e.filename}:${e.lineno})\n`; });
window.addEventListener('unhandledrejection', e => { errBox.hidden = false; errBox.textContent += `${e.reason && e.reason.stack || e.reason}\n`; });

function store(k, v) { try { localStorage.setItem(k, v); } catch (_) {} }
function read(k, d) { try { return localStorage.getItem(k) ?? d; } catch (_) { return d; } }

// ---------- theme ----------
function applyTheme(mode) {
  if (mode === 'light' || mode === 'dark') document.documentElement.dataset.theme = mode;
  else delete document.documentElement.dataset.theme;
  document.getElementById('theme-toggle').textContent = mode === 'dark' ? '☾' : mode === 'light' ? '☀' : '◐';
}
const query = new URLSearchParams(location.search);   // ?theme=light|dark&lang=en overrides (sharing / screenshots)
let themeMode = ['light', 'dark', 'auto'].includes(query.get('theme')) ? query.get('theme') : read('fb.theme', 'auto');
applyTheme(themeMode);
document.getElementById('theme-toggle').addEventListener('click', () => {
  themeMode = themeMode === 'auto' ? 'dark' : themeMode === 'dark' ? 'light' : 'auto';
  store('fb.theme', themeMode);
  applyTheme(themeMode);
  route();
});
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => { if (themeMode === 'auto') route(); });

// ---------- language ----------
setLang(query.get('lang') || read('fb.lang', (navigator.language || 'zh').toLowerCase().startsWith('zh') ? 'zh' : 'en'));
document.getElementById('lang-toggle').addEventListener('click', () => {
  setLang(getLang() === 'zh' ? 'en' : 'zh');
  store('fb.lang', getLang());
  refreshChrome();
  route();
});

state.scope = read('fb.scope', 'frontier') === 'all' ? 'all' : 'frontier';

function refreshChrome() {
  applyStatic(document);
  document.getElementById('lang-toggle').textContent = t('top.lang');
  document.title = getLang() === 'zh' ? 'Frontier Bench · 前沿 AI Benchmark 看板' : 'Frontier Bench · Frontier AI Benchmarks';
  if (state.summary) {
    const u = document.getElementById('updated-at');
    u.textContent = t('top.updated', { t: fmtCST(state.summary.generated_at) });
    u.title = state.summary.generated_at;
  }
  renderBanner();
}

function renderBanner() {
  const banner = document.getElementById('banner');
  if (!state.catalog) return;
  const bad = state.catalog.sources.filter(s => s.status !== 'ok' || s.stale);
  if (!bad.length) { banner.hidden = true; return; }
  const list = bad.map(s => `${s.name} (${s.status !== 'ok' ? t('src.status.' + s.status) : t('src.stale')}${s.upstream_updated_at ? ', ' + s.upstream_updated_at : ''})`).join('; ');
  banner.textContent = t('banner.stale', { list });
  banner.hidden = false;
}

// ---------- routing ----------
function parseHash() {
  const h = (location.hash || '#/overview').replace(/^#\/?/, '');
  const [name, ...rest] = h.split('/');
  return { name: PANELS[name] ? name : 'overview', arg: rest.join('/') ? decodeURIComponent(rest.join('/')) : '' };
}

let renderToken = 0;
async function route() {
  const { name, arg } = parseHash();
  document.querySelectorAll('#nav a').forEach(a => a.classList.toggle('active', a.dataset.route === name));
  const token = ++renderToken;
  disposeAll();
  const container = el('div', { class: 'panel panel-' + name });
  try {
    await PANELS[name].render(container, arg);
  } catch (e) {
    container.append(el('pre', { class: 'empty', text: String(e && e.stack || e) }));
    console.error(e);
  }
  if (token !== renderToken) return;
  main.replaceChildren(container);
  window.scrollTo({ top: 0 });
}
window.addEventListener('hashchange', route);

// ---------- near-real-time refresh ----------
async function pollStatus() {
  try {
    const st = await fetchJSON('status.json', { cache: 'no-store' });
    if (state.summary && st.generated_at && st.generated_at !== state.summary.generated_at) {
      const toast = document.getElementById('toast');
      toast.textContent = t('toast.new_data');
      toast.hidden = false;
      toast.onclick = () => location.reload();
    }
  } catch (_) { /* offline or building; try again later */ }
}

// ---------- boot ----------
(async () => {
  try {
    await loadCore();
  } catch (e) {
    main.replaceChildren(el('pre', { class: 'empty', text: 'Failed to load data: ' + e }));
    return;
  }
  refreshChrome();
  await route();
  setInterval(pollStatus, 10 * 60 * 1000);
})();
