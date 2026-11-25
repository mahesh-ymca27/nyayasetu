// Shared UI helpers: escaping, icons, toasts, counters, markdown, modals.
import { get } from "./api.js";

export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
export const fmt = (n) => Number(n || 0).toLocaleString("en-IN");
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const P = {
  scale: '<path d="M12 3v18M7 21h10M4 7h16M4 7l-3 7a3 3 0 0 0 6 0zM20 7l-3 7a3 3 0 0 0 6 0z"/>',
  dashboard: '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
  chat: '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 21l1.9-5.4A8 8 0 1 1 21 12z"/><path d="M8.5 11h.01M12 11h.01M15.5 11h.01"/>',
  swap: '<path d="M7 4 3 8l4 4M3 8h14M17 20l4-4-4-4M21 16H7"/>',
  file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h4"/>',
  book: '<path d="M4 19.5V5a2 2 0 0 1 2-2h14v16H6.5A2.5 2.5 0 0 0 4 21.5z"/><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20M9 7h7"/>',
  graph: '<circle cx="6" cy="6" r="2.5"/><circle cx="18" cy="7" r="2.5"/><circle cx="12" cy="18" r="2.5"/><path d="M8.2 7.2 10.8 16M15.8 8.5 13 16M8.5 6.2l7 .6"/>',
  flask: '<path d="M9 3h6M10 3v6L4.5 18.5A2 2 0 0 0 6.2 21h11.6a2 2 0 0 0 1.7-2.5L14 9V3"/><path d="M7 15h10"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  moon: '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
  logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>',
  send: '<path d="m22 2-7 20-4-9-9-4z"/><path d="M22 2 11 13"/>',
  upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>',
  sparkles: '<path d="M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/>',
  alert: '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/>',
  zap: '<path d="M13 2 3 14h9l-1 8 10-12h-9z"/>',
  layers: '<path d="m12 2 10 5-10 5L2 7z"/><path d="m2 17 10 5 10-5M2 12l10 5 10-5"/>',
  trash: '<path d="M3 6h18M8 6V4h8v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>',
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  copy: '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
  target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
  printer: '<path d="M6 9V2h12v7M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/>',
  mic: '<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0 0 14 0M12 19v3"/>',
  refresh: '<path d="M21 12a9 9 0 1 1-2.6-6.4L21 8M21 3v5h-5"/>',
  database: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
  activity: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 16v-4M12 8h.01"/>',
};

export function icon(name, cls = "") {
  return `<svg class="${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${P[name] || ""}</svg>`;
}

export function toast(message, type = "success", ms = 3500) {
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = message;
  document.getElementById("toasts").appendChild(el);
  setTimeout(() => { el.style.opacity = "0"; el.style.transition = "opacity .3s"; setTimeout(() => el.remove(), 300); }, ms);
}

