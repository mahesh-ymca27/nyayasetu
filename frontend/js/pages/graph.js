import { get } from "../api.js";
import { ForceGraph, nodeColor } from "../graph.js";
import { $, esc, icon } from "../ui.js";

let fg = null;

export function unmount() { fg?.destroy(); fg = null; }

export async function render(el, params) {
  const chapters = await get("/api/acts/BNS/chapters");
  el.innerHTML = `
  <div class="row wrap between" style="margin-bottom:14px">
    <div class="tabs" id="g-mode">
      <button class="tab" data-mode="overview">Overview: codes & chapters</button>
      <button class="tab" data-mode="chapter">Chapter: BNS ← IPC</button>
      <button class="tab" data-mode="section">Section neighbourhood</button>
    </div>
    <div class="row">
      <select class="select" id="g-chapter" style="width:320px">${chapters.map((c) => `<option value="${esc(c.chapter)}">${esc(c.chapter)} · ${esc(title(c.name))} (${c.count})</option>`).join("")}</select>
      <input class="input hidden" id="g-section" placeholder="Section id, e.g. BNS-318 or IPC-302" style="width:240px"/>
    </div>
  </div>
  <div class="card graph-wrap">
    <canvas id="g-canvas"></canvas>
    <div class="graph-tools"><button class="icon-btn" id="z-in" title="Zoom in">+</button><button class="icon-btn" id="z-out" title="Zoom out">−</button><button class="icon-btn" id="z-reset" title="Reset">${icon("refresh")}</button></div>
    <div class="graph-legend">
      ${[["BNS", "#ff9933"], ["BNSS", "#f59e0b"], ["BSA", "#fb7185"], ["IPC", "#818cf8"], ["CrPC", "#38bdf8"], ["IEA", "#2dd4bf"], ["New in 2023", "#22c55e"]].map(([l, c]) => `<span><span class="legend-dot" style="background:${c}"></span>${l}</span>`).join("")}
      <span class="faint">→ orange: official mapping · blue: auto-aligned</span>
    </div>
    <div class="card graph-info" id="g-info"><div class="card-title">${icon("info")} Explore</div><div class="muted" style="font-size:12.5px;margin-top:6px">Drag to pan, scroll to zoom, drag nodes to rearrange. Click a node to see its details. Double-click a section to open its full text.</div><div id="g-stats" class="mt"></div></div>
  </div>`;

  fg = new ForceGraph($("#g-canvas", el), { onSelect: info });
  $("#g-canvas", el).addEventListener("dblclick", () => { if (fg.selected?.type === "section") document.dispatchEvent(new CustomEvent("open-section")); });
  $("#z-in", el).onclick = () => fg.zoom(1.2);
  $("#z-out", el).onclick = () => fg.zoom(0.83);
  $("#z-reset", el).onclick = () => { fg.reset(); fg.reheat(); };

  const setMode = async (mode) => {
    el.querySelectorAll("#g-mode .tab").forEach((t) => t.classList.toggle("active", t.dataset.mode === mode));
    $("#g-chapter").classList.toggle("hidden", mode !== "chapter");
    $("#g-section").classList.toggle("hidden", mode !== "section");
    let data;
    if (mode === "overview") data = await get("/api/graph/overview");
    else if (mode === "chapter") data = await get("/api/graph/chapter", { act: "BNS", chapter: $("#g-chapter").value });
    else data = await get(`/api/graph/section/${encodeURIComponent($("#g-section").value || "BNS-318")}`);
    fg.setData(data);
    const newCount = data.nodes.filter((n) => n.is_new).length;
    $("#g-stats").innerHTML = `<div class="row wrap" style="gap:6px"><span class="chip">${data.nodes.length} nodes</span><span class="chip">${data.edges.length} edges</span>${newCount ? `<span class="chip" style="border-color:rgba(34,197,94,.5)">${newCount} new offences</span>` : ""}</div>`;
    if (mode === "section") setTimeout(() => fg.focus(($("#g-section").value || "BNS-318").toUpperCase().replace("CRPC", "CrPC")), 400);
  };
  el.querySelectorAll("#g-mode .tab").forEach((t) => t.onclick = () => setMode(t.dataset.mode));
  $("#g-chapter").onchange = () => setMode("chapter");
  $("#g-section").onkeydown = (e) => { if (e.key === "Enter") setMode("section"); };

  const focus = params.get("focus");
  if (focus) { $("#g-section").value = focus; await setMode("section"); }
  else { $("#g-chapter").value = "CHAPTER VI"; await setMode("chapter"); }
}

function info(n) {
  const box = $("#g-info");
  if (!box) return;
  if (!n) { box.innerHTML = `<div class="card-title">${icon("info")} Explore</div><div class="muted" style="font-size:12.5px;margin-top:6px">Click a node to see its details.</div><div id="g-stats" class="mt"></div>`; return; }
  const links = fg.edges.filter((e) => e.s === n || e.t === n);
  box.innerHTML = `<div class="row"><span class="legend-dot" style="background:${nodeColor(n)};width:12px;height:12px"></span><span class="tag ${n.era === "old" ? "tag-old" : "tag-new"}">${esc(n.type)}</span>${n.is_new ? '<span class="tag tag-new">NEW 2023</span>' : ""}</div>
    <h3 style="margin:10px 0 4px">${esc(n.label)}</h3><div class="muted" style="font-size:13px;text-transform:${n.type === "chapter" ? "capitalize" : "none"}">${esc(n.type === "chapter" ? (n.title || "").toLowerCase() : n.title || "")}</div>
    <div class="label mt">${links.length} connections</div>
    <div class="stack" style="gap:6px">${links.slice(0, 12).map((e) => { const o = e.s === n ? e.t : e.s; return `<div class="row" style="font-size:12.5px;cursor:pointer" data-node="${esc(o.id)}"><span class="legend-dot" style="background:${nodeColor(o)}"></span><b>${esc(o.label)}</b><span class="faint" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc((o.title || "").slice(0, 40))}</span></div>`; }).join("")}</div>
    ${n.type === "section" ? `<button class="btn btn-sm mt" data-section="${esc(n.id)}">${icon("book")} Open full section</button>` : ""}`;
  box.querySelectorAll("[data-node]").forEach((r) => r.onclick = () => fg.focus(r.dataset.node));
}

document.addEventListener("open-section", () => {
  if (fg?.selected) document.querySelector(`#g-info [data-section]`)?.click();
});

const title = (s) => (s || "").toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());
