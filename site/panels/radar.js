import { t, getLang } from '../i18n.js';
import { state, loadRadar, fmtScore, fmtNum, bench, benchLabel, modelLabel } from '../data.js';
import { el, sectionHead, benchLink, extLink, checkbox } from '../ui.js';

let domainFilter = 'all';
let highOnly = false;
let sourceFilter = 'all';

function domainLabel(r, d) { const x = r.domains[d] || r.domains.other; return x ? x[getLang()] || x.en : d; }
function vendorName(r, v) { return (r.vendors[v] || {}).name || v; }
function chips(r, vendors) { return el('span', { class: 'chips' }, (vendors || []).map(v => el('span', { class: 'tag vendor', text: vendorName(r, v) }))); }

function hbar(h) {
  if (h === null || h === undefined) return el('span', { class: 'muted small', text: '–' });
  const pct = Math.round(h * 100);
  return el('span', { class: 'hbar', title: `${pct}%` }, el('i', { style: { width: pct + '%' } }), el('b', { text: pct + '%' }));
}

function rankDelta(a) {
  if (a.is_new) return el('span', { class: 'rank-delta new', text: t('rd.new') });
  if (a.prev_rank === null || a.prev_rank === undefined) return el('span', { class: 'rank-delta', text: '–' });
  const d = a.prev_rank - a.rank;
  if (d === 0) return el('span', { class: 'rank-delta', text: '＝' });
  return el('span', { class: 'rank-delta ' + (d > 0 ? 'up' : 'down'), text: (d > 0 ? '▲' : '▼') + Math.abs(d) });
}

function nameLink(item) {
  const label = item.name || item.key;
  if (item.bid && bench(item.bid)) return benchLink(item.bid, benchLabel(item.bid));
  if (item.url) return extLink(item.url, label);
  return el('span', { text: label });
}

function sotaText(item) {
  const b = item.bid ? bench(item.bid) : null;
  if (item.sota && b) return `${fmtScore(item.sota.score, b.unit)} · ${modelLabel(item.sota.model_id)}`;
  if (item.best_reported && item.best_reported.score !== null && item.best_reported.score !== undefined) return t('rd.paper_best', { n: fmtNum(item.best_reported.score, 1) });
  return t('rd.no_third_party');
}

function docsList(docs, r) {
  return el('ul', { class: 'docs' }, (docs || []).map(d => el('li', {}, el('span', { class: 'tag', text: vendorName(r, d.vendor) }), ' ', extLink(d.url, d.title || d.url), ' ', el('span', { class: 'muted small', text: d.date || '' }))));
}

