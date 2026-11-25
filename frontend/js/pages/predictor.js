import { get, post } from "../api.js";
import { $, classificationFacts, esc, fmt, icon, toast } from "../ui.js";

const EXAMPLES = [
  ["English", "My neighbour took Rs 2 lakh from me promising a government job. He gave me a fake appointment letter and now refuses to return the money."],
  ["English", "Two men on a motorcycle pulled the gold chain from my mother's neck and ran away. She fell and was injured."],
  ["Hinglish", "Mere pati aur saas dahej ke liye mujhe roz maarte hain aur ghar se nikalne ki dhamki dete hain."],
  ["Hindi", "किसी ने मेरे घर का ताला तोड़कर गहने और नकदी चोरी कर ली।"],
];

export async function render(el) {
  el.innerHTML = `
  <section class="hero">
    <div class="hindi">Own ML model · trained on Indian case law</div>
    <h2>Which sections could apply to what happened?</h2>
    <p>Describe an incident in your own words. NyayaSetu's Section Predictor, a model trained on tens of thousands of real Indian case facts, suggests the likely sections and converts them to the new BNS 2023. The search engine gives an independent second opinion.</p>
  </section>

  <div id="pred-status" class="mt"></div>

  <div class="card mt">
    <div class="card-head"><div class="card-title">${icon("file")} Describe the incident</div><span class="faint" style="font-size:12px">English, Hindi or Hinglish</span></div>
    <textarea class="textarea" id="pred-text" style="min-height:130px" placeholder="e.g. Someone called pretending to be from my bank, took my OTP and withdrew Rs 50,000 from my account."></textarea>
    <div class="row wrap mt" style="gap:8px"><span class="faint" style="font-size:12px">Try:</span>
      ${EXAMPLES.map(([lang, t], i) => `<span class="chip click" data-ex="${i}">${esc(lang)}: ${esc(t.slice(0, 42))}…</span>`).join("")}</div>
    <div class="row mt"><button class="btn btn-primary" id="pred-go">${icon("sparkles")} Predict sections</button>
      <span class="faint" style="font-size:12px">Suggestions to explore, not legal advice. Police, lawyers and courts decide which sections apply.</span></div>
  </div>

  <div id="pred-result"></div>
  <div id="pred-about" class="mt"></div>`;

  el.querySelectorAll("[data-ex]").forEach((c) => c.onclick = () => { $("#pred-text").value = EXAMPLES[+c.dataset.ex][1]; run(); });
  $("#pred-go", el).onclick = run;
  $("#pred-text", el).addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) run(); });

  const s = await get("/api/predict/status");
  showStatus(s);
  about(s);
}

function showStatus(s) {
  const box = $("#pred-status");
  if (s.available) { box.innerHTML = ""; return; }
  box.innerHTML = `<div class="card" style="border-color:rgba(245,158,11,.45)">
    <div class="row"><span class="status-dot"></span><b>The model is not active yet</b></div>
    <div class="muted" style="font-size:13px;margin-top:6px">${esc(s.message || "")}. Until then, only the search-engine suggestions are shown.</div>
    <div class="converted-text mono" style="min-height:0;font-size:12px;margin-top:10px">pip install -r requirements-ml.txt
python -m ml.train_section_predictor
python run.py</div></div>`;
}

async function run() {
  const text = $("#pred-text").value.trim();
  if (text.length < 15) return toast("Please describe what happened in at least one full sentence.", "info");
  const btn = $("#pred-go");
  btn.disabled = true; btn.innerHTML = `<span class="spinner"></span> Predicting…`;
  const out = $("#pred-result");
  out.innerHTML = `<div class="grid g-main mt"><div class="skeleton" style="height:320px"></div><div class="skeleton" style="height:320px"></div></div>`;
  try {
    const r = await post("/api/predict", { text, k: 5 });
    draw(r);
  } catch (e) {
    out.innerHTML = `<div class="card mt empty">${icon("alert")}<div>${esc(e.message)}</div></div>`;
  }
  btn.disabled = false; btn.innerHTML = `${icon("sparkles")} Predict sections`;
}

