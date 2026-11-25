import { auth, get, post } from "../api.js";
import { logout, refreshStatus } from "../app.js";
import { $, esc, icon, timeAgo, toast } from "../ui.js";

export async function render(el) {
  const user = auth.user || {};
  el.innerHTML = `
  <div class="grid g-2">
    <div class="card">
      <div class="card-head"><div class="card-title">${icon("zap")} AI engine (Groq)</div><button class="btn btn-sm" id="test">${icon("refresh")} Test connection</button></div>
      <div id="llm-status" class="stack"><div class="skeleton" style="height:60px"></div></div>
      <div class="mt"><label class="label">Model</label><div class="row"><select class="select" id="model"><option>Loading…</option></select><button class="btn" id="save-model">Save</button></div>
      <div class="faint" style="font-size:12px;margin-top:6px">The model list comes live from your Groq account. The key itself stays on the server in <span class="mono">.env</span>.</div></div>
    </div>
    <div class="card">
      <div class="card-head"><div class="card-title">${icon("user")} Account</div><button class="btn btn-sm" id="logout">${icon("logout")} Sign out</button></div>
      <div class="row"><div class="avatar" style="width:54px;height:54px;font-size:20px">${esc((user.name || "U")[0].toUpperCase())}</div>
      <div><b style="font-size:16px">${esc(user.name)}</b><div class="muted">${esc(user.email)}</div><span class="tag tag-violet">${esc(user.role || "citizen")}</span></div></div>
      <div class="card-title mt" style="margin-bottom:8px">${icon("clock")} Your recent questions</div>
      <div class="list" id="hist"></div>
    </div>
  </div>
  <div class="card mt">
    <div class="card-title" style="margin-bottom:10px">${icon("info")} About NyayaSetu</div>
    <div class="muted" style="font-size:13px">NyayaSetu explains India's new criminal laws using retrieval-augmented generation. Statute text comes from the Gazette of India via the CC0 datasets <a class="link" href="https://github.com/kanoonhq/open-laws" target="_blank" rel="noopener">kanoonhq/open-laws</a> and <a class="link" href="https://github.com/JasonTKG/bns-sections" target="_blank" rel="noopener">JasonTKG/bns-sections</a> (NCRB correspondence table and BNSS First Schedule). Answers are legal information, not legal advice. Interactive API documentation is at <a class="link" href="/docs" target="_blank">/docs</a>.</div>
  </div>`;
  $("#logout", el).onclick = logout;
  $("#test", el).onclick = status;
  $("#save-model", el).onclick = async () => {
    try { await post("/api/llm/model", { model: $("#model").value }); toast("Model updated"); refreshStatus(); status(); } catch (e) { toast(e.message, "error"); }
  };
  status();
  models();
  const hist = await get("/api/history");
  $("#hist").innerHTML = hist.length ? hist.slice(0, 8).map((h) => `<div class="list-item"><div class="list-icon i-saffron">${icon("chat")}</div><div style="min-width:0;flex:1">
    <a class="link" style="font-weight:600" href="#/assistant?q=${encodeURIComponent(h.question)}">${esc(h.question.slice(0, 90))}</a>
    <div class="faint" style="font-size:12px">${esc(h.top_section || "")} · ${esc(h.mode)} · ${Math.round((h.citation_score || 0) * 100)}% grounded · ${timeAgo(h.created_at)}</div></div></div>`).join("") : '<div class="faint">No questions yet.</div>';
}

async function status() {
  const box = $("#llm-status");
  box.innerHTML = `<div class="row"><span class="spinner dark"></span> Contacting Groq…</div>`;
  const s = await get("/api/llm/status");
  box.innerHTML = s.ok
    ? `<div class="row"><span class="status-dot ok"></span><b>Connected</b><span class="chip">${esc(s.model)}</span><span class="chip">${s.latency_ms} ms</span></div>`
    : `<div class="row"><span class="status-dot"></span><b>${s.configured ? "Connection problem" : "Offline mode"}</b></div><div class="muted" style="font-size:12.5px">${esc(s.message || "")}</div>
       ${s.configured ? "" : `<div class="converted-text mono" style="min-height:0;font-size:12px">1. Get a free key at console.groq.com/keys\n2. Create a file named .env next to run.py:\n   GROQ_API_KEY=gsk_your_key_here\n3. Restart: python run.py</div>`}`;
}

async function models() {
  const sel = $("#model");
  try {
    const r = await get("/api/llm/models");
    if (!r.models.length) { sel.innerHTML = `<option>Add a GROQ_API_KEY to choose a model</option>`; sel.disabled = true; return; }
    sel.innerHTML = r.models.map((m) => `<option ${m === r.current ? "selected" : ""}>${esc(m)}</option>`).join("");
  } catch (e) { sel.innerHTML = `<option>${esc(e.message)}</option>`; }
}
