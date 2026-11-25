import { get, post } from "../api.js";
import { $, classificationFacts, esc, fmt, icon, toast } from "../ui.js";

const QUICK = [["IPC", "302"], ["IPC", "420"], ["IPC", "498A"], ["IPC", "376"], ["IPC", "124A"], ["CrPC", "154"], ["CrPC", "438"], ["IEA", "65B"], ["BNS", "111"]];
const SAMPLE = `The accused persons were booked u/s 420/406/120B IPC at P.S. Kotwali. The complainant's statement was recorded under Section 161 Cr.P.C. and the CCTV footage was produced with a certificate under Section 65B of the Indian Evidence Act. Bail is sought under section 438 CrPC. A separate complaint alleges cruelty under IPC 498A and criminal intimidation u/s 506 IPC.`;

let state = { act: "BNS", q: "", type: "", page: 1 };

export async function render(el, params) {
  el.innerHTML = `
  <div class="card">
    <div class="card-head"><div><div class="card-title">${icon("swap")} Convert a section</div><div class="card-sub">Pick a code and section number. Old codes show their 2023 successor; new codes show what they replaced.</div></div></div>
    <form class="big-input" id="conv-form">
      <select class="select" id="conv-act">${["IPC", "CrPC", "IEA", "BNS", "BNSS", "BSA"].map((a) => `<option>${a}</option>`).join("")}</select>
      <input class="input" id="conv-num" placeholder="Section number, e.g. 420 or 65B" autocomplete="off"/>
      <button class="btn btn-primary" type="submit" style="padding:0 26px">${icon("swap")} Convert</button>
    </form>
    <div class="row wrap" style="margin-top:12px;gap:8px"><span class="faint" style="font-size:12px">Popular:</span>${QUICK.map(([a, n]) => `<span class="chip click" data-quick="${a}|${n}">${a} ${n}</span>`).join("")}</div>
    <div id="conv-result" class="mt"></div>
  </div>

  <div class="grid g-2 mt">
    <div class="card">
      <div class="card-head"><div><div class="card-title">${icon("file")} Bulk-convert a passage</div><div class="card-sub">Paste an FIR, order or notice. Every old reference is detected and annotated.</div></div><button class="btn btn-sm" id="sample">Load sample</button></div>
      <textarea class="textarea" id="bulk" style="min-height:190px" placeholder="Paste text with references like 'u/s 420/406 IPC' or 'Section 154 Cr.P.C.'"></textarea>
      <div class="row mt"><button class="btn btn-primary" id="bulk-go">${icon("sparkles")} Detect & convert</button><button class="btn" id="bulk-copy">${icon("copy")} Copy result</button></div>
    </div>
    <div class="card">
      <div class="card-head"><div class="card-title">${icon("check")} Converted text</div><div class="row" id="bulk-stats"></div></div>
      <div class="converted-text" id="bulk-out"><span class="faint">The converted passage will appear here, with each new section highlighted.</span></div>
      <div id="bulk-refs" class="mt"></div>
    </div>
  </div>

  <div class="card mt">
    <div class="card-head wrap">
      <div><div class="card-title">${icon("layers")} Complete correspondence table</div><div class="card-sub">BNS↔IPC from the official NCRB table; BNSS↔CrPC and BSA↔IEA aligned automatically by NyayaSetu (confidence shown)</div></div>
      <div class="row wrap">
        <div class="tabs" id="map-tabs">${["BNS", "BNSS", "BSA"].map((a) => `<button class="tab ${a === state.act ? "active" : ""}" data-act="${a}">${a}</button>`).join("")}</div>
        <select class="select" id="map-type" style="width:auto"><option value="">All types</option><option value="direct">Direct</option><option value="merged">Merged</option><option value="modified">Modified</option><option value="new_provision">New provision</option></select>
        <input class="input" id="map-q" placeholder="Filter: theft, 302, bail…" style="width:220px"/>
      </div>
    </div>
    <div id="map-table"></div>
  </div>`;

  $("#conv-form", el).onsubmit = (e) => { e.preventDefault(); convertOne($("#conv-act").value, $("#conv-num").value); };
  el.querySelectorAll("[data-quick]").forEach((c) => c.onclick = () => { const [a, n] = c.dataset.quick.split("|"); $("#conv-act").value = a; $("#conv-num").value = n; convertOne(a, n); });
  $("#sample", el).onclick = () => { $("#bulk").value = SAMPLE; };
  $("#bulk-go", el).onclick = bulk;
  $("#bulk-copy", el).onclick = () => { navigator.clipboard?.writeText($("#bulk-out").innerText); toast("Copied"); };
  el.querySelectorAll("#map-tabs .tab").forEach((t) => t.onclick = () => { state = { ...state, act: t.dataset.act, page: 1 }; el.querySelectorAll("#map-tabs .tab").forEach((x) => x.classList.toggle("active", x === t)); table(); });
  $("#map-type", el).onchange = (e) => { state = { ...state, type: e.target.value, page: 1 }; table(); };
  let timer;
  $("#map-q", el).oninput = (e) => { clearTimeout(timer); timer = setTimeout(() => { state = { ...state, q: e.target.value, page: 1 }; table(); }, 220); };

  const a = params.get("act"), n = params.get("n");
  if (a && n) { $("#conv-act").value = a; $("#conv-num").value = n; convertOne(a, n); }
  else { $("#conv-act").value = "IPC"; $("#conv-num").value = "420"; convertOne("IPC", "420"); }
  table();
}