function draw(r) {
  const agree = r.search_suggestions.filter((s) => s.agrees_with_model).length;
  const preds = r.predictions;
  const left = preds.length ? preds.map((p, i) => {
    const pct = Math.round(p.probability * 100);
    const bns = p.bns[0];
    return `<div class="section-row" style="cursor:default">
      <div class="row between wrap">
        <div class="row" style="gap:8px"><span class="tag ${i === 0 ? "tag-new" : "tag-violet"}">#${i + 1}</span>
          <span class="link" data-section="${esc(p.ipc_id)}">${esc(p.ipc)}</span><span class="muted">${esc(p.ipc_heading)}</span></div>
        ${p.above_threshold ? '<span class="tag tag-off">likely</span>' : '<span class="tag tag-auto">possible</span>'}
      </div>
      <div class="row" style="gap:10px;margin-top:8px"><div class="bar-track" style="flex:1"><div class="bar-fill" style="width:${pct}%"></div></div><b style="min-width:42px;text-align:right">${pct}%</b></div>
      <div style="margin-top:8px">${p.bns.length ? `Now: ${p.bns.map((b) => `<span class="link" data-section="${esc(b.id)}">${esc(b.act)} ${esc(b.number)}</span> <span class="muted">${esc(b.heading)}</span>`).join(" · ")}` : '<span class="faint">No BNS equivalent in the mapping table</span>'}</div>
      ${bns && bns.classification?.length ? classificationFacts(bns.classification[0]) : ""}
    </div>`;
  }).join("") : `<div class="empty">${icon("info")}<div>The trained model is not active, so there are no model predictions. See the note above.</div></div>`;

  $("#pred-result").innerHTML = `
  <div class="grid g-main mt">
    <div class="card">
      <div class="card-head"><div><div class="card-title">${icon("zap")} Model prediction</div><div class="card-sub">Probability per section from NyayaSetu's trained classifier, mapped from IPC to BNS 2023</div></div>
        <span class="chip">${icon("clock")} ${r.latency_ms} ms</span></div>
      <div class="stack">${left}</div>
      ${r.added_terms.length ? `<div class="faint mt" style="font-size:12px">Hindi/Hinglish words translated for the model: <i>${esc(r.added_terms.join(", "))}</i></div>` : ""}
    </div>
    <div class="stack">
      <div class="card">
        <div class="card-head"><div><div class="card-title">${icon("search")} Search engine suggestions</div><div class="card-sub">BM25 hybrid search over BNS text (independent of the model)</div></div>
          ${preds.length ? `<span class="chip" style="border-color:${agree ? "rgba(34,197,94,.5)" : "rgba(245,158,11,.5)"}">${agree} agree with model</span>` : ""}</div>
        <div class="stack">${r.search_suggestions.map((s) => `<div class="source-card" data-section="${esc(s.id)}">
          <div class="row between"><span class="h"><span class="act-BNS">BNS ${esc(s.number)}</span> · ${esc(s.heading)}</span>${s.agrees_with_model ? '<span class="tag tag-new">agrees</span>' : ""}</div>
          <div class="s">${esc(s.snippet)}</div></div>`).join("")}</div>
      </div>
      <div class="card"><div class="card-title" style="margin-bottom:8px">${icon("shield")} Read this before relying on it</div>
        <div class="muted" style="font-size:12.5px">The model learned from facts written in court judgments, which use formal English. Short everyday descriptions are harder for it. It only knows the 100 most common IPC sections. Treat the results as sections to read and discuss with a lawyer or the police.</div></div>
    </div>
  </div>`;
}

function about(s) {
  const m = s.metrics;
  if (!m) return;
  const t = m.test;
  const pct = (v) => `${(v * 100).toFixed(1)}%`;
  $("#pred-about").innerHTML = `<div class="card">
    <div class="card-head"><div><div class="card-title">${icon("flask")} About the model</div><div class="card-sub">${esc(m.model)}</div></div>
      ${m.quick_run ? '<span class="tag tag-off">quick trial run</span>' : ""}</div>
    <div class="grid g-4">
      ${tile("Macro-F1", pct(t.macro_f1), `IL-TUR paper baseline: ${pct(m.reference.macro_f1)}`)}
      ${tile("Micro-F1", pct(t.micro_f1), "over all predicted sections")}
      ${tile("Top-1 correct", pct(t.precision_at_1), "first suggestion is a correct section")}
      ${tile("Hit@3", pct(t.hit_at_3), "a correct section in the top 3")}
    </div>
    <div class="row wrap mt" style="gap:8px;font-size:12.5px">
      <span class="chip">${fmt(m.train_cases)} training cases</span><span class="chip">${fmt(m.test_cases)} test cases</span>
      <span class="chip">${m.sections} IPC sections</span><span class="chip">${fmt(m.features)} features</span>
      <span class="chip">threshold ${m.threshold}</span><span class="chip">trained in ${fmt(m.train_seconds)} s</span>
      <span class="chip">${m.model_size_mb} MB</span><span class="chip">${esc(m.trained_at)}</span></div>
    <div class="faint mt" style="font-size:12px">Data: ${esc(m.dataset)}. Test cases were never seen during training. Trained on ${esc(m.trained_on)}.</div>
  </div>`;
}

const tile = (k, v, sub) => `<div class="fact" style="padding:14px"><div class="k">${k}</div><div class="stat-value" style="font-size:24px;margin-top:4px">${v}</div><div class="faint" style="font-size:11.5px">${esc(sub)}</div></div>`;
