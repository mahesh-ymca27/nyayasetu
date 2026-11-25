import { get } from "../api.js";
import { $, esc, fmt, icon } from "../ui.js";

const ACTS = [
  ["BNS", "Bharatiya Nyaya Sanhita, 2023", "new"], ["BNSS", "Bharatiya Nagarik Suraksha Sanhita, 2023", "new"], ["BSA", "Bharatiya Sakshya Adhiniyam, 2023", "new"],
  ["IPC", "Indian Penal Code, 1860", "old"], ["CrPC", "Code of Criminal Procedure, 1973", "old"], ["IEA", "Indian Evidence Act, 1872", "old"],
];
let sections = [];

export async function render(el, params) {
  const act = params.get("act") || "BNS";
  el.innerHTML = `
  <div class="tabs" id="act-tabs">${ACTS.map(([c, , era]) => `<button class="tab ${c === act ? "active" : ""}" data-act="${c}">${c}${era === "old" ? ' <span class="faint" style="font-size:10px">(repealed)</span>' : ""}</button>`).join("")}</div>
  <div class="lib-layout mt">
    <div class="card" style="padding:14px">
      <div style="padding:4px 6px 12px"><div class="label" style="margin:0">${esc(ACTS.find((a) => a[0] === act)[1])}</div></div>
      <div class="chapter-list" id="chapters"><div class="skeleton" style="height:300px"></div></div>
    </div>
    <div class="card">
      <div class="card-head wrap"><div><div class="card-title" id="ch-title">${icon("book")} Sections</div><div class="card-sub" id="ch-sub"></div></div>
        <input class="input" id="lib-filter" placeholder="Filter sections in this chapter…" style="width:260px"/></div>
      <div class="stack" id="sec-list"><div class="skeleton" style="height:400px"></div></div>
    </div>
  </div>`;
  el.querySelectorAll("#act-tabs .tab").forEach((t) => t.onclick = () => { location.hash = `#/library?act=${t.dataset.act}`; });
  const chapters = await get(`/api/acts/${act}/chapters`);
  const want = params.get("chapter");
  const active = chapters.find((c) => c.chapter === want || c.name === want) || chapters[0];
  $("#chapters").innerHTML = chapters.map((c, i) => `<div class="chapter-item ${c === active ? "active" : ""}" data-i="${i}">
    <div class="row between"><span class="n">${esc(c.chapter || "PART")}</span><span class="faint" style="font-size:11px">${c.count} sections</span></div>
    <div class="t">${esc((c.name || "General").toLowerCase())}</div></div>`).join("");
  el.querySelectorAll(".chapter-item").forEach((n) => n.onclick = () => {
    el.querySelectorAll(".chapter-item").forEach((x) => x.classList.toggle("active", x === n));
    load(act, chapters[+n.dataset.i]);
  });
  $("#lib-filter").oninput = draw;
  load(act, active);
}

async function load(act, ch) {
  $("#ch-title").innerHTML = `${icon("book")} ${esc(ch.chapter || "")} <span style="text-transform:capitalize;font-weight:600">${esc((ch.name || "").toLowerCase())}</span>`;
  $("#ch-sub").textContent = `${fmt(ch.count)} sections`;
  $("#sec-list").innerHTML = `<div class="skeleton" style="height:400px"></div>`;
  sections = await get(`/api/acts/${act}/sections`, { chapter: ch.chapter || ch.name });
  $("#lib-filter").value = "";
  draw();
}

function draw() {
  const f = $("#lib-filter").value.toLowerCase().trim();
  const rows = sections.filter((s) => !f || `${s.number} ${s.heading} ${s.snippet}`.toLowerCase().includes(f));
  $("#sec-list").innerHTML = rows.map((s) => `
    <div class="section-row" data-section="${esc(s.id)}">
      <div class="row between wrap"><div><b class="act-${esc(s.act)}">${esc(s.act)} ${esc(s.number)}</b> · <b>${esc(s.heading)}</b> ${s.is_new ? '<span class="tag tag-new">NEW IN 2023</span>' : ""}</div>
      <div class="row" style="gap:6px">${s.predecessors.slice(0, 4).map((p) => `<span class="chip" style="font-size:11px">was ${esc(p)}</span>`).join("")}${s.predecessors.length > 4 ? `<span class="chip" style="font-size:11px">+${s.predecessors.length - 4}</span>` : ""}
      ${s.successors.slice(0, 3).map((p) => `<span class="chip" style="font-size:11px;border-color:rgba(255,153,51,.4)">now ${esc(p)}</span>`).join("")}</div></div>
      <div class="muted" style="font-size:12.5px;margin-top:6px">${esc(s.snippet)}${s.snippet.length >= 160 ? "…" : ""}</div>
    </div>`).join("") || `<div class="empty">${icon("search")}<div>No sections match.</div></div>`;
}