async function convertOne(act, num) {
  num = (num || "").trim();
  const out = $("#conv-result");
  if (!num) return toast("Enter a section number", "info");
  out.innerHTML = `<div class="skeleton" style="height:260px"></div>`;
  try {
    const r = await get("/api/convert", { act, number: num });
    const q = r.query;
    if (!r.results.length) {
      out.innerHTML = `<div class="compare"><div class="law-card ${q.era}">${lawHead(q.act, q.number, q.heading, q.era)}<div class="law-text">${esc(q.text)}</div></div>
        <div class="compare-arrow"><div>${icon("arrow")}</div></div>
        <div class="law-card new" style="display:grid;place-items:center;text-align:center"><div>${icon("info")}<h3 style="margin:8px 0 4px">${q.era === "new" ? "Brand-new provision" : "No direct equivalent"}</h3><div class="muted">${q.era === "new" ? "This section has no predecessor in the old code. It was introduced in 2023." : "This provision was dropped or has no listed successor in the 2023 code."}</div></div></div></div>`;
      return;
    }
    const [first, ...rest] = r.results;
    const oldSide = q.era === "old" ? { act: q.act, number: q.number, heading: q.heading, text: q.text } : { act: first.act, number: first.number, heading: first.heading, text: first.text };
    const newSide = q.era === "old" ? first : { ...q, classification: q.classification };
    const d = diff(oldSide.text, newSide.text);
    const sim = d.same / Math.max(1, Math.max(d.oldLen, d.newLen));
    out.innerHTML = `
      <div class="row wrap" style="margin-bottom:12px;gap:8px">
        <span class="chip">${icon("target")} Text similarity ${Math.round(sim * 100)}%</span>
        <span class="chip"><span class="diff-add">&nbsp;+${fmt(d.added)}&nbsp;</span> words added</span>
        <span class="chip"><span class="diff-del">&nbsp;−${fmt(d.removed)}&nbsp;</span> words removed</span>
        <span class="tag ${first.source === "official" ? "tag-off" : "tag-auto"}">${first.source === "official" ? "Official NCRB mapping" : `Auto-aligned · ${Math.round(first.confidence * 100)}% confidence`}</span>
        ${r.results.length > 1 ? `<span class="tag tag-violet">${r.results.length} related sections</span>` : ""}
      </div>
      <div class="compare">
        <div class="law-card old">${lawHead(oldSide.act, oldSide.number, oldSide.heading, "old")}<div class="law-text">${d.oldHtml}</div></div>
        <div class="compare-arrow"><div>${icon("arrow")}</div></div>
        <div class="law-card new">${lawHead(newSide.act, newSide.number, newSide.heading, "new")}<div class="law-text">${d.newHtml}</div></div>
      </div>
      ${(newSide.classification || []).slice(0, 1).map(classificationFacts).join("")}
      ${rest.length ? `<div class="mt"><div class="label">Also maps to</div><div class="row wrap">${rest.map((x) => `<span class="chip click" data-section="${esc(x.id)}"><b class="act-${esc(x.act)}">${esc(x.act)} ${esc(x.number)}</b> ${esc(x.heading)}</span>`).join("")}</div></div>` : ""}`;
  } catch (e) {
    out.innerHTML = `<div class="empty">${icon("alert")}<div>${esc(e.message)}</div></div>`;
  }
}

function lawHead(act, number, heading, era) {
  return `<div class="row between"><span class="tag ${era === "new" ? "tag-new" : "tag-old"}">${era === "new" ? "2023 CODE · IN FORCE" : "REPEALED"}</span><span class="link" data-section="${esc(act)}-${esc(number)}" style="font-size:12px">Open ${icon("arrow")}</span></div>
    <div class="law-code mt act-${esc(act)}">${esc(act)} ${esc(number)}</div><div style="font-weight:600">${esc(heading)}</div>`;
}

