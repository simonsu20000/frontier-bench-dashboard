import { t } from '../i18n.js';
import { state, loadScores, ranking, isExt, better, fmtScore, fmtCI, benchLabel, benchDesc, catLabel, modelLabel, model, categoryOrder, unitLabel } from '../data.js';
import { el, esc, sectionHead, provenanceBadge, scopeControl, checkbox, table, td, modelLink, extLink } from '../ui.js';
import { barH, stepLine } from '../charts.js';

let showAll = false;
let showExt = true;

function sidebar(current) {
  const side = el('nav', { class: 'side' });
  const select = el('select', { class: 'side-select', onchange: e => { location.hash = '#/benchmarks/' + encodeURIComponent(e.target.value); } });
  for (const cat of categoryOrder()) {
    const items = state.catalog.benchmarks.filter(b => b.category === cat);
    if (!items.length) continue;
    side.append(el('div', { class: 'cat', text: catLabel(cat) }));
    const group = el('optgroup', { label: catLabel(cat) });
    for (const b of items) {
      const sota = state.summary.sota[b.id];
      side.append(el('a', { href: '#/benchmarks/' + encodeURIComponent(b.id), class: b.id === current ? 'active' : '' },
        el('span', {}, b.featured ? el('span', { class: 'star', text: '★' }) : null, benchLabel(b)),
        el('span', { class: 'n', text: sota ? String(sota.n_models) : '' })));
      const opt = el('option', { value: b.id, text: (b.featured ? '★ ' : '') + benchLabel(b) });
      if (b.id === current) opt.selected = true;
      group.append(opt);
    }
    select.append(group);
  }
  return [select, side];
}

function tooltipFor(rec, b) {
  const parts = [`<b>${esc(modelLabel(rec.m))}</b>${rec.v ? ' <span style="opacity:.7">(' + esc(rec.v) + ')</span>' : ''}`,
    `<b>${fmtScore(rec.s, b.unit)}</b>${fmtCI(rec, b.unit) ? ' <span style="opacity:.7">CI ' + esc(fmtCI(rec, b.unit)) + '</span>' : ''}`,
    `${esc(t('prov.' + rec.t))}${rec.src ? ' · ' + esc(rec.src) : ''}`];
  if (rec.sc) parts.push(esc(rec.sc));
  if (rec.d) parts.push(esc(rec.d));
  return parts.join('<br>');
}

