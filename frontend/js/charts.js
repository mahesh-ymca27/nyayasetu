// Dependency-free SVG charts with hover tooltips and entry animations.
import { esc, fmt } from "./ui.js";

const PALETTE = ["#ff9933", "#8b5cf6", "#14b8a6", "#38bdf8", "#f43f5e", "#22c55e", "#f59e0b", "#6d6afe", "#ec4899", "#a3e635"];
export const color = (i) => PALETTE[i % PALETTE.length];

const tip = () => document.getElementById("chart-tip");
function bindTips(root) {
  root.querySelectorAll("[data-tip]").forEach((el) => {
    el.addEventListener("mousemove", (e) => {
      const t = tip(); t.innerHTML = el.dataset.tip; t.style.opacity = 1;
      t.style.left = `${e.clientX + 14}px`; t.style.top = `${e.clientY + 14}px`;
    });
    el.addEventListener("mouseleave", () => { tip().style.opacity = 0; });
  });
}

let gid = 0;

export function areaChart(el, points, { height = 220, label = "value", colorA = "#ff9933", colorB = "#8b5cf6" } = {}) {
  const w = Math.max(320, el.clientWidth || 600), h = height, pad = { l: 34, r: 12, t: 14, b: 26 };
  const max = Math.max(1, ...points.map((p) => p.value));
  const nice = Math.ceil(max / 4) * 4 || 4;
  const x = (i) => pad.l + (i * (w - pad.l - pad.r)) / Math.max(1, points.length - 1);
  const y = (v) => pad.t + (h - pad.t - pad.b) * (1 - v / nice);
  const id = `ag${++gid}`;
  const line = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(" ");
  const smooth = points.length > 1 ? catmull(points.map((p, i) => [x(i), y(p.value)])) : line;
  const area = `${smooth} L${x(points.length - 1)},${y(0)} L${x(0)},${y(0)} Z`;
  const grid = [0, 1, 2, 3, 4].map((k) => {
    const v = (nice / 4) * k;
    return `<line class="grid-line" x1="${pad.l}" x2="${w - pad.r}" y1="${y(v)}" y2="${y(v)}"/><text x="${pad.l - 8}" y="${y(v) + 4}" text-anchor="end">${fmt(v)}</text>`;
  }).join("");
  const every = Math.ceil(points.length / 7);
  const labels = points.map((p, i) => (i % every === 0 || i === points.length - 1) ? `<text x="${x(i)}" y="${h - 6}" text-anchor="middle">${esc(p.label)}</text>` : "").join("");
  const dots = points.map((p, i) => `<circle cx="${x(i)}" cy="${y(p.value)}" r="4" fill="${colorA}" stroke="var(--panel-solid)" stroke-width="2" data-tip="<b>${fmt(p.value)}</b> ${esc(label)}<br><span class='muted'>${esc(p.full || p.label)}</span>" style="cursor:pointer"/>`).join("");
  el.innerHTML = `<svg class="chart" viewBox="0 0 ${w} ${h}" height="${h}">
    <defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${colorA}" stop-opacity=".45"/><stop offset="1" stop-color="${colorB}" stop-opacity="0"/></linearGradient>
    <linearGradient id="${id}l" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="${colorA}"/><stop offset="1" stop-color="${colorB}"/></linearGradient></defs>
    ${grid}<path d="${area}" fill="url(#${id})"/><path d="${smooth}" fill="none" stroke="url(#${id}l)" stroke-width="3" stroke-linecap="round" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1"><animate attributeName="stroke-dashoffset" from="1" to="0" dur="1.2s" fill="freeze"/></path>${dots}${labels}</svg>`;
  bindTips(el);
}