export async function render(root) {
  const r = await loadRadar();
  if (!r) { root.append(el('div', { class: 'card empty', text: t('rd.unavailable') })); return; }

  root.append(sectionHead(t('rd.title'), t('rd.subtitle', { w: r.week_of, d: r.generated_at })));
  root.append(el('div', { class: 'grid kpis section' },
    tile(t('rd.kpi_new_today'), fmtNum(r.kpis.new_today, 0), t('rd.kpi_new_7d', { n: r.kpis.new_7d })),
    tile(t('rd.kpi_attention'), fmtNum(r.kpis.attention_n, 0), t('rd.kpi_week', { w: r.week_of })),
    tile(t('rd.kpi_vendors'), `${r.kpis.vendors_active_60d}/${Object.keys(r.vendors).length}`, t('rd.kpi_docs', { n: r.kpis.docs_60d })),
    tile(t('rd.kpi_llm'), r.llm && r.llm.enabled ? t('rd.llm_on', { m: r.llm.model }) : t('rd.llm_off'), r.llm && r.llm.enabled ? t('rd.llm_judged', { n: r.llm.judged_today }) : t('rd.llm_hint')),
  ));

  // ---- new & hard ----
  const hard = el('div', { class: 'grid cards' }, r.hard_new.map(h => el('div', { class: 'card hard-card' },
    el('div', { class: 'cat', text: `${domainLabel(r, h.domain || (bench(h.bid || '') || {}).category || 'other')} · ${h.release_date || ''}` }),
    el('div', { class: 'bname' }, nameLink(h)),
    el('div', { class: 'score-line' }, el('span', { class: 'muted small', text: t('rd.current_best') + ' ' }), el('b', { text: sotaText(h) }),
      h.headroom_src === 'paper' ? el('span', { class: 'tag', text: t('rd.src_paper') }) : null),
    el('div', { class: 'kv-line' }, el('span', { class: 'muted small', text: t('rd.headroom') }), hbar(h.headroom)),
    el('div', { class: 'kv-line' }, el('span', { class: 'muted small', text: t('rd.importance') }), el('b', { text: (h.importance_norm * 100).toFixed(0) }), el('span', { class: 'muted small', text: ` · ${t('rd.vendors_n', { n: h.v })}` })),
    chips(r, h.vendors),
  )));
  root.append(el('section', { class: 'section' }, sectionHead(t('rd.hard_title'), t('rd.hard_hint')),
    r.hard_new.length ? hard : el('div', { class: 'card empty', text: t('rd.hard_empty') }),
    r.unscored_new.length ? el('div', { class: 'card', style: { marginTop: '14px' } }, el('h3', { text: t('rd.unscored_title') }), el('p', { class: 'hint', text: t('rd.unscored_hint') }),
      el('ul', { class: 'plain' }, r.unscored_new.map(u => el('li', {}, nameLink(u), ' ', el('span', { class: 'muted small', text: u.release_date || '' }), ' ', chips(r, u.vendors))))) : null));

  // ---- weekly attention ----
  const rows = r.attention.map(a => {
    const tr = el('tr', {},
      el('td', { class: 'rank num', text: String(a.rank) }),
      el('td', {}, rankDelta(a)),
      el('td', {}, el('span', { class: 'model' }, nameLink(a)), el('div', { class: 'sub', text: `${domainLabel(r, a.domain || (bench(a.bid || '') || {}).category || 'other')}${a.release_date ? ' · ' + a.release_date : ''}` })),
      el('td', {}, el('b', { text: String(a.v) }), ' ', chips(r, a.vendors)),
      el('td', { class: 'num' }, el('button', { type: 'button', class: 'expand', text: String(a.n_docs), onclick: e => {
        const next = e.target.closest('tr').nextSibling; if (next && next.classList.contains('alt')) next.hidden = !next.hidden;
      } })),
      el('td', {}, el('span', { text: sotaText(a) }), a.coverage ? el('div', { class: 'sub', text: t('rd.coverage', { n: a.coverage }) }) : null),
      el('td', {}, hbar(a.headroom)),
      el('td', { class: 'num', text: a.importance.toFixed(3) }),
    );
    const alt = el('tr', { class: 'alt' }, el('td', { colspan: '8' }, docsList(a.docs, r)));
    alt.hidden = true;
    return [tr, alt];
  }).flat();
  root.append(el('section', { class: 'section' }, sectionHead(t('rd.attention_title'), t('rd.attention_hint', { w: r.week_of })),
    el('div', { class: 'card' }, rows.length ? el('div', { class: 'table-wrap' }, el('table', { class: 'data' },
      el('thead', {}, el('tr', {}, [t('col.rank'), t('rd.change'), t('col.benchmark'), t('rd.vendors'), t('rd.docs'), t('rd.current_best'), t('rd.headroom'), t('rd.importance')].map(h => el('th', { text: h })))),
      el('tbody', {}, rows))) : el('div', { class: 'empty', text: t('rd.attention_empty') }),
      el('p', { class: 'hint', style: { marginTop: '10px' }, text: t('rd.attention_method') }))));

  // ---- releases feed ----
  const feedCard = el('div');
  const domains = ['all', ...Object.keys(r.domains).filter(d => r.releases.some(x => x.domain === d))];
  const sources = ['all', ...new Set(r.releases.flatMap(x => x.sources || []))];
  const sel = el('select', { onchange: e => { domainFilter = e.target.value; drawFeed(); } }, domains.map(d => { const o = el('option', { value: d, text: d === 'all' ? t('rd.all_domains') : domainLabel(r, d) }); if (d === domainFilter) o.selected = true; return o; }));
  const selS = el('select', { onchange: e => { sourceFilter = e.target.value; drawFeed(); } }, sources.map(s => { const o = el('option', { value: s, text: s === 'all' ? t('rd.all_sources') : s }); if (s === sourceFilter) o.selected = true; return o; }));
  root.append(el('section', { class: 'section' }, sectionHead(t('rd.feed_title'), t('rd.feed_hint')),
    el('div', { class: 'filters' }, el('span', { class: 'muted small', text: t('rd.domain') }), sel, el('span', { class: 'muted small', text: t('rd.source') }), selS,
      checkbox(t('rd.high_only'), highOnly, v => { highOnly = v; drawFeed(); })),
    feedCard));

  function drawFeed() {
    feedCard.replaceChildren();
    const items = r.releases.filter(x => (domainFilter === 'all' || x.domain === domainFilter) && (sourceFilter === 'all' || (x.sources || []).includes(sourceFilter)) && (!highOnly || x.conf === 'high'));
    if (!items.length) { feedCard.append(el('div', { class: 'card empty', text: t('rd.feed_empty') })); return; }
    const byDay = new Map();
    for (const x of items) { const d = x.first_seen || x.date || ''; if (!byDay.has(d)) byDay.set(d, []); byDay.get(d).push(x); }
    for (const [day, list] of byDay) {
      feedCard.append(el('div', { class: 'day-head' }, el('b', { text: day }), el('span', { class: 'muted small', text: ` · ${t('cl.entries', { n: list.length })}` })));
      feedCard.append(el('div', { class: 'grid cards' }, list.map(x => {
        const zh = getLang() === 'zh' && x.summary_zh;
        const b = x.bid ? bench(x.bid) : null;
        return el('div', { class: 'card feed-card' + (x.conf === 'low' ? ' low' : '') },
          el('div', { class: 'cat' }, el('span', { text: domainLabel(r, x.domain) }), ' · ', el('span', { text: x.kind }), x.date && x.date !== x.first_seen ? el('span', { class: 'muted', text: ` · ${x.date}` }) : null,
            x.conf === 'low' ? el('span', { class: 'tag low', text: t('rd.low_conf') }) : null),
          el('div', { class: 'bname' }, x.url ? extLink(x.url, x.name || x.title) : el('span', { text: x.name || x.title })),
          x.title && x.title !== x.name ? el('div', { class: 'sub', text: x.title }) : null,
          el('p', { class: 'summary', text: zh ? x.summary_zh : (x.summary_en || '') }),
          el('div', { class: 'meta' },
            x.org ? el('span', { class: 'tag', text: x.org }) : null,
            (x.sources || []).map(s => el('span', { class: 'tag src', text: s })),
            x.best_reported && x.best_reported.score !== null ? el('span', { class: 'tag', text: t('rd.paper_best', { n: fmtNum(x.best_reported.score, 1) }) }) : null,
            x.upvotes ? el('span', { class: 'muted small', text: `▲${x.upvotes}` }) : null),
          el('div', { class: 'meta links' },
            x.code_url ? extLink(x.code_url, t('rd.code')) : null,
            x.hf_url ? extLink(x.hf_url, 'HF') : null,
            b ? el('span', {}, t('rd.tracked'), ' ', benchLink(b.id, benchLabel(b)), x.sota ? el('span', { class: 'muted small', text: ` · ${fmtScore(x.sota.score, b.unit)} ${modelLabel(x.sota.model_id)}` }) : null) : null,
            x.vendors && x.vendors.length ? el('span', {}, t('rd.cited_by'), ' ', chips(r, x.vendors)) : null),
        );
      })));
    }
  }
  drawFeed();

  // ---- sources ----
  root.append(el('section', { class: 'section' }, sectionHead(t('rd.sources_title'), t('rd.sources_hint')),
    el('div', { class: 'card' }, el('div', { class: 'table-wrap' }, el('table', { class: 'data' },
      el('thead', {}, el('tr', {}, [t('col.provenance'), t('col.status'), t('col.upstream'), t('col.records'), t('col.note')].map(h => el('th', { text: h })))),
      el('tbody', {}, r.sources.map(s => el('tr', {}, el('td', {}, extLink(s.url, s.name)), el('td', {}, el('span', { class: 'badge status-' + (s.status === 'ok' && s.stale ? 'stale' : s.status), text: s.status + (s.stale ? ' · stale' : '') })),
        el('td', { class: 'small nowrap', text: s.upstream_updated_at || '–' }), el('td', { class: 'num', text: String(s.records) }), el('td', { class: 'small', text: (s.note || '') + (s.error ? ' · ' + s.error : '') })))))),
    el('p', { class: 'hint', style: { marginTop: '10px' }, text: Object.values(r.vendors).filter(v => v.note).map(v => `${v.name}: ${v.note}`).join(' · ') }))));
}

function tile(label, value, sub) {
  return el('div', { class: 'tile' }, el('div', { class: 'label', text: label }), el('div', { class: 'value', text: value }), sub ? el('div', { class: 'sub', text: sub }) : null);
}
