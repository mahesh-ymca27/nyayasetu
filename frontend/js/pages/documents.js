import { del, download, get, post, upload } from "../api.js";
import { barChart, donut } from "../charts.js";
import { $, animateCount, bytes, esc, fmt, icon, markdown, timeAgo, toast } from "../ui.js";

let doc = null;
let page = 1;

export async function render(el, params) {
  el.innerHTML = `
  <div class="grid g-main">
    <div class="card">
      <div class="dropzone" id="dz">
        <div class="dz-icon">${icon("upload")}</div>
        <h3 style="margin:0 0 4px">Drop a legal PDF here, or click to browse</h3>
        <div class="muted">FIRs, chargesheets, judgments, legal notices, bail applications or bare acts · PDF or TXT · up to 20 MB</div>
        <div class="row" style="justify-content:center;margin-top:16px;gap:10px">
          <button class="btn btn-primary" id="pick">${icon("file")} Choose file</button>
          <button class="btn" id="sample">${icon("sparkles")} Try a sample FIR</button>
        </div>
        <input type="file" id="file" accept=".pdf,.txt,application/pdf,text/plain" hidden/>
        <div class="progress hidden" id="prog"><div></div></div>
        <div class="faint hidden" id="prog-label" style="margin-top:8px;font-size:12.5px"></div>
      </div>
      <div class="row wrap mt" style="gap:16px;font-size:12.5px">
        ${["Page-by-page text extraction", "Section detection & IPC→BNS conversion", "Dates, amounts, FIR no., police station", "AI summary, timeline & Q&A", "Export TXT · Markdown · JSON"].map((t) => `<span class="row" style="gap:6px;color:var(--muted)"><span style="color:var(--green)">${icon("check")}</span>${t}</span>`).join("")}
      </div>
    </div>
    <div class="card">
      <div class="card-head"><div class="card-title">${icon("clock")} Your documents</div><span class="chip" id="doc-count">0</span></div>
      <div class="list" id="doc-list"><div class="skeleton" style="height:120px"></div></div>
    </div>
  </div>
  <div id="result"></div>`;

  const input = $("#file", el), dz = $("#dz", el);
  $("#pick", el).onclick = (e) => { e.stopPropagation(); input.click(); };
  dz.onclick = (e) => { if (e.target === dz || e.target.closest(".dz-icon") || e.target.tagName === "H3") input.click(); };
  input.onchange = () => input.files[0] && handle(input.files[0]);
  ["dragenter", "dragover"].forEach((t) => dz.addEventListener(t, (e) => { e.preventDefault(); dz.classList.add("drag"); }));
  ["dragleave", "drop"].forEach((t) => dz.addEventListener(t, (e) => { e.preventDefault(); dz.classList.remove("drag"); }));
  dz.addEventListener("drop", (e) => e.dataTransfer.files[0] && handle(e.dataTransfer.files[0]));
  $("#sample", el).onclick = async (e) => {
    e.stopPropagation();
    const blob = await (await fetch("/samples/sample_fir.pdf")).blob();
    handle(new File([blob], "sample_fir.pdf", { type: "application/pdf" }));
  };
  await loadList();
  const id = params.get("id");
  if (id) open(id);
}

async function loadList() {
  const list = await get("/api/documents");
  $("#doc-count").textContent = list.length;
  $("#doc-list").innerHTML = list.length ? list.slice(0, 8).map((d) => `
    <div class="list-item" style="cursor:pointer" data-open="${esc(d.id)}">
      <div class="list-icon i-indigo">${icon("file")}</div>
      <div style="min-width:0;flex:1"><div style="font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(d.filename)}</div>
      <div class="faint" style="font-size:12px">${esc(d.doc_type)} · ${d.pages} pages · ${d.references_count} refs · ${timeAgo(d.created_at)}</div></div>
      <button class="icon-btn" style="width:30px;height:30px" data-del="${esc(d.id)}" title="Delete">${icon("trash")}</button>
    </div>`).join("") : `<div class="empty" style="padding:20px">${icon("file")}<div style="font-size:12.5px">No documents yet. Upload one or try the sample FIR.</div></div>`;
  document.querySelectorAll("[data-open]").forEach((n) => n.onclick = (e) => { if (!e.target.closest("[data-del]")) open(n.dataset.open); });
  document.querySelectorAll("[data-del]").forEach((b) => b.onclick = async (e) => {
    e.stopPropagation();
    if (!confirm("Delete this document and its analysis?")) return;
    await del(`/api/documents/${b.dataset.del}`);
    if (doc?.id === b.dataset.del) { doc = null; $("#result").innerHTML = ""; }
    toast("Document deleted"); loadList();
  });
}

