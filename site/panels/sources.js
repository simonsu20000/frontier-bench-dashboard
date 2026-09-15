import { t } from '../i18n.js';
import { state, fetchJSON, fmtCST, fmtNum } from '../data.js';
import { el, sectionHead, statusBadge, table, td, extLink } from '../ui.js';

export async function render(root) {
  let status = null;
  try { status = await fetchJSON('status.json', { cache: 'no-store' }); } catch (_) { status = null; }
  const sources = (status && status.sources) || state.catalog.sources;

  const rows = sources.map(s => el('tr', {},
    td(extLink(s.url, s.name)),
    td(statusBadge(s)),
    td(fmtCST(s.fetched_at), 'small nowrap'),
    td(s.upstream_updated_at || '–', 'small nowrap'),
    td(fmtNum(s.records, 0), 'num'),
    td(s.license || '', 'small'),
    td([s.not_modified ? el('span', { class: 'tag', text: t('src.not_modified') }) : null, s.error ? el('span', { class: 'small', text: ' ' + s.error }) : null, s.consecutive_failures ? el('span', { class: 'tag', text: `×${s.consecutive_failures}` }) : null], 'small'),
  ));
  root.append(el('section', { class: 'section' }, sectionHead(t('src.title'), t('src.hint')),
    el('div', { class: 'card' }, table([t('col.provenance'), t('col.status'), t('col.fetched'), t('col.upstream'), t('col.records'), t('col.license'), t('col.note')], rows, { classes: ['', '', '', '', 'num', '', ''] }))));

  const counts = (status && status.build && status.build.provenance_counts) || {};
  root.append(el('section', { class: 'section' }, sectionHead(t('src.policy_title'), t('src.policy_hint')),
    el('div', { class: 'card policy' }, ['epoch_run', 'official_leaderboard', 'third_party', 'vendor_reported'].map(k =>
      el('div', { class: 'item' }, el('b', {}, el('span', { class: 'badge ' + k, text: t('prov.' + k) }), counts[k] !== undefined ? el('span', { class: 'muted small', text: `  ${fmtNum(counts[k], 0)}` }) : null),
        el('span', { class: 'small', text: t('src.policy.' + k) }))))));

  if (status && status.build) {
    const b = status.build;
    const dropped = Object.entries(b.dropped || {}).map(([k, v]) => `${k}: ${v}`).join(', ');
    root.append(el('section', { class: 'section' }, sectionHead(t('src.build_title')),
      el('div', { class: 'card' }, el('div', { class: 'kv small' },
        el('div', {}, el('b', { text: t('src.generated') + ': ' }), fmtCST(status.generated_at) + ' (CST) · ' + status.generated_at),
        el('div', {}, el('b', { text: t('src.kept') + ': ' }), fmtNum(b.kept, 0) + ' / ' + fmtNum(b.records_in, 0)),
        el('div', {}, el('b', { text: t('src.dropped') + ': ' }), dropped || '–'),
        el('div', {}, el('b', { text: t('src.unmatched') + ': ' }), String(b.unmatched_models || 0))))));
  }

  root.append(el('section', { class: 'section' }, sectionHead(t('src.license_title')),
    el('div', { class: 'card small' }, el('p', { 'data-i18n-html': 'footer.attribution', html: t('footer.attribution') }),
      el('p', { class: 'muted', text: 'Epoch AI, "Capabilities & Benchmarking" (epoch.ai/benchmarks), CC BY 4.0. External rows retain their upstream licenses; see DATA_LICENSES.md in the repository.' }))));
}