function catmull(pts) {
  let d = `M${pts[0][0]},${pts[0][1]}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[i - 1] || pts[i], p1 = pts[i], p2 = pts[i + 1], p3 = pts[i + 2] || p2;
    const c1 = [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6];
    const c2 = [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6];
    d += ` C${c1[0].toFixed(1)},${c1[1].toFixed(1)} ${c2[0].toFixed(1)},${c2[1].toFixed(1)} ${p2[0].toFixed(1)},${p2[1].toFixed(1)}`;
  }
  return d;
}

export function barChart(el, items, { height = 240, horizontal = false, valueLabel = "", onClick } = {}) {
  const w = Math.max(320, el.clientWidth || 600);
  const max = Math.max(1, ...items.map((i) => i.value));
  const id = `bg${++gid}`;
  const defs = `<defs><linearGradient id="${id}" x1="0" y1="0" x2="${horizontal ? 1 : 0}" y2="${horizontal ? 0 : 1}"><stop offset="0" stop-color="#ff9933"/><stop offset="1" stop-color="#8b5cf6"/></linearGradient></defs>`;
  if (horizontal) {
    const rowH = 30, labelW = Math.min(230, w * 0.42), h = items.length * rowH + 6;
    const bars = items.map((it, i) => {
      const bw = ((w - labelW - 50) * it.value) / max;
      return `<g data-tip="<b>${esc(it.label)}</b><br>${fmt(it.value)} ${esc(valueLabel)}" data-idx="${i}" style="cursor:${onClick ? "pointer" : "default"}">
        <text x="0" y="${i * rowH + 19}" style="font-size:11.5px">${esc(trunc(it.label, Math.floor(labelW / 6.4)))}</text>
        <rect x="${labelW}" y="${i * rowH + 7}" width="${w - labelW - 50}" height="16" rx="8" fill="rgba(148,163,230,.08)"/>
        <rect x="${labelW}" y="${i * rowH + 7}" width="0" height="16" rx="8" fill="${it.color || `url(#${id})`}"><animate attributeName="width" from="0" to="${Math.max(4, bw)}" dur=".9s" fill="freeze" begin="${i * 0.03}s"/></rect>
        <text x="${labelW + Math.max(4, bw) + 8}" y="${i * rowH + 19}" style="font-weight:700;fill:var(--text)">${fmt(it.value)}</text></g>`;
    }).join("");
    el.innerHTML = `<svg class="chart" viewBox="0 0 ${w} ${h}" height="${h}">${defs}${bars}</svg>`;
  } else {
    const h = height, pad = { l: 30, r: 8, t: 12, b: 34 };
    const bw = (w - pad.l - pad.r) / items.length;
    const nice = Math.ceil(max / 4) * 4 || 4;
    const y = (v) => pad.t + (h - pad.t - pad.b) * (1 - v / nice);
    const grid = [0, 1, 2, 3, 4].map((k) => `<line class="grid-line" x1="${pad.l}" x2="${w - pad.r}" y1="${y((nice / 4) * k)}" y2="${y((nice / 4) * k)}"/><text x="${pad.l - 6}" y="${y((nice / 4) * k) + 4}" text-anchor="end">${fmt((nice / 4) * k)}</text>`).join("");
    const bars = items.map((it, i) => {
      const x = pad.l + i * bw + bw * 0.18, ww = bw * 0.64, top = y(it.value);
      return `<g data-tip="<b>${esc(it.full || it.label)}</b><br>${fmt(it.value)} ${esc(valueLabel)}" data-idx="${i}" style="cursor:${onClick ? "pointer" : "default"}">
        <rect x="${pad.l + i * bw}" y="${pad.t}" width="${bw}" height="${h - pad.t - pad.b}" fill="transparent"/>
        <rect x="${x}" y="${y(0)}" width="${ww}" height="0" rx="5" fill="${it.color || `url(#${id})`}"><animate attributeName="y" from="${y(0)}" to="${top}" dur=".8s" fill="freeze" begin="${i * 0.025}s"/><animate attributeName="height" from="0" to="${y(0) - top}" dur=".8s" fill="freeze" begin="${i * 0.025}s"/></rect>
        <text x="${x + ww / 2}" y="${h - 14}" text-anchor="middle">${esc(it.label)}</text></g>`;
    }).join("");
    el.innerHTML = `<svg class="chart" viewBox="0 0 ${w} ${h}" height="${h}">${defs}${grid}${bars}</svg>`;
  }
  bindTips(el);
  if (onClick) el.querySelectorAll("[data-idx]").forEach((g) => g.addEventListener("click", () => onClick(items[+g.dataset.idx])));
}

export function groupedBars(el, groups, series, { height = 260, percent = true } = {}) {
  // groups: [{label, values: {seriesKey: number}}], series: [{key, label, color}]
  const w = Math.max(320, el.clientWidth || 600), h = height, pad = { l: 38, r: 8, t: 12, b: 30 };
  const gw = (w - pad.l - pad.r) / groups.length;
  const y = (v) => pad.t + (h - pad.t - pad.b) * (1 - v);
  const grid = [0, 0.25, 0.5, 0.75, 1].map((v) => `<line class="grid-line" x1="${pad.l}" x2="${w - pad.r}" y1="${y(v)}" y2="${y(v)}"/><text x="${pad.l - 6}" y="${y(v) + 4}" text-anchor="end">${percent ? Math.round(v * 100) + "%" : v}</text>`).join("");
  const bars = groups.map((g, gi) => {
    const bw = (gw * 0.76) / series.length;
    return series.map((s, si) => {
      const v = g.values[s.key] || 0, x = pad.l + gi * gw + gw * 0.12 + si * bw, top = y(v);
      return `<rect x="${x}" y="${y(0)}" width="${bw - 3}" height="0" rx="4" fill="${s.color}" data-tip="<b>${esc(g.label)}</b><br>${esc(s.label)}: ${percent ? (v * 100).toFixed(1) + "%" : v}"><animate attributeName="y" from="${y(0)}" to="${top}" dur=".8s" fill="freeze"/><animate attributeName="height" from="0" to="${y(0) - top}" dur=".8s" fill="freeze"/></rect>`;
    }).join("") + `<text x="${pad.l + gi * gw + gw / 2}" y="${h - 10}" text-anchor="middle">${esc(g.label)}</text>`;
  }).join("");
  el.innerHTML = `<svg class="chart" viewBox="0 0 ${w} ${h}" height="${h}">${grid}${bars}</svg>`;
  bindTips(el);
}

export function donut(el, items, { size = 170, thickness = 22, center = "", sub = "" } = {}) {
  const total = items.reduce((a, b) => a + b.value, 0) || 1;
  const r = (size - thickness) / 2, c = 2 * Math.PI * r;
  let acc = 0;
  const arcs = items.map((it, i) => {
    const len = (it.value / total) * c;
    const seg = `<circle r="${r}" cx="${size / 2}" cy="${size / 2}" fill="none" stroke="${it.color || color(i)}" stroke-width="${thickness}" stroke-dasharray="0 ${c}" stroke-dashoffset="${-acc}" transform="rotate(-90 ${size / 2} ${size / 2})" data-tip="<b>${esc(it.label)}</b><br>${fmt(it.value)} (${((it.value / total) * 100).toFixed(1)}%)" style="cursor:pointer"><animate attributeName="stroke-dasharray" from="0 ${c}" to="${Math.max(0, len - 2)} ${c}" dur=".9s" fill="freeze" begin="${i * 0.08}s"/></circle>`;
    acc += len;
    return seg;
  }).join("");
  const legend = items.map((it, i) => `<div class="legend-row"><span class="legend-dot" style="background:${it.color || color(i)}"></span><span style="min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(it.label)}</span><b>${fmt(it.value)}</b></div>`).join("");
  el.innerHTML = `<div class="donut-wrap"><svg width="${size}" height="${size}" style="flex:none"><circle r="${r}" cx="${size / 2}" cy="${size / 2}" fill="none" stroke="rgba(148,163,230,.08)" stroke-width="${thickness}"/>${arcs}
    <text x="50%" y="48%" text-anchor="middle" style="font-size:22px;font-weight:800;fill:var(--text)">${esc(center)}</text><text x="50%" y="62%" text-anchor="middle" style="font-size:11px;fill:var(--muted)">${esc(sub)}</text></svg><div class="legend">${legend}</div></div>`;
  bindTips(el);
}