async function handle(file) {
  const prog = $("#prog"), label = $("#prog-label");
  prog.classList.remove("hidden"); label.classList.remove("hidden");
  const bar = prog.firstElementChild;
  label.textContent = `Uploading ${file.name} (${bytes(file.size)})…`;
  try {
    const res = await upload("/api/documents", file, (p) => {
      bar.style.width = `${Math.round(p * 70)}%`;
      if (p >= 1) label.textContent = "Extracting text and detecting legal references…";
    });
    bar.style.width = "100%";
    label.textContent = `Done in ${res.analysis.stats.extract_ms} ms. ${res.analysis.stats.pages} pages, ${res.analysis.references.length} legal references found.`;
    toast(`${file.name} analysed`);
    doc = res; page = 1;
    showResult();
    loadList();
  } catch (e) {
    bar.style.width = "0";
    label.textContent = e.message;
    toast(e.message, "error");
  }
}

async function open(id) {
  try { doc = await get(`/api/documents/${id}`); page = 1; showResult(); }
  catch (e) { toast(e.message, "error"); }
}

function showResult() {
  const a = doc.analysis, s = a.stats;
  const box = $("#result");
  box.innerHTML = `
  <div class="card mt" style="background:var(--grad-soft)">
    <div class="row between wrap">
      <div class="row"><div class="list-icon i-saffron" style="width:46px;height:46px">${icon("file")}</div>
        <div><h2 style="margin:0;font-size:19px">${esc(doc.filename)}</h2><div class="muted" style="font-size:12.5px">${bytes(doc.size_bytes)} · detected as <b>${esc(a.doc_type.type)}</b> (${Math.round(a.doc_type.confidence * 100)}% of signals)${a.metadata?.producer ? " · " + esc(a.metadata.producer) : ""}</div></div></div>
      <div class="row wrap">
        <button class="btn btn-sm" data-export="txt">${icon("download")} Text</button>
        <button class="btn btn-sm" data-export="md">${icon("download")} Report</button>
        <button class="btn btn-sm" data-export="json">${icon("download")} JSON</button>
      </div>
    </div>
    ${a.is_scanned ? `<div class="chip mt" style="border-color:rgba(245,158,11,.5)">${icon("alert")} This looks like a scanned PDF with no text layer. OCR is needed to read it.</div>` : ""}
  </div>
  <div class="grid g-4 mt">
    ${mini("Pages", s.pages, "layers", "i-indigo")}${mini("Words", s.words, "file", "i-teal")}
    ${mini("Legal references", a.references.length, "scale", "i-saffron")}${mini("Under repealed codes", a.outdated_references, "alert", "i-rose")}
  </div>
  <div class="row mt"><div class="tabs" id="doc-tabs">
    <button class="tab active" data-tab="overview">Overview</button><button class="tab" data-tab="text">Extracted text</button>
    <button class="tab" data-tab="summary">${icon("sparkles").replace("<svg", '<svg style="width:14px;height:14px;vertical-align:-2px"')} AI summary</button><button class="tab" data-tab="ask">Ask the document</button></div></div>
  <div id="tab-body" class="mt"></div>`;
  box.querySelectorAll("[data-count]").forEach((n) => animateCount(n, +n.dataset.count));
  box.querySelectorAll("[data-export]").forEach((b) => b.onclick = () => {
    const f = b.dataset.export, base = doc.filename.replace(/\.[^.]+$/, "");
    download(`/api/documents/${doc.id}/export?format=${f}`, `${base}_${f === "txt" ? "extracted.txt" : f === "md" ? "report.md" : "analysis.json"}`).catch((e) => toast(e.message, "error"));
  });
  box.querySelectorAll("#doc-tabs .tab").forEach((t) => t.onclick = () => {
    box.querySelectorAll("#doc-tabs .tab").forEach((x) => x.classList.toggle("active", x === t));
    ({ overview, text, summary, ask })[t.dataset.tab]();
  });
  overview();
  box.scrollIntoView({ behavior: "smooth", block: "start" });
}

