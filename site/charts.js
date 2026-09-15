// ECharts helpers with the dataviz reference palette read from CSS variables.
import { fmtScore, fmtAxis } from './data.js';
import { esc } from './ui.js';

const live = new Set();
let resizeBound = false;

export function theme() {
  const cs = getComputedStyle(document.documentElement);
  const v = n => cs.getPropertyValue(n).trim();
  return {
    surface: v('--surface'), text: v('--text'), text2: v('--text-2'), muted: v('--muted'), grid: v('--grid'), axis: v('--axis'),
    border: v('--border-strong'),
    series: [v('--s1'), v('--s2'), v('--s3'), v('--s4'), v('--s5')],
    seq: [v('--seq-1'), v('--seq-2'), v('--seq-3'), v('--seq-4'), v('--seq-5'), v('--seq-6'), v('--seq-7')],
    font: 'system-ui, -apple-system, "Segoe UI", "PingFang SC", "Hiragino Sans GB", sans-serif',
  };
}

export function mount(elm) {
  const c = echarts.init(elm, null, { renderer: 'canvas' });
  live.add(c);
  if (!resizeBound) {
    resizeBound = true;
    window.addEventListener('resize', () => live.forEach(x => x.resize()));
  }
  return c;
}

export function disposeAll() {
  for (const c of live) c.dispose();
  live.clear();
}

function tooltipStyle(th) {
  return {
    backgroundColor: th.surface, borderColor: th.border, borderWidth: 1, padding: [8, 10],
    textStyle: { color: th.text, fontSize: 12, fontFamily: th.font },
    extraCssText: 'box-shadow:0 4px 16px rgba(0,0,0,.14);border-radius:8px;max-width:360px;white-space:normal;',
  };
}

function base(th) {
  // no entrance animation: values must be readable the instant the page paints (and in screenshots)
  return { backgroundColor: 'transparent', textStyle: { fontFamily: th.font }, animation: false };
}

/** Horizontal bar chart, single series (identity is the row label; colour = slot 1). */
export function barH(elm, { items, unit, max = null }) {
  const th = theme();
  const c = mount(elm);
  const rowH = 30;
  elm.style.height = Math.max(120, items.length * rowH + 40) + 'px';
  c.resize();
  c.setOption({
    ...base(th),
    grid: { left: 8, right: 70, top: 6, bottom: 24, containLabel: true },
    xAxis: {
      type: 'value', max, axisLabel: { color: th.muted, formatter: v => fmtAxis(v, unit) },
      splitLine: { lineStyle: { color: th.grid, width: 1 } }, axisLine: { show: false }, axisTick: { show: false },
    },
    yAxis: {
      type: 'category', inverse: true, data: items.map(i => i.label),
      axisLabel: { color: th.text2, width: 170, overflow: 'truncate', fontSize: 12 },
      axisLine: { lineStyle: { color: th.axis } }, axisTick: { show: false },
    },
    series: [{
      type: 'bar', data: items.map(i => i.value), barMaxWidth: 22, barCategoryGap: '38%',
      itemStyle: { color: th.series[0], borderRadius: [0, 4, 4, 0] },
      label: { show: true, position: 'right', color: th.text, fontSize: 12, formatter: p => fmtScore(p.value, unit) },
      emphasis: { itemStyle: { opacity: 0.8 } },
    }],
    tooltip: { trigger: 'item', ...tooltipStyle(th), formatter: p => items[p.dataIndex].tooltip },
  });
  return c;
}

/** Bars with confidence-interval whiskers (used for the ECI chart). */
export function barCI(elm, { items, unit }) {
  const th = theme();
  const c = mount(elm);
  elm.style.height = Math.max(120, items.length * 30 + 40) + 'px';
  c.resize();
  const lo = Math.min(...items.map(i => i.lo ?? i.value));
  c.setOption({
    ...base(th),
    grid: { left: 8, right: 70, top: 6, bottom: 24, containLabel: true },
    xAxis: {
      type: 'value', min: Math.floor((lo - 5) / 10) * 10, axisLabel: { color: th.muted },
      splitLine: { lineStyle: { color: th.grid } }, axisLine: { show: false }, axisTick: { show: false },
    },
    yAxis: {
      type: 'category', inverse: true, data: items.map(i => i.label),
      axisLabel: { color: th.text2, width: 170, overflow: 'truncate', fontSize: 12 },
      axisLine: { lineStyle: { color: th.axis } }, axisTick: { show: false },
    },
    series: [
      {
        type: 'bar', data: items.map(i => i.value), barMaxWidth: 20, barCategoryGap: '40%',
        itemStyle: { color: th.series[0], borderRadius: [0, 4, 4, 0] },
        // label sits inside the fill (white on blue clears contrast in both themes) so the CI whisker stays readable
        label: { show: true, position: 'insideRight', distance: 8, color: '#fff', fontSize: 12, formatter: p => fmtScore(p.value, unit) },
        z: 2,
      },
      {
        type: 'custom', z: 3, silent: true,
        data: items.map((i, idx) => [idx, i.lo ?? i.value, i.hi ?? i.value]),
        renderItem: (params, api) => {
          const y = api.coord([0, api.value(0)])[1];
          const x1 = api.coord([api.value(1), 0])[0];
          const x2 = api.coord([api.value(2), 0])[0];
          const stroke = th.text2;
          return { type: 'group', children: [
            { type: 'line', shape: { x1, y1: y, x2, y2: y }, style: { stroke, lineWidth: 1.5 } },
            { type: 'line', shape: { x1, y1: y - 4, x2: x1, y2: y + 4 }, style: { stroke, lineWidth: 1.5 } },
            { type: 'line', shape: { x1: x2, y1: y - 4, x2, y2: y + 4 }, style: { stroke, lineWidth: 1.5 } },
          ] };
        },
        encode: { x: [1, 2], y: 0 },
      },
    ],
    tooltip: { trigger: 'item', ...tooltipStyle(th), formatter: p => items[p.dataIndex]?.tooltip || '' },
  });
  return c;
}

