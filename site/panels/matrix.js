import { t } from '../i18n.js';
import { state, loadScores, authoritative, fmtScore, benchLabel, modelLabel, bench } from '../data.js';
import { el, esc, sectionHead } from '../ui.js';
import { heatmap } from '../charts.js';

export async function render(root) {
  await loadScores();
  const mx = state.summary.matrix;
  const rows = mx.models;
  const cols = mx.benchmarks;
  const values = mx.values;
  // per-column min-max normalisation (direction-aware)
  const norm = values.map(r => r.slice());
  cols.forEach((bid, x) => {
    const b = bench(bid);
    const col = values.map(r => r[x]).filter(v => v !== null && v !== undefined);
    if (!col.length) return;
    const min = Math.min(...col), max = Math.max(...col);
    values.forEach((r, y) => {
      const v = r[x];
      if (v === null || v === undefined) { norm[y][x] = null; return; }
      let n = max === min ? 1 : (v - min) / (max - min);
      if (b && b.direction === 'lower') n = 1 - n;
      norm[y][x] = n;
    });
  });
  const chartEl = el('div', { class: 'chart' });
  root.append(el('section', { class: 'section' }, sectionHead(t('mx.title'), t('mx.hint')),
    el('div', { class: 'card' }, chartEl)));
  const detail = el('div', { class: 'card' });
  detail.hidden = true;
  root.append(detail);

  requestAnimationFrame(() => heatmap(chartEl, {
    rows: rows.map(modelLabel), cols: cols.map(benchLabel), values, norm,
    labelFor: (x, y, v) => { const b = bench(cols[x]); return fmtScore(v, b.unit, { withUnit: false }); },
    tooltipFor: (x, y, v) => {
      const b = bench(cols[x]);
      const rec = authoritative(rows[y], cols[x]);
      return `<b>${esc(modelLabel(rows[y]))}</b><br>${esc(benchLabel(b))}: <b>${fmtScore(v, b.unit)}</b>` +
        (rec ? `<br><span style="opacity:.75">${esc(t('prov.' + rec.t))}${rec.src ? ' · ' + esc(rec.src) : ''}${rec.v ? ' · ' + esc(rec.v) : ''}</span>` : '');
    },
    onClick: (x, y) => {
      const b = bench(cols[x]);
      const rec = authoritative(rows[y], cols[x]);
      detail.replaceChildren(
        el('h3', { text: t('mx.cell', { model: modelLabel(rows[y]), bench: benchLabel(b) }) }),
        rec ? el('p', {}, el('b', { text: fmtScore(rec.s, b.unit) }), rec.v ? ` (${rec.v})` : '', ' · ',
          rec.url ? el('a', { href: rec.url, target: '_blank', rel: 'noopener', text: `${t('prov.' + rec.t)} · ${rec.src}` }) : el('span', { text: t('prov.' + rec.t) }),
          rec.sc ? ` · ${rec.sc}` : '', rec.d ? ` · ${rec.d}` : '') : null,
        el('p', {}, el('a', { href: '#/models/' + encodeURIComponent(rows[y]), text: t('mx.open_model') }), ' · ',
          el('a', { href: '#/benchmarks/' + encodeURIComponent(cols[x]), text: t('mx.open_bench') })),
      );
      detail.hidden = false;
      detail.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    },
  }));
}