const mini = (label, v, ic, cls) => `<div class="card stat"><div class="stat-icon ${cls}">${icon(ic)}</div><div><div class="stat-value" data-count="${v}">0</div><div class="stat-label">${label}</div></div></div>`;

function overview() {
  const a = doc.analysis, e = a.entities;
  const ent = (k, label, items) => items?.length ? `<div class="entity-group"><div class="k">${label}</div><div class="row wrap" style="gap:6px">${items.map((x) => `<span class="chip">${esc(x)}</span>`).join("")}</div></div>` : "";
  $("#tab-body").innerHTML = `
  <div class="grid g-main">
    <div class="card">
      <div class="card-head"><div><div class="card-title">${icon("scale")} Legal references detected</div><div class="card-sub">Old-code references are converted to BNS / BNSS / BSA automatically</div></div></div>
      ${a.references.length ? `<div class="table-wrap"><table><thead><tr><th>Reference</th><th>Heading</th><th>2023 equivalent</th><th>Pages</th><th>×</th></tr></thead><tbody>
      ${a.references.map((r) => `<tr><td><span class="link" data-section="${esc(r.section_id)}">${esc(r.label)}</span> ${r.era === "old" ? '<span class="tag tag-old">old</span>' : '<span class="tag tag-new">new</span>'}${r.inferred ? ` <span class="tag tag-auto" title="Written as 'of the Code'; this document defines the Code as ${esc(a.code_act)}">"the Code"</span>` : ""}</td>
        <td>${esc(r.heading || "Not in corpus")}</td>
        <td>${r.converted.length ? r.converted.map((c) => `<span class="link" data-section="${esc(c.id)}">${esc(c.act)} ${esc(c.number)}</span>`).join(", ") : r.previous?.length ? `<span class="faint">was ${r.previous.map((p) => esc(p.act + " " + p.number)).join(", ")}</span>` : "-"}</td>
        <td class="mono">${r.pages.join(", ")}</td><td>${r.count}</td></tr>`).join("")}</tbody></table></div>` : `<div class="empty">${icon("info")}<div>No statutory references found in this document.</div></div>`}
    </div>
    <div class="card">
      <div class="card-title" style="margin-bottom:14px">${icon("target")} Extracted entities</div>
      ${ent("fir", "FIR / crime number", e.fir_numbers)}${ent("ps", "Police station", e.police_stations)}${ent("court", "Court", e.courts)}
      ${ent("dates", "Dates", e.dates)}${ent("amounts", "Amounts", e.amounts)}${ent("phones", "Phone numbers", e.phones)}${ent("emails", "Emails", e.emails)}
      ${Object.values(e).every((x) => !x.length) ? '<div class="faint">No entities found.</div>' : ""}
    </div>
  </div>
  <div class="grid g-3 mt">
    <div class="card"><div class="card-title" style="margin-bottom:12px">${icon("layers")} Codes cited</div><div id="acts-donut"></div></div>
    <div class="card"><div class="card-title" style="margin-bottom:12px">${icon("activity")} Top keywords</div><div id="kw-chart"></div></div>
    <div class="card"><div class="card-title" style="margin-bottom:12px">${icon("file")} Words per page</div><div id="wpp-chart"></div>
      <div class="faint mt" style="font-size:12px">Document type signals: ${a.doc_type.candidates.map((c) => `${esc(c.type)} ${Math.round(c.score * 100)}%`).join(" · ") || "none"}</div></div>
  </div>`;
  const acts = Object.entries(a.acts_mentioned);
  if (acts.length) donut($("#acts-donut"), acts.map(([k, v]) => ({ label: k, value: v, color: { BNS: "#ff9933", BNSS: "#f59e0b", BSA: "#fb7185", IPC: "#818cf8", CrPC: "#38bdf8", IEA: "#2dd4bf" }[k] })), { size: 130, thickness: 18, center: String(a.references.length), sub: "refs" });
  else $("#acts-donut").innerHTML = '<div class="faint">No codes cited.</div>';
  barChart($("#kw-chart"), a.keywords.slice(0, 8).map((k) => ({ label: k.word, value: k.count })), { horizontal: true, valueLabel: "times" });
  barChart($("#wpp-chart"), a.words_per_page.slice(0, 30).map((p) => ({ label: String(p.page), full: `Page ${p.page}`, value: p.words })), { height: 180, valueLabel: "words" });
}