// Word-level LCS diff.
function diff(a, b) {
  const A = a.split(/(\s+)/).filter((x) => x.trim()), B = b.split(/(\s+)/).filter((x) => x.trim());
  const n = Math.min(A.length, 900), m = Math.min(B.length, 900);
  const norm = (w) => w.toLowerCase().replace(/[^\w]/g, "");
  const dp = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--)
    dp[i][j] = norm(A[i]) === norm(B[j]) ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  const oa = [], ob = [];
  let i = 0, j = 0, added = 0, removed = 0;
  while (i < n && j < m) {
    if (norm(A[i]) === norm(B[j])) { oa.push(esc(A[i])); ob.push(esc(B[j])); i++; j++; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) { oa.push(`<span class="diff-del">${esc(A[i])}</span>`); removed++; i++; }
    else { ob.push(`<span class="diff-add">${esc(B[j])}</span>`); added++; j++; }
  }
  while (i < n) { oa.push(`<span class="diff-del">${esc(A[i++])}</span>`); removed++; }
  while (j < m) { ob.push(`<span class="diff-add">${esc(B[j++])}</span>`); added++; }
  return { oldHtml: oa.join(" "), newHtml: ob.join(" "), added, removed, same: dp[0][0], oldLen: n, newLen: m };
}

async function bulk() {
  const text = $("#bulk").value.trim();
  if (!text) return toast("Paste some text first, or load the sample", "info");
  const btn = $("#bulk-go");
  btn.disabled = true;
  try {
    const r = await post("/api/convert/text", { text });
    $("#bulk-out").innerHTML = esc(r.converted_text).replace(/\[→ ([^\]]+)\]/g, "<mark>→ $1</mark>");
    $("#bulk-stats").innerHTML = `<span class="chip">${r.references.length} references</span><span class="chip" style="border-color:rgba(34,197,94,.5)">${r.converted_count} converted</span>`;
    $("#bulk-refs").innerHTML = r.references.length ? `<div class="table-wrap"><table><thead><tr><th>Found</th><th>Heading</th><th>2023 equivalent</th></tr></thead><tbody>${r.references.map((x) => `<tr>
      <td><span class="link" data-section="${esc(x.section_id)}">${esc(x.label)}</span></td><td>${esc(x.heading || "Not found in corpus")}</td>
      <td>${x.converted.length ? x.converted.map((c) => `<span class="link" data-section="${esc(c.id)}">${esc(c.act)} ${esc(c.number)}</span>`).join(", ") : x.era === "new" ? '<span class="tag tag-new">already new</span>' : "-"}</td></tr>`).join("")}</tbody></table></div>` : "";
  } catch (e) { toast(e.message, "error"); }
  btn.disabled = false;
}

async function table() {
  const box = $("#map-table");
  if (!box) return;
  box.innerHTML = `<div class="skeleton" style="height:300px"></div>`;
  const r = await get("/api/mappings", { act: state.act, q: state.q, type: state.type, page: state.page, size: 15 });
  const pages = Math.max(1, Math.ceil(r.total / r.size));
  const typeTag = { direct: "tag-off", merged: "tag-violet", modified: "tag-auto", new_provision: "tag-new" };
  box.innerHTML = `<div class="table-wrap"><table><thead><tr><th>2023 section</th><th>Heading</th><th>Replaces</th><th>Type</th><th>Source</th></tr></thead><tbody>
    ${r.rows.map((x) => `<tr><td><span class="link" data-section="${esc(x.new_id)}">${esc(x.new)}</span></td><td>${esc(x.new_heading)}</td>
      <td>${x.old.length ? x.old.map((o, i) => `<span class="link" data-section="${esc(o.replace(" ", "-"))}" title="${esc(x.old_headings[i])}">${esc(o)}</span>`).join(", ") : '<span class="faint">-</span>'}</td>
      <td><span class="tag ${typeTag[x.type] || ""}">${esc(x.type.replace("_", " "))}</span></td>
      <td>${x.source === "official" ? '<span class="tag tag-off">NCRB official</span>' : `<span class="tag tag-auto">auto · ${Math.round(x.confidence * 100)}%</span>`}</td></tr>`).join("") || `<tr><td colspan="5" class="empty">No rows match.</td></tr>`}
    </tbody></table></div>
    <div class="row between mt"><span class="faint">${fmt(r.total)} rows · page ${r.page} of ${pages}</span>
    <div class="row"><button class="btn btn-sm" id="pg-prev" ${r.page <= 1 ? "disabled" : ""}>Previous</button><button class="btn btn-sm" id="pg-next" ${r.page >= pages ? "disabled" : ""}>Next</button></div></div>`;
  $("#pg-prev").onclick = () => { state.page--; table(); };
  $("#pg-next").onclick = () => { state.page++; table(); };
}
