import { t } from '../i18n.js';
import { state, loadScores, ranking, authoritative, percentile, isExt, fmtScore, fmtCI, fmtNum, benchLabel, catLabel, modelLabel, model, categoryOrder, unitLabel, better } from '../data.js';
import { el, esc, sectionHead, provenanceBadge, checkbox, table, td, benchLink } from '../ui.js';
import { radar } from '../charts.js';

const MAX = 3;
let featuredOnly = false;

function parseIds(arg) {
  return (arg || '').split(',').map(s => s.trim()).filter(s => s && state.modelById.has(s) && !isExt(s)).slice(0, MAX);
}

function setIds(ids) { location.hash = '#/models/' + ids.map(encodeURIComponent).join(','); }

function picker(ids) {
  const wrap = el('div', { class: 'search' });
  const input = el('input', { type: 'search', placeholder: t('sc.search_placeholder'), autocomplete: 'off', 'aria-label': t('sc.search_placeholder') });
  const results = el('div', { class: 'results' });
  results.hidden = true;
  const models = state.catalog.models.filter(m => !m.ext);
  let focus = -1;
  const show = q => {
    const query = q.trim().toLowerCase();
    results.replaceChildren();
    if (!query) { results.hidden = true; return; }
    const hits = models.filter(m => m.name.toLowerCase().includes(query) || (m.org || '').toLowerCase().includes(query)).slice(0, 12);
    for (const m of hits) {
      results.append(el('button', { type: 'button', onclick: () => { add(m.id); } },
        el('span', { text: m.name }), el('span', { class: 'org', text: `${m.org || ''}${m.release_date ? ' · ' + m.release_date : ''}${m.eci ? ' · ECI ' + fmtNum(m.eci, 0) : ''}` })));
    }
    focus = -1;
    results.hidden = !hits.length;
  };
  const add = id => {
    if (ids.includes(id)) return;
    const next = ids.length >= MAX ? [...ids.slice(1), id] : [...ids, id];
    setIds(next);
  };
  input.addEventListener('input', () => show(input.value));
  input.addEventListener('keydown', e => {
    const btns = [...results.querySelectorAll('button')];
    if (e.key === 'ArrowDown') { focus = Math.min(btns.length - 1, focus + 1); btns.forEach((b, i) => b.classList.toggle('focus', i === focus)); e.preventDefault(); }
    else if (e.key === 'ArrowUp') { focus = Math.max(0, focus - 1); btns.forEach((b, i) => b.classList.toggle('focus', i === focus)); e.preventDefault(); }
    else if (e.key === 'Enter') { (btns[focus] || btns[0])?.click(); }
    else if (e.key === 'Escape') { results.hidden = true; }
  });
  document.addEventListener('click', e => { if (!wrap.contains(e.target)) results.hidden = true; });
  wrap.append(input, results);
  return wrap;
}

function headerCard(m, i, nScores) {
  const eci = m.eci !== null && m.eci !== undefined;
  return el('div', { class: `card model-card c${i + 1}` },
    el('h3', { text: m.name }),
    el('div', { class: 'muted small', text: [m.org, m.country].filter(Boolean).join(' · ') }),
    el('div', { class: 'eci' }, eci ? [fmtNum(m.eci, 1), el('small', { text: `${t('sc.eci')} · 95% CI ${fmtNum(m.eci_lo, 1)}–${fmtNum(m.eci_hi, 1)}` })] : el('small', { text: `${t('sc.eci')}: ${t('sc.eci_none')}` })),
    el('div', { class: 'kv' },
      el('span', { text: t('sc.release') }), el('b', { text: m.release_date || '–' }),
      el('span', { text: t('sc.access') }), el('b', { text: m.accessibility || '–' }),
      el('span', { text: t('sc.n_scores') }), el('b', { text: String(nScores) }),
      el('span', { text: t('sc.frontier') }), el('b', { text: m.frontier ? '★' : '–' })),
  );
}