function text() {
  const pages = doc.pages;
  $("#tab-body").innerHTML = `<div class="card">
    <div class="card-head wrap"><div class="card-title">${icon("file")} Extracted text</div>
      <div class="row"><input class="input" id="find" placeholder="Find in document…" style="width:240px"/><button class="btn btn-sm" id="copy-text">${icon("copy")} Copy page</button></div></div>
    <div class="page-tabs">${pages.map((p) => `<button class="page-tab ${p.page === page ? "active" : ""}" data-p="${p.page}">${p.page}</button>`).join("")}</div>
    <div class="row" style="gap:14px;font-size:12px;margin-bottom:10px"><span><mark style="background:rgba(255,153,51,.22);border-bottom:2px solid var(--saffron);padding:0 4px">IPC 420</mark> legal reference (click to open)</span><span><mark style="background:rgba(56,189,248,.16);border-bottom:2px solid var(--sky);padding:0 4px">12/03/2024</mark> entity</span></div>
    <div class="page-viewer" id="viewer"></div></div>`;
  const draw = () => {
    const p = pages.find((x) => x.page === page) || pages[0];
    $("#viewer").innerHTML = highlight(p.text, doc.analysis.highlights?.[String(p.page)] || [], $("#find").value) || '<span class="faint">No text on this page.</span>';
    document.querySelectorAll(".page-tab").forEach((b) => b.classList.toggle("active", +b.dataset.p === page));
  };
  document.querySelectorAll(".page-tab").forEach((b) => b.onclick = () => { page = +b.dataset.p; draw(); });
  $("#find").oninput = draw;
  $("#copy-text").onclick = () => { navigator.clipboard?.writeText(pages.find((x) => x.page === page)?.text || ""); toast("Page text copied"); };
  draw();
}

function highlight(raw, spans, find) {
  const e = doc.analysis.entities;
  const entityWords = [...e.dates, ...e.amounts, ...e.fir_numbers, ...e.phones].filter((x) => x && x.length > 2);
  let out = "", last = 0;
  const wrapEntities = (chunk) => {
    let h = esc(chunk);
    for (const w of entityWords) {
      const ew = esc(w).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      h = h.replace(new RegExp(ew, "g"), (m) => `<mark class="ent">${m}</mark>`);
    }
    if (find && find.trim().length > 1) {
      const f = esc(find.trim()).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      h = h.replace(new RegExp(`(?![^<]*>)(${f})`, "gi"), '<mark class="ent" style="background:rgba(34,197,94,.25);border-bottom-color:var(--green)">$1</mark>');
    }
    return h;
  };
  for (const s of spans) {
    if (s.start < last) continue;
    out += wrapEntities(raw.slice(last, s.start));
    out += `<mark data-section="${esc(s.ids[0])}" title="${esc(s.ids.join(", "))}">${esc(raw.slice(s.start, s.end))}</mark>`;
    last = s.end;
  }
  return out + wrapEntities(raw.slice(last));
}