export async function render(root, arg) {
  await loadScores();
  const benches = state.catalog.benchmarks;
  const current = arg && state.benchById.has(arg) ? arg : benches[0].id;
  const b = state.benchById.get(current);
  const [select, side] = sidebar(current);
  const content = el('div');
  root.append(el('div', { class: 'two-col' }, el('div', {}, select, side), content));

  const rerender = () => { content.replaceChildren(); draw(); };

  function draw() {
    const { list } = ranking(b.id, state.scope);
    const allRecs = (state.byBench.get(b.id) || []);
    const extRecs = allRecs.filter(r => r.a && isExt(r.m)).sort((p, q) => b.direction === 'lower' ? p.s - q.s : q.s - p.s);
    const sota = state.summary.sota[b.id];

    // header
    const meta = el('div', { class: 'meta' },
      el('span', { class: 'tag', text: catLabel(b.category) }),
      b.featured ? el('span', { class: 'tag', text: '★ featured' }) : null,
      el('span', { text: `${t('col.score')}: ${unitLabel(b.unit)}${b.direction === 'lower' ? ' ↓' : ''}` }),
      el('span', { text: t('lb.models_n', { n: ranking(b.id, 'all').n }) }),
      b.official_url ? extLink(b.official_url, t('lb.official')) : null,
      b.sources && b.sources.length ? el('span', { text: `${t('lb.sources')}: ${b.sources.join(', ')}` }) : null,
    );
    content.append(el('div', { class: 'bench-head section' }, el('h2', { text: benchLabel(b) }),
      benchDesc(b) ? el('p', { class: 'desc', text: benchDesc(b) }) : null, meta));

    // filter row
    content.append(el('div', { class: 'filters' },
      el('span', { class: 'muted small', text: t('filter.scope') }), scopeControl(rerender),
      checkbox(t('filter.all_records'), showAll, v => { showAll = v; rerender(); }),
      extRecs.length ? checkbox(t('filter.include_ext'), showExt, v => { showExt = v; rerender(); }) : null));

    if (!list.length && !extRecs.length) {
      content.append(el('div', { class: 'card empty', text: t('lb.no_data') }));
      return;
    }

    // top-N chart
    const top = list.slice(0, 15);
    if (top.length) {
      const chartEl = el('div', { class: 'chart' });
      content.append(el('div', { class: 'card' }, el('h3', { text: t('lb.top', { n: top.length }) }), chartEl));
      requestAnimationFrame(() => barH(chartEl, {
        unit: b.unit, max: b.unit === 'pct' ? 100 : null,
        items: top.map(r => ({ label: modelLabel(r.m) + (r.v ? ` (${r.v})` : ''), value: r.s, tooltip: tooltipFor(r, b) })),
      }));
    }

    // frontier over time
    const series = state.summary.frontier_series[b.id];
    if (series && series.length > 1) {
      const chartEl = el('div', { class: 'chart short' });
      content.append(el('div', { class: 'card' }, el('h3', { text: t('lb.frontier_over_time') }), el('p', { class: 'hint', text: t('lb.frontier_hint') }), chartEl));
      requestAnimationFrame(() => stepLine(chartEl, {
        unit: b.unit, name: benchLabel(b),
        points: series.map(p => ({ date: p.date, value: p.score, label: modelLabel(p.model_id),
          tooltip: `<b>${esc(modelLabel(p.model_id))}</b> · ${esc(p.date)}<br><b>${fmtScore(p.score, b.unit)}</b>` })),
      }));
    }

    // table
    const rows = [];
    const bestScore = list.length ? list[0].s : null;
    for (const r of list) {
      const rank = rows.filter(x => !x.classList.contains('alt')).length + 1;
      const m = model(r.m) || {};
      rows.push(el('tr', {},
        td(String(rank), 'rank num'),
        td([modelLink(r.m, modelLabel(r.m)), m.frontier ? el('span', { class: 'tag', text: '★', title: t('sc.frontier') }) : null, r.v ? el('span', { class: 'sub', text: ' ' + r.v }) : null]),
        td(m.org || '', ''),
        td([fmtScore(r.s, b.unit), fmtCI(r, b.unit) ? el('div', { class: 'ci', text: fmtCI(r, b.unit) }) : null], 'num'),
        td(gapCell(r.s, bestScore, b), 'num'),
        td(r.sc || '', 'small'),
        td(provenanceBadge(r)),
        td(r.d || (m.release_date ? '' : ''), 'small nowrap'),
      ));
      if (showAll) {
        for (const alt of allRecs.filter(x => x.m === r.m && !x.a)) {
          rows.push(el('tr', { class: 'alt' }, td('', 'rank'), td([el('span', { class: 'sub', text: '↳ ' + (alt.v || 'default') })]), td(''),
            td(fmtScore(alt.s, b.unit), 'num'), td(gapCell(alt.s, bestScore, b), 'num'), td(alt.sc || '', 'small'), td(provenanceBadge(alt)), td(alt.d || '', 'small nowrap')));
        }
      }
    }
    content.append(el('div', { class: 'card' }, table(
      [t('col.rank'), t('col.model'), t('col.org'), t('col.score'), t('col.gap'), t('col.scaffold'), t('col.provenance'), t('col.eval_date')],
      rows, { classes: ['rank', '', '', 'num', 'num', '', '', ''] })));

    if (showExt && extRecs.length) {
      const extRows = extRecs.map((r, i) => el('tr', { class: 'ext' },
        td(String(i + 1), 'rank num'),
        td([el('span', { class: 'model', text: r.raw }), r.v ? el('span', { class: 'sub', text: ' ' + r.v }) : null]),
        td(r.org || '', ''), td(fmtScore(r.s, b.unit), 'num'), td(r.sc || '', 'small'), td(provenanceBadge(r)), td(r.d || '', 'small nowrap')));
      content.append(el('div', { class: 'card' }, el('h3', { text: t('lb.ext_title') }), el('p', { class: 'hint', text: t('lb.ext_hint') }),
        table([t('col.rank'), t('col.model'), t('col.org'), t('col.score'), t('col.scaffold'), t('col.provenance'), t('col.eval_date')], extRows)));
    }
  }

  function gapCell(score, best, b) {
    if (best === null) return '';
    if (score === best) return el('span', { class: 'gap sota', text: t('sc.sota') });
    const diff = score - best;
    const txt = (diff > 0 ? '+' : '') + fmtScore(diff, b.unit === 'pct' ? 'pct' : b.unit, { withUnit: b.unit === 'pct' });
    return el('span', { class: 'gap ' + (better(score, best, b.id) ? 'pos' : 'neg'), text: txt });
  }

  draw();
}