export function animateCount(el, to, ms = 1100, suffix = "") {
  const start = performance.now();
  const isFloat = !Number.isInteger(to);
  const step = (t) => {
    const p = Math.min(1, (t - start) / ms);
    const e = 1 - Math.pow(1 - p, 3);
    const v = to * e;
    el.textContent = (isFloat ? v.toFixed(1) : fmt(Math.round(v))) + suffix;
    if (p < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

export function timeAgo(ts) {
  const s = Math.max(1, Math.floor(Date.now() / 1000 - ts));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export function bytes(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1048576) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1048576).toFixed(1)} MB`;
}

const CITE_RE = /\[(BNSS|BNS|BSA|IPC|CrPC|IEA)\s+([0-9]{1,3}[A-Z]{0,2})(\([^\]]*\))?\]/g;

// Minimal, safe markdown: input is escaped first, then a few constructs are re-enabled.
export function markdown(src, validIds = null) {
  let s = esc(src);
  s = s.replace(CITE_RE, (_, act, num, sub) => {
    const id = `${act}-${num}`;
    const bad = validIds && !validIds.has(id);
    return `<span class="cite${bad ? " bad" : ""}" data-section="${id}" title="${bad ? "Not in retrieved sources" : "Open section"}">${act} ${num}${sub || ""}</span>`;
  });
  s = s.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/(^|[^*])\*(?!\s)(.+?)\*(?!\*)/g, "$1<i>$2</i>")
    .replace(/(^|\s)_(.+?)_(?=\s|$)/g, "$1<i>$2</i>").replace(/`([^`]+)`/g, "<code>$1</code>");
  const lines = s.split("\n");
  const out = [];
  let list = null;
  const close = () => { if (list) { out.push(`</${list}>`); list = null; } };
  for (const raw of lines) {
    const line = raw.trimEnd();
    let m;
    if ((m = line.match(/^\s*[-*•]\s+(.*)/))) { if (list !== "ul") { close(); out.push("<ul>"); list = "ul"; } out.push(`<li>${m[1]}</li>`); }
    else if ((m = line.match(/^\s*\d+[.)]\s+(.*)/))) { if (list !== "ol") { close(); out.push("<ol>"); list = "ol"; } out.push(`<li>${m[1]}</li>`); }
    else if ((m = line.match(/^#{1,4}\s+(.*)/))) { close(); out.push(`<h4>${m[1]}</h4>`); }
    else if (!line.trim()) { close(); }
    else { close(); out.push(`<p>${line}</p>`); }
  }
  close();
  return out.join("");
}

export function modal(html, { wide = false } = {}) {
  const ov = document.createElement("div");
  ov.className = "overlay";
  ov.innerHTML = `<div class="modal" style="${wide ? "width:min(1100px,100%)" : ""}"><button class="icon-btn modal-close" aria-label="Close">${icon("x")}</button>${html}</div>`;
  const close = () => { ov.remove(); document.removeEventListener("keydown", onKey); };
  const onKey = (e) => e.key === "Escape" && close();
  ov.addEventListener("click", (e) => { if (e.target === ov) close(); });
  ov.querySelector(".modal-close").onclick = close;
  document.addEventListener("keydown", onKey);
  document.body.appendChild(ov);
  return { el: ov.querySelector(".modal"), close };
}

export function classificationFacts(c) {
  if (!c) return "";
  return `<div class="facts">
    <div class="fact"><div class="k">Punishment</div><div class="v">${esc(c.punishment)}</div></div>
    <div class="fact"><div class="k">Cognizable</div><div class="v">${esc(c.cognizable)}</div></div>
    <div class="fact"><div class="k">Bailable</div><div class="v">${esc(c.bailable)}</div></div>
    <div class="fact"><div class="k">Triable by</div><div class="v">${esc(c.triable_by)}</div></div>
  </div>`;
}

export async function openSection(id) {
  const m = modal(`<div class="skeleton" style="height:28px;width:40%"></div><div class="skeleton mt" style="height:200px"></div>`);
  try {
    const s = await get(`/api/sections/${encodeURIComponent(id)}`);
    const tagFor = (x) => x.source === "official" ? "tag-off" : "tag-auto";
    const rel = (list, label) => list.length ? `<div class="mt"><div class="label">${label}</div><div class="row wrap">${list.map((x) =>
      `<span class="chip click" data-section="${esc(x.id)}"><b class="act-${esc(x.act)}">${esc(x.act)} ${esc(x.number)}</b> ${esc(x.heading).slice(0, 60)} <span class="tag ${tagFor(x)}">${x.source === "official" ? "official" : Math.round(x.confidence * 100) + "%"}</span></span>`).join("")}</div></div>` : "";
    m.el.innerHTML = m.el.querySelector(".modal-close").outerHTML + `
      <div class="row" style="gap:8px"><span class="tag ${s.era === "new" ? "tag-new" : "tag-old"}">${s.era === "new" ? "IN FORCE · 2023 CODE" : "REPEALED · 1 JULY 2024"}</span><span class="faint">${esc(s.act_name)}, ${s.act_year}</span></div>
      <h2 style="margin:10px 0 4px;letter-spacing:-.02em"><span class="act-${esc(s.act)}">${esc(s.act)} ${esc(s.number)}</span> · ${esc(s.heading)}</h2>
      <div class="muted" style="font-size:12.5px;text-transform:capitalize">${esc(s.chapter)} ${s.chapter_name ? "· " + esc(s.chapter_name.toLowerCase()) : ""}</div>
      ${s.classification.slice(0, 1).map(classificationFacts).join("")}
      ${s.classification.length > 1 ? `<details class="mt"><summary class="link">All ${s.classification.length} Schedule entries for this section</summary><div class="table-wrap mt"><table><thead><tr><th>Provision</th><th>Offence</th><th>Punishment</th><th>Cognizable</th><th>Bailable</th></tr></thead><tbody>${s.classification.map((c) => `<tr><td class="mono">${esc(c.provision)}</td><td>${esc(c.offence)}</td><td>${esc(c.punishment)}</td><td>${esc(c.cognizable)}</td><td>${esc(c.bailable)}</td></tr>`).join("")}</tbody></table></div></details>` : ""}
      <div class="law-text" style="max-height:none;color:var(--text);margin-top:16px">${esc(s.text)}</div>
      ${rel(s.predecessors, "Replaces (old code)")}${rel(s.successors, "Replaced by (2023 code)")}
      ${s.cross_references.length ? `<div class="mt"><div class="label">Cross-references in this section</div><div class="row wrap">${s.cross_references.map((r) => `<span class="chip click" data-section="${esc(r)}">${esc(r.replace("-", " "))}</span>`).join("")}</div></div>` : ""}
      <div class="row mt"><button class="btn btn-sm" id="copy-sec">${icon("copy")} Copy text</button><a class="btn btn-sm" href="#/graph?focus=${encodeURIComponent(s.id)}">${icon("graph")} View in graph</a></div>`;
    m.el.querySelector(".modal-close").onclick = m.close;
    m.el.querySelector("#copy-sec").onclick = () => { navigator.clipboard?.writeText(`${s.act} ${s.number} - ${s.heading}\n\n${s.text}`); toast("Section copied"); };
    m.el.querySelectorAll("a").forEach((a) => a.addEventListener("click", m.close));
  } catch (e) {
    m.el.innerHTML += `<div class="empty">${icon("alert")}<div>${esc(e.message)}</div></div>`;
  }
}

// Any element with data-section opens the section modal.
document.addEventListener("click", (e) => {
  const t = e.target.closest("[data-section]");
  if (t) { e.preventDefault(); openSection(t.dataset.section); }
});