async function summary(force = false) {
  const body = $("#tab-body");
  if (!doc.summary || force) {
    body.innerHTML = `<div class="card"><div class="row"><span class="spinner dark"></span><b>Generating structured summary…</b></div><div class="skeleton mt" style="height:220px"></div></div>`;
    try { doc.summary = await post(`/api/documents/${doc.id}/summary`); }
    catch (e) { body.innerHTML = `<div class="card empty">${icon("alert")}<div>${esc(e.message)}</div></div>`; return; }
  }
  const s = doc.summary;
  const list = (items) => (items || []).map((x) => `<li>${esc(typeof x === "string" ? x : JSON.stringify(x))}</li>`).join("");
  body.innerHTML = `<div class="grid g-main">
    <div class="card">
      <div class="card-head"><div class="card-title">${icon("sparkles")} ${esc(s.title || "Summary")}</div>
        <div class="row">${s.risk_level ? `<span class="risk ${esc(s.risk_level)}">${esc(s.risk_level)} risk</span>` : ""}<span class="chip">${s.mode === "groq" ? "Groq AI" : "Offline extractive"} · ${fmt(s.latency_ms)} ms</span><button class="btn btn-sm" id="regen">${icon("refresh")} Regenerate</button></div></div>
      <div class="bubble" style="max-width:none">${markdown(String(s.summary || ""))}</div>
      ${s.key_facts?.length ? `<h4>Key facts</h4><ul>${list(s.key_facts)}</ul>` : ""}
      ${s.offences?.length ? `<h4>Offences</h4><div class="table-wrap"><table><thead><tr><th>Old section</th><th>New section</th><th>Description</th></tr></thead><tbody>${s.offences.map((o) => `<tr><td>${esc(o.old_section || "-")}</td><td><b class="act-BNS">${esc(o.new_section || "-")}</b></td><td>${esc(o.description || "")}</td></tr>`).join("")}</tbody></table></div>` : ""}
      ${s.mode !== "groq" ? `<div class="faint mt" style="font-size:12px">Offline mode picks the most informative sentences. Add a GROQ_API_KEY for a full AI summary with parties, timeline and next steps.</div>` : ""}
    </div>
    <div class="stack">
      ${s.parties?.length ? `<div class="card"><div class="card-title" style="margin-bottom:8px">${icon("user")} Parties</div><ul style="margin:0;padding-left:18px">${list(s.parties)}</ul></div>` : ""}
      ${s.timeline?.length ? `<div class="card"><div class="card-title" style="margin-bottom:12px">${icon("clock")} Timeline</div><div class="timeline">${s.timeline.map((t) => `<div class="tl-item"><b>${esc(t.date || "")}</b><div class="muted">${esc(t.event || "")}</div></div>`).join("")}</div></div>` : ""}
      ${s.next_steps?.length ? `<div class="card"><div class="card-title" style="margin-bottom:8px">${icon("arrow")} Suggested next steps</div><ol style="margin:0;padding-left:18px">${list(s.next_steps)}</ol><div class="faint mt" style="font-size:12px">Legal information, not legal advice.</div></div>` : ""}
    </div></div>`;
  $("#regen").onclick = () => summary(true);
}

function ask() {
  $("#tab-body").innerHTML = `<div class="card">
    <div class="card-title" style="margin-bottom:12px">${icon("chat")} Ask questions about this document</div>
    <form class="row" id="doc-ask"><input class="input" id="doc-q" placeholder="e.g. Who is the accused? What amount was lost? Which sections apply?"/><button class="btn btn-primary">${icon("send")} Ask</button></form>
    <div class="row wrap mt" style="gap:8px">${["Who is the complainant?", "Which sections are applied?", "What is the date of the incident?", "How much money was involved?"].map((q) => `<span class="chip click" data-dq="${esc(q)}">${esc(q)}</span>`).join("")}</div>
    <div id="doc-answer" class="mt"></div></div>`;
  const go = async (q) => {
    if (!q.trim()) return;
    const out = $("#doc-answer");
    out.innerHTML = `<div class="row"><span class="spinner dark"></span> Searching the document…</div>`;
    try {
      const r = await post(`/api/documents/${doc.id}/ask`, { question: q, language: localStorage.getItem("nyayasetu.lang") || "en" });
      out.innerHTML = `<div class="bubble" style="max-width:none">${markdown(r.answer)}</div>
        <div class="label mt">Supporting passages</div><div class="stack">${r.passages.map((p) => `<div class="source-card" style="cursor:default"><div class="row between"><b>Page ${p.page}</b><span class="faint">score ${p.score}</span></div><div class="s" style="-webkit-line-clamp:5">${esc(p.text)}</div></div>`).join("")}</div>`;
    } catch (e) { out.innerHTML = `<div class="empty">${icon("alert")}<div>${esc(e.message)}</div></div>`; }
  };
  $("#doc-ask").onsubmit = (e) => { e.preventDefault(); go($("#doc-q").value); };
  document.querySelectorAll("[data-dq]").forEach((c) => c.onclick = () => { $("#doc-q").value = c.dataset.dq; go(c.dataset.dq); });
}