export function gauge(el, value, { size = 150, label = "", colorA = "#22c55e" } = {}) {
  const r = size / 2 - 12, c = Math.PI * r;
  el.innerHTML = `<svg width="${size}" height="${size / 2 + 20}" viewBox="0 0 ${size} ${size / 2 + 20}">
    <path d="M12 ${size / 2} A ${r} ${r} 0 0 1 ${size - 12} ${size / 2}" fill="none" stroke="rgba(148,163,230,.1)" stroke-width="14" stroke-linecap="round"/>
    <path d="M12 ${size / 2} A ${r} ${r} 0 0 1 ${size - 12} ${size / 2}" fill="none" stroke="${colorA}" stroke-width="14" stroke-linecap="round" stroke-dasharray="0 ${c}"><animate attributeName="stroke-dasharray" from="0 ${c}" to="${c * value} ${c}" dur="1.1s" fill="freeze"/></path>
    <text x="50%" y="${size / 2 - 4}" text-anchor="middle" style="font-size:26px;font-weight:800;fill:var(--text)">${Math.round(value * 100)}%</text>
    <text x="50%" y="${size / 2 + 16}" text-anchor="middle" style="font-size:11px;fill:var(--muted)">${esc(label)}</text></svg>`;
}

export function sparkline(values, { w = 90, h = 32, stroke = "#ff9933" } = {}) {
  if (!values.length) return "";
  const max = Math.max(1, ...values);
  const pts = values.map((v, i) => `${(i * w) / Math.max(1, values.length - 1)},${h - 2 - (v / max) * (h - 4)}`).join(" ");
  return `<svg width="${w}" height="${h}"><polyline points="${pts}" fill="none" stroke="${stroke}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
}

const trunc = (s, n) => (s.length > n ? s.slice(0, n - 1) + "…" : s);