export async function render(root, arg) {
  await loadScores();
  let ids = parseIds(arg);
  if (!ids.length) {
    const first = state.catalog.models.find(m => !m.ext && m.frontier) || state.catalog.models.find(m => !m.ext);
    if (first) ids = [first.id];
  }
  const models = ids.map(id => model(id));

  root.append(sectionHead(t('sc.title'), t('sc.compare_hint')));
  const chips = el('div', { class: 'filters' }, picker(ids),
    models.map((m, i) => el('span', { class: 'chip' }, el('i', { class: 'swatch', style: { background: `var(--s${i + 1})` } }), m.name,
      el('button', { type: 'button', 'aria-label': 'remove', text: '×', onclick: () => setIds(ids.filter(x => x !== m.id)) }))),
    el('span', { class: 'spacer' }),
    checkbox(t('sc.featured_only'), featuredOnly, v => { featuredOnly = v; drawTable(); }));
  root.append(chips);
  if (!models.length) return;

  // header cards
  const counts = models.map(m => (state.byModel.get(m.id) || []).filter(r => r.a).length);
  root.append(el('div', { class: 'model-head section' }, models.map((m, i) => headerCard(m, i, counts[i]))));

  // radar by category (featured benchmarks only)
  const cats = categoryOrder().filter(c => state.catalog.benchmarks.some(b => b.featured && b.category === c));
  const radarSeries = models.map(m => ({
    name: m.name,
    values: cats.map(c => {
      const vals = state.catalog.benchmarks.filter(b => b.featured && b.category === c).map(b => percentile(m.id, b.id)).filter(v => v !== null);
      return vals.length ? vals.reduce((a, v) => a + v, 0) / vals.length : 0;
    }),
  }));
  const radarEl = el('div', { class: 'chart tall' });
  root.append(el('section', { class: 'section' }, el('div', { class: 'card' }, el('h3', { text: t('sc.radar_title') }), el('p', { class: 'hint', text: t('sc.radar_hint') }), radarEl,
    el('div', { class: 'legend' }, models.map((m, i) => el('span', { class: 'key' }, el('i', { style: { background: `var(--s${i + 1})` } }), m.name))))));
  requestAnimationFrame(() => radar(radarEl, { indicators: cats.map(c => ({ name: catLabel(c) })), series: radarSeries }));

  // score table
  const tableCard = el('div', { class: 'card' });
  root.append(el('section', { class: 'section' }, sectionHead(t('sc.table_title'), t('sc.table_hint')), tableCard));

  function drawTable() {
    tableCard.replaceChildren();
    const benches = state.catalog.benchmarks.filter(b => (!featuredOnly || b.featured) && models.some(m => authoritative(m.id, b.id)));
    const rows = [];
    for (const b of benches) {
      const sota = state.summary.sota[b.id];
      const cells = [td([benchLink(b.id, benchLabel(b)), el('div', { class: 'sub', text: `${catLabel(b.category)} · ${unitLabel(b.unit)}` })])];
      const alts = [];
      for (const m of models) {
        const rec = authoritative(m.id, b.id);
        if (!rec) { cells.push(td(el('span', { class: 'muted', text: t('sc.no_score') }), 'num'), td(''), ...(models.length === 1 ? [td(''), td(''), td('')] : [])); continue; }
        const rk = ranking(b.id, 'all');
        const rank = rk.rankOf.get(m.id);
        const gap = sota ? rec.s - sota.score : null;
        const gapEl = sota && sota.model_id === m.id && rec.s === sota.score
          ? el('span', { class: 'gap sota', text: t('sc.sota') })
          : gap === null ? '' : el('span', { class: 'gap ' + (better(rec.s, sota.score, b.id) ? 'pos' : 'neg'), text: (gap > 0 ? '+' : '') + fmtScore(gap, b.unit, { withUnit: b.unit === 'pct' }) });
        cells.push(td([el('b', { text: fmtScore(rec.s, b.unit) }), rec.v ? el('span', { class: 'sub', text: ' ' + rec.v }) : null, fmtCI(rec, b.unit) ? el('div', { class: 'ci', text: fmtCI(rec, b.unit) }) : null], 'num'));
        cells.push(td([rank ? `${rank} ` : '', el('span', { class: 'sub', text: rank ? t('sc.of', { n: rk.n }) : '' }), ' ', gapEl], 'num'));
        if (models.length === 1) {
          const others = (state.byModel.get(m.id) || []).filter(r => r.b === b.id && !r.a);
          cells.push(td(provenanceBadge(rec)));
          cells.push(td([rec.sc || '', others.length ? el('div', {}, el('button', { type: 'button', class: 'expand', text: t('sc.alternates', { n: others.length }), onclick: e => {
            const tr = e.target.closest('tr');
            const open = tr.dataset.open === '1';
            tr.dataset.open = open ? '0' : '1';
            e.target.textContent = open ? t('sc.alternates', { n: others.length }) : t('sc.hide');
            let next = tr.nextSibling;
            while (next && next.classList.contains('alt')) { next.hidden = open; next = next.nextSibling; }
          } })) : null], 'small'));
          cells.push(td(rec.d || '', 'small nowrap'));
          alts.push(...others.map(o => { const tr = el('tr', { class: 'alt' }, td(el('span', { class: 'sub', text: '↳ ' + (o.v || 'default') })), td(fmtScore(o.s, b.unit), 'num'), td(''), td(provenanceBadge(o)), td(o.sc || '', 'small'), td(o.d || '', 'small nowrap')); tr.hidden = true; return tr; }));
        }
      }
      rows.push(el('tr', {}, cells), ...alts);
    }
    const headers = [t('col.benchmark')];
    if (models.length === 1) headers.push(t('col.score'), t('col.rank_n'), t('col.provenance'), t('col.scaffold'), t('col.eval_date'));
    else for (const m of models) headers.push(`${m.name} · ${t('col.score')}`, t('col.rank_n'));
    tableCard.append(rows.length ? table(headers, rows) : el('div', { class: 'empty', text: t('sc.no_score') }));
  }
  drawTable();
}