/** Step line of record-setting scores by release date. */
export function stepLine(elm, { points, unit, name }) {
  const th = theme();
  const c = mount(elm);
  const data = points.map(p => ({ value: [p.date, p.value], label: p.label, tooltip: p.tooltip }));
  const last = data.length - 1;
  c.setOption({
    ...base(th),
    grid: { left: 8, right: 24, top: 24, bottom: 8, containLabel: true },
    xAxis: { type: 'time', axisLabel: { color: th.muted }, axisLine: { lineStyle: { color: th.axis } }, splitLine: { show: false } },
    yAxis: {
      type: 'value', axisLabel: { color: th.muted, formatter: v => fmtAxis(v, unit) },
      splitLine: { lineStyle: { color: th.grid } }, axisLine: { show: false }, axisTick: { show: false },
      max: unit === 'pct' ? 100 : null, scale: unit !== 'pct',
    },
    series: [{
      type: 'line', name, step: 'end', data, symbol: 'circle', symbolSize: 9, lineStyle: { width: 2, color: th.series[0] },
      itemStyle: { color: th.series[0], borderColor: th.surface, borderWidth: 2 },
      label: { show: true, color: th.text2, fontSize: 11, position: 'top', formatter: p => (p.dataIndex === last || p.dataIndex === 0) ? p.data.label : '' },
      areaStyle: { color: th.series[0], opacity: 0.08 },
    }],
    tooltip: { trigger: 'axis', axisPointer: { type: 'line', lineStyle: { color: th.axis } }, ...tooltipStyle(th),
      formatter: ps => ps.map(p => p.data.tooltip).join('<br>') },
  });
  return c;
}

/** Radar with ≤3 series (the three all-pairs-validated slots). */
export function radar(elm, { indicators, series }) {
  const th = theme();
  const c = mount(elm);
  c.setOption({
    ...base(th),
    radar: {
      indicator: indicators.map(i => ({ name: i.name, max: 100 })), radius: '68%',
      axisName: { color: th.text2, fontSize: 12 }, splitLine: { lineStyle: { color: th.grid } },
      splitArea: { show: false }, axisLine: { lineStyle: { color: th.axis } },
    },
    series: [{
      type: 'radar', symbolSize: 7,
      data: series.map((s, i) => ({
        name: s.name, value: s.values, lineStyle: { width: 2, color: th.series[i] },
        itemStyle: { color: th.series[i], borderColor: th.surface, borderWidth: 2 },
        areaStyle: { color: th.series[i], opacity: 0.10 },
      })),
    }],
    tooltip: { trigger: 'item', ...tooltipStyle(th),
      formatter: p => `<b>${esc(p.name)}</b><br>` + indicators.map((ind, i) => `${esc(ind.name)}: <b>${p.value[i] === null ? '–' : Math.round(p.value[i])}</b>`).join('<br>') },
  });
  return c;
}

/** Heatmap: rows × cols with per-column normalised colour and raw labels. */
export function heatmap(elm, { rows, cols, values, norm, labelFor, tooltipFor, onClick }) {
  const th = theme();
  const c = mount(elm);
  elm.style.height = Math.max(240, rows.length * 24 + 120) + 'px';
  c.resize();
  const data = [];
  rows.forEach((r, y) => cols.forEach((col, x) => { if (values[y][x] !== null && values[y][x] !== undefined) data.push([x, y, norm[y][x], values[y][x]]); }));
  c.setOption({
    ...base(th),
    grid: { left: 8, right: 16, top: 8, bottom: 100, containLabel: true },
    xAxis: { type: 'category', data: cols, position: 'bottom', axisLabel: { color: th.text2, rotate: 38, fontSize: 11, interval: 0 }, axisLine: { lineStyle: { color: th.axis } }, axisTick: { show: false }, splitArea: { show: false } },
    yAxis: { type: 'category', data: rows, inverse: true, axisLabel: { color: th.text2, fontSize: 12, width: 190, overflow: 'truncate' }, axisLine: { lineStyle: { color: th.axis } }, axisTick: { show: false } },
    visualMap: { show: false, min: 0, max: 1, dimension: 2, inRange: { color: th.seq } },
    series: [{
      type: 'heatmap', data,
      label: { show: true, fontSize: 11, formatter: p => labelFor(p.value[0], p.value[1], p.value[3]),
        color: th.text, textBorderColor: th.surface, textBorderWidth: 2 },
      itemStyle: { borderColor: th.surface, borderWidth: 2, borderRadius: 3 },
      emphasis: { itemStyle: { borderColor: th.text, borderWidth: 1.5 } },
    }],
    tooltip: { trigger: 'item', ...tooltipStyle(th), formatter: p => tooltipFor(p.value[0], p.value[1], p.value[3]) },
  });
  if (onClick) c.on('click', p => onClick(p.value[0], p.value[1]));
  return c;
}
