// Small DOM helpers. All text goes through textContent — source data is untrusted.
import { t } from './i18n.js';
import { state, fmtCST } from './data.js';

export function el(tag, attrs = {}, ...children) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') n.className = v;
    else if (k === 'text') n.textContent = v;
    else if (k === 'html') n.innerHTML = v;            // only for i18n strings we author
    else if (k.startsWith('on') && typeof v === 'function') n.addEventListener(k.slice(2), v);
    else if (k === 'dataset') Object.assign(n.dataset, v);
    else if (k === 'style' && typeof v === 'object') Object.assign(n.style, v);
    else n.setAttribute(k, v === true ? '' : v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    n.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return n;
}

export function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

export function sectionHead(title, sub) {
  return el('div', { class: 'section-head' }, el('h2', { text: title }), sub ? el('span', { class: 'sub', text: sub }) : null);
}

export function extLink(href, text, cls) {
  if (!href) return el('span', { class: cls, text });
  return el('a', { href, target: '_blank', rel: 'noopener', class: cls, text });
}

/** Provenance badge: dot colour = source type, text = localised type, links to the source. */
export function provenanceBadge(rec, { withName = true } = {}) {
  const label = t('prov.' + rec.t);
  const title = (rec.src ? rec.src + ' · ' : '') + label + (rec.mb ? ' · ' + t('prov.matched', { m: t('mb.' + rec.mb) }) : '');
  const inner = withName && rec.src ? `${label} · ${rec.src}` : label;
  const a = rec.url ? el('a', { href: rec.url, target: '_blank', rel: 'noopener', text: inner }) : el('span', { text: inner });
  return el('span', { class: 'badge ' + rec.t, title }, a);
}

export function statusBadge(src) {
  const cls = src.status === 'ok' && src.stale ? 'status-stale' : 'status-' + src.status;
  const text = src.stale ? `${t('src.status.' + src.status)} · ${t('src.stale')}` : t('src.status.' + src.status);
  return el('span', { class: 'badge ' + cls, text });
}

export function scopeControl(onChange) {
  const mk = (value, label) => el('button', {
    type: 'button', class: state.scope === value ? 'active' : '', text: label,
    onclick: () => { if (state.scope !== value) { state.scope = value; try { localStorage.setItem('fb.scope', value); } catch (_) {} onChange(value); } },
  });
  return el('div', { class: 'seg', role: 'group', 'aria-label': t('filter.scope') },
    mk('frontier', t('filter.frontier')), mk('all', t('filter.all')));
}

export function checkbox(label, checked, onChange) {
  const input = el('input', { type: 'checkbox' });
  input.checked = !!checked;
  input.addEventListener('change', () => onChange(input.checked));
  return el('label', { class: 'check' }, input, el('span', { text: label }));
}

export function table(headers, rows, { classes = [] } = {}) {
  const thead = el('thead', {}, el('tr', {}, headers.map((h, i) => el('th', { class: classes[i] || '', text: h }))));
  const tbody = el('tbody', {}, rows);
  return el('div', { class: 'table-wrap' }, el('table', { class: 'data' }, thead, tbody));
}

export function td(content, cls) {
  return el('td', { class: cls || '' }, content);
}

export function modelLink(mid, label) {
  return el('a', { href: '#/models/' + encodeURIComponent(mid), class: 'model', text: label });
}
export function benchLink(bid, label) {
  return el('a', { href: '#/benchmarks/' + encodeURIComponent(bid), text: label });
}

export function fmtUpdated(iso) { return fmtCST(iso); }
