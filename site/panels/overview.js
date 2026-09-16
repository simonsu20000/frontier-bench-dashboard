import { t } from '../i18n.js';
import { state, fmtScore, fmtCST, benchLabel, catLabel, modelLabel, model, bench, fmtNum, loadRadar } from '../data.js';
import { el, esc, sectionHead, benchLink, modelLink } from '../ui.js';
import { barCI } from '../charts.js';

function tile(label, value, sub) {
  return el('div', { class: 'tile' }, el('div', { class: 'label', text: label }), el('div', { class: 'value', text: value }), sub ? el('div', { class: 'sub', text: sub }) : null);
}

export async function render(root) {
  const { summary, catalog } = state;
  const k = summary.kpis;

  // KPI tiles
  root.append(el('section', { class: 'section' }, el('div', { class: 'grid kpis' },
    tile(t('kpi.models'), fmtNum(k.models, 0), t('kpi.models_sub', { n: k.frontier_models })),
    tile(t('kpi.benchmarks'), fmtNum(k.benchmarks, 0), t('kpi.benchmarks_sub', { n: k.featured })),
    tile(t('kpi.records'), fmtNum(k.records, 0)),
    tile(t('kpi.latest_eval'), k.latest_eval_date || '–'),
    tile(t('kpi.sources'), `${k.sources_ok}/${k.sources_total}`, k.sources_stale ? t('kpi.sources_sub', { n: k.sources_stale }) : ''),
    tile(t('kpi.updated'), fmtCST(summary.generated_at)),
  )));

  // Radar strip (new benchmarks, vendor attention, new & hard)
  const radar = await loadRadar();
  if (radar) {
    const vn = v => (radar.vendors[v] || {}).name || v;
    const nameOf = x => x.bid && bench(x.bid) ? benchLink(x.bid, benchLabel(x.bid)) : (x.url ? el('a', { href: x.url, target: '_blank', rel: 'noopener', text: x.name || x.key }) : el('span', { text: x.name || x.key }));
    root.append(el('section', { class: 'section' }, sectionHead(t('ov.radar_title'), t('ov.radar_new', { n: radar.kpis.new_today, m: radar.kpis.new_7d })),
      el('div', { class: 'grid cards radar-strip' },
        el('div', { class: 'card' }, el('h3', { text: t('ov.radar_attention') }), el('ol', { class: 'plain' }, radar.attention.slice(0, 5).map(a => el('li', {}, nameOf(a), ' ', el('span', { class: 'muted small', text: a.vendors.map(vn).join(', ') }))))),
        el('div', { class: 'card' }, el('h3', { text: t('ov.radar_hard') }), el('ol', { class: 'plain' }, radar.hard_new.slice(0, 3).map(h => el('li', {}, nameOf(h), ' ', el('span', { class: 'muted small', text: h.sota && h.bid && bench(h.bid) ? fmtScore(h.sota.score, bench(h.bid).unit) : (h.best_reported ? `${fmtNum(h.best_reported.score, 1)}%` : '') }))))),
        el('div', { class: 'card' }, el('h3', { text: t('rd.feed_title') }), el('ul', { class: 'plain' }, radar.releases.filter(x => x.conf === 'high').slice(0, 5).map(x => el('li', {}, el('a', { href: x.url, target: '_blank', rel: 'noopener', text: x.name || x.title }), ' ', el('span', { class: 'muted small', text: x.date || '' })))),
          el('a', { href: '#/radar', class: 'small', text: t('ov.radar_more') })),
      )));
  }

  // ECI chart
  const eciModels = catalog.models.filter(m => !m.ext && m.eci !== null && m.eci !== undefined && m.frontier)
    .sort((a, b) => b.eci - a.eci).slice(0, 15);
  if (eciModels.length) {
    const chartEl = el('div', { class: 'chart' });
    root.append(el('section', { class: 'section' }, sectionHead(t('ov.eci_title')),
      el('div', { class: 'card' }, el('p', { class: 'hint', text: t('ov.eci_hint') }), chartEl)));
    requestAnimationFrame(() => barCI(chartEl, {
      unit: 'score',
      items: eciModels.map(m => ({
        label: m.name, value: m.eci, lo: m.eci_lo, hi: m.eci_hi,
        tooltip: `<b>${esc(m.name)}</b> · ${esc(m.org)}<br>ECI <b>${fmtNum(m.eci, 1)}</b> (${fmtNum(m.eci_lo, 1)} – ${fmtNum(m.eci_hi, 1)})<br>${esc(m.release_date || '')}`,
      })),
    }));
  }

  // SOTA cards
  const featured = catalog.benchmarks.filter(b => b.featured);
  root.append(el('section', { class: 'section' }, sectionHead(t('ov.sota_title'), t('ov.sota_hint')),
    el('div', { class: 'grid cards' }, featured.map(b => {
      const s = summary.sota[b.id];
      const m = s ? model(s.model_id) : null;
      return el('a', { class: 'card sota-card', href: '#/benchmarks/' + encodeURIComponent(b.id) },
        el('div', { class: 'cat', text: catLabel(b.category) }),
        el('div', { class: 'bname', text: benchLabel(b) }),
        s ? el('div', { class: 'score', text: fmtScore(s.score, b.unit) }) : el('div', { class: 'score muted', text: '–' }),
        s ? el('div', { class: 'model', text: (m ? m.name : modelLabel(s.model_id)) + (s.variant ? ` (${s.variant})` : '') }) : el('div', { class: 'empty', text: t('lb.no_data') }),
        el('div', { class: 'meta' },
          s ? el('span', { class: 'badge ' + s.source_type, text: t('prov.' + s.source_type) }) : null,
          s ? el('span', { text: t('lb.models_n', { n: s.n_models }) }) : null),
      );
    }))));

  // Changelog
  const cl = el('div', { class: 'changelog card' });
  if (!summary.changelog || !summary.changelog.length) {
    cl.append(el('div', { class: 'empty', text: t('ov.no_changes') }));
  } else {
    for (const day of summary.changelog) {
      const items = [];
      const lim = (arr, f, n = 12) => arr.slice(0, n).map(f).concat(arr.length > n ? [el('li', { class: 'muted', text: t('cl.more', { n: arr.length - n }) })] : []);
      if (day.new_sota && day.new_sota.length) items.push(el('div', {}, el('b', { text: t('cl.new_sota') }), el('ul', {}, lim(day.new_sota, x => {
        const b = bench(x.benchmark_id);
        return el('li', {}, benchLink(x.benchmark_id, benchLabel(x.benchmark_id)), ': ', modelLink(x.model_id, modelLabel(x.model_id)), ` ${fmtScore(x.score, b ? b.unit : 'pct')} `,
          el('span', { class: 'muted', text: `(${t('cl.prev')} ${modelLabel(x.prev_model_id)} ${fmtScore(x.prev, b ? b.unit : 'pct')})` }));
      }))));
      if (day.new_models && day.new_models.length) items.push(el('div', {}, el('b', { text: `${t('cl.new_models')} · ${t('cl.entries', { n: day.new_models.length })}` }), el('ul', {}, lim(day.new_models, mid => el('li', {}, modelLink(mid, modelLabel(mid)), ' ', el('span', { class: 'muted', text: (model(mid) || {}).org || '' }))))));
      if (day.new_scores && day.new_scores.length) items.push(el('div', {}, el('b', { text: `${t('cl.new_scores')} · ${t('cl.entries', { n: day.new_scores.length })}` }), el('ul', {}, lim(day.new_scores, x => {
        const b = bench(x.benchmark_id);
        return el('li', {}, modelLink(x.model_id, modelLabel(x.model_id)), ' · ', benchLink(x.benchmark_id, benchLabel(x.benchmark_id)), `: ${fmtScore(x.score, b ? b.unit : 'pct')}`);
      }))));
      if (day.changed && day.changed.length) items.push(el('div', {}, el('b', { text: `${t('cl.changed')} · ${t('cl.entries', { n: day.changed.length })}` }), el('ul', {}, lim(day.changed, x => {
        const b = bench(x.benchmark_id);
        return el('li', {}, modelLink(x.model_id, modelLabel(x.model_id)), ' · ', benchLink(x.benchmark_id, benchLabel(x.benchmark_id)), `: ${fmtScore(x.prev, b ? b.unit : 'pct')} → ${fmtScore(x.score, b ? b.unit : 'pct')}`);
      }))));
      cl.append(el('div', { class: 'day' }, el('div', { class: 'date', text: day.date }), items));
    }
  }
  root.append(el('section', { class: 'section' }, sectionHead(t('ov.changelog_title'), t('ov.changelog_hint')), cl));
}
