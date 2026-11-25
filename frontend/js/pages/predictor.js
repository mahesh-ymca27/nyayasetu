import { get, post } from "../api.js";
import { $, classificationFacts, esc, fmt, icon, markdown, toast } from "../ui.js";

const PIPE = ["Understand the incident (Groq, or rules offline)", "Candidate sections: trained model + search + fact rules",
  "Check each section: fact rules, then Groq as judge", "Punishment & bail from the official BNSS Schedule",
  "Relief and rights for your role", "Verify every cited section"];

const VERDICT = { applies: ["Likely applies", "tag-new"], needs_info: ["Depends on facts", "tag-off"], unlikely: ["Ruled out", "tag-old"] };
const SRC = { model: "Trained model", search_rank: "Search", fact_rule: "Fact rule", groq_added: "Added by Groq" };

function sourceChips(c) {
  return Object.keys(c.sources).filter((k) => SRC[k]).map((k) => {
    const v = c.sources[k];
    const extra = k === "model" ? ` ${Math.round(v * 100)}%` : k === "search_rank" ? ` #${v}` : "";
    return `<span class="chip" style="font-size:11px">${SRC[k]}${extra}</span>`;
  }).join("");
}

function chargeCard(c) {
  const [label, cls] = VERDICT[c.verdict];
  const against = c.against === "user" ? "against you" : c.against === "other_party" ? "against the other side" : "";
  return `<div class="section-row" style="cursor:default">
    <div class="row between wrap"><div class="row wrap" style="gap:8px"><span class="tag ${cls}">${label}</span>
      <span class="link" data-section="${esc(c.id)}">${esc(c.act)} ${esc(c.number)}</span><b>${esc(c.heading)}</b>
      ${c.ipc.length ? `<span class="faint" style="font-size:12px">was ${esc(c.ipc.join(", "))}</span>` : ""}</div>
      <div class="row wrap" style="gap:4px">${against ? `<span class="chip" style="font-size:11px">${against}</span>` : ""}${sourceChips(c)}</div></div>
    <div class="muted" style="margin-top:6px;font-size:13px">${esc(c.reason)} <span class="faint" style="font-size:11.5px">(${c.decided_by === "groq" ? "checked by Groq" : "rule"})</span></div>
    ${c.verdict !== "unlikely" && c.classification ? classificationFacts(c.classification) : ""}</div>`;
}

function drawAnalysis(box, r) {
  const f = r.facts, p = r.pipeline, s = r.severity;
  const applies = r.candidates.filter((c) => c.verdict === "applies");
  const depends = r.candidates.filter((c) => c.verdict === "needs_info" && !c.weak);
  const weak = r.candidates.filter((c) => c.verdict === "needs_info" && c.weak);
  const ruled = r.candidates.filter((c) => c.verdict === "unlikely");
  const flags = Object.entries(f.flags).filter(([, v]) => v).map(([k]) => k.replace(/_/g, " "));
  const roleText = { accused: "You are facing a complaint", complainant: "You were wronged", witness: "You are a witness", unclear: "Role unclear" }[f.user_role];
  const ids = new Set([...applies.map((c) => c.id), ...r.relief.map((x) => x.id)]);
  box.innerHTML = `
  <div class="grid g-main mt">
    <div class="card">
      <div class="card-head"><div class="card-title">${icon("file")} What happened</div><span class="tag tag-violet">${esc(roleText)}</span></div>
      <div>${esc(f.summary)}</div>
      ${flags.length ? `<div class="row wrap mt" style="gap:6px">${flags.map((x) => `<span class="chip">${esc(x)}</span>`).join("")}</div>` : ""}
      ${f.allegations_against_user.length ? `<div class="mt"><div class="label">The other side claims</div><ul style="margin:0;padding-left:18px">${f.allegations_against_user.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>` : ""}
      ${f.missing_info.length ? `<div class="mt"><div class="label">Details that would change the analysis</div><ul style="margin:0;padding-left:18px">${f.missing_info.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>` : ""}
      ${r.advice ? `<div class="bubble mt" style="max-width:none">${markdown(r.advice, ids)}</div>
        <div class="msg-meta"><span class="chip">${icon("shield")} ${r.advice_verification.grounded}/${r.advice_verification.total} citations verified</span></div>` : ""}
    </div>
    <div class="stack">
      <div class="card">
        <div class="card-title" style="margin-bottom:10px">${icon("alert")} How serious</div>
        <div class="row wrap" style="gap:8px">
          <span class="chip">${s.charges} likely charge${s.charges === 1 ? "" : "s"}</span>
          <span class="chip" style="border-color:${s.any_non_bailable ? "rgba(244,63,94,.5)" : "rgba(34,197,94,.5)"}">${s.any_non_bailable ? "Includes a non-bailable offence" : "All bailable"}</span>
          ${s.any_cognizable ? '<span class="chip">Police can register an FIR (cognizable)</span>' : ""}
          ${s.courts.map((c) => `<span class="chip">${esc(c)}</span>`).join("")}</div>
      </div>
      <div class="card">
        <div class="card-title" style="margin-bottom:10px">${icon("zap")} How this was worked out</div>
        <div class="pipeline">
          ${step(`Understood by ${p.understand === "groq" ? "Groq AI" : "keyword rules (offline)"}`)}
          ${step(p.model_available ? `Trained model suggested ${p.model_candidates} section(s)` : "Trained model not active", p.model_available)}
          ${step(`Search found ${p.search_candidates}; fact rules added well-known sections`)}
          ${step(`${p.ruled_out_by_rules} ruled out by fact rules; the rest checked by ${p.judge === "groq" ? "Groq" : "rules"}`)}
          ${step("Punishment and bail from the BNSS First Schedule")}
        </div>
        ${p.judge_error ? `<div class="faint mt" style="font-size:12px">Groq check failed (${esc(p.judge_error.slice(0, 90))}); rules were used.</div>` : ""}
        <div class="faint mt" style="font-size:12px">${r.latency_ms} ms in total</div>
      </div>
    </div>
  </div>

  <div class="card mt">
    <div class="card-head"><div><div class="card-title">${icon("scale")} Sections that may apply</div><div class="card-sub">Each one was checked against the facts you gave</div></div></div>
    <div class="stack">${applies.map(chargeCard).join("") || '<div class="faint">No section clearly applies on these facts.</div>'}</div>
    ${depends.length ? `<div class="label mt">Depends on the evidence</div><div class="stack">${depends.map(chargeCard).join("")}</div>` : ""}
    ${ruled.length ? `<details class="mt"><summary class="link">${ruled.length} section(s) ruled out, with the reason</summary><div class="stack mt">${ruled.map(chargeCard).join("")}</div></details>` : ""}
    ${weak.length ? `<details class="mt"><summary class="link">${weak.length} weaker possibilities found only by keyword search</summary><div class="stack mt">${weak.map(chargeCard).join("")}</div></details>` : ""}
    ${r.outside_corpus.length ? `<div class="label mt">Other laws to check (outside NyayaSetu's data, verify separately)</div><div class="stack">${r.outside_corpus.map((o) => `<div class="source-card" style="cursor:default"><b>${esc(o.law)}${o.section ? `, Section ${esc(o.section)}` : ""}</b> <span class="tag tag-auto">verify</span><div class="s">${esc(o.reason)}</div></div>`).join("")}</div>` : ""}
  </div>

  <div class="grid g-2 mt">
    <div class="card">
      <div class="card-title" style="margin-bottom:10px">${icon("shield")} Your protection and options</div>
      <div class="stack">${r.relief.map((x) => `<div class="source-card" data-section="${esc(x.id)}"><div class="row between"><span class="h">${esc(x.title)}</span><span class="act-BNS" style="font-weight:700;font-size:12px">${esc(x.act)} ${esc(x.number)}</span></div><div class="s">${esc(x.explanation)}</div></div>`).join("")}</div>
    </div>
    <div class="card">
      <div class="card-title" style="margin-bottom:10px">${icon("check")} What to do now</div>
      <ol style="margin:0;padding-left:18px">${r.next_steps.map((x) => `<li style="margin:6px 0">${esc(x)}</li>`).join("")}</ol>
      <div class="faint mt" style="font-size:12px">Legal information, not legal advice. For your case, speak to a lawyer.</div>
    </div>
  </div>`;
}

const step = (t, ok = true) => `<div class="pipe-step ${ok ? "done" : ""}"><span class="dot">${ok ? "✓" : "–"}</span>${esc(t)}</div>`;

async function analyse() {
  const text = $("#pred-text").value.trim();
  if (text.length < 15) return toast("Please describe what happened in at least one full sentence.", "info");
  const btn = $("#case-go");
  btn.disabled = true; btn.innerHTML = `<span class="spinner"></span> Analysing…`;
  $("#pred-result").innerHTML = `<div class="card mt"><div class="pipeline">${PIPE.map((p, i) => `<div class="pipe-step ${i === 0 ? "run" : ""}"><span class="dot">${i + 1}</span>${p}</div>`).join("")}</div></div>`;
  try {
    drawAnalysis($("#pred-result"), await post("/api/analyze", { text, role: $("#case-role").value || null }));
  } catch (e) {
    $("#pred-result").innerHTML = `<div class="card mt empty">${icon("alert")}<div>${esc(e.message)}</div></div>`;
  }
  btn.disabled = false; btn.innerHTML = `${icon("shield")} Analyse my case`;
}

const EXAMPLES = [
  ["English", "Two friends and I were riding a scooty. I was drunk and we hit a car parked on the street. The car owner is suing us for the damage and also falsely claims we hit her and physically abused her."],
  ["English", "My neighbour took Rs 2 lakh from me promising a government job. He gave me a fake appointment letter and now refuses to return the money."],
  ["English", "Two men on a motorcycle pulled the gold chain from my mother's neck and ran away. She fell and was injured."],
  ["Hinglish", "Mere pati aur saas dahej ke liye mujhe roz maarte hain aur ghar se nikalne ki dhamki dete hain."],
  ["Hindi", "किसी ने मेरे घर का ताला तोड़कर गहने और नकदी चोरी कर ली।"],
];

export async function render(el) {
  el.innerHTML = `
  <section class="hero">
    <div class="hindi">Trained model + legal rules + Groq AI</div>
    <h2>What could you be charged with, and what can you do?</h2>
    <p>Describe an incident in your own words. NyayaSetu's model, trained on 42,750 real Indian case facts, proposes sections; fact rules and Groq check each one against what you said; the official BNSS Schedule gives punishment and bail; and you get the rights and remedies that fit your side of the case.</p>
  </section>

  <div id="pred-status" class="mt"></div>

  <div class="card mt">
    <div class="card-head"><div class="card-title">${icon("file")} Describe the incident</div><span class="faint" style="font-size:12px">English, Hindi or Hinglish</span></div>
    <textarea class="textarea" id="pred-text" style="min-height:130px" placeholder="e.g. Someone called pretending to be from my bank, took my OTP and withdrew Rs 50,000 from my account."></textarea>
    <div class="row wrap mt" style="gap:8px"><span class="faint" style="font-size:12px">Try:</span>
      ${EXAMPLES.map(([lang, t], i) => `<span class="chip click" data-ex="${i}">${esc(lang)}: ${esc(t.slice(0, 42))}…</span>`).join("")}</div>
    <div class="row wrap mt">
      <button class="btn btn-primary" id="case-go">${icon("shield")} Analyse my case</button>
      <select class="select" id="case-role" style="width:auto" title="Who are you in this incident?">
        <option value="">Detect my role</option><option value="accused">I am accused / facing a complaint</option><option value="complainant">I was wronged / want to complain</option>
      </select>
      <button class="btn" id="pred-go">${icon("zap")} Model prediction only</button>
      <span class="faint" style="font-size:12px">Suggestions to explore, not legal advice. Police, lawyers and courts decide which sections apply.</span></div>
  </div>

  <div id="pred-result"></div>
  <div id="pred-about" class="mt"></div>`;

  el.querySelectorAll("[data-ex]").forEach((c) => c.onclick = () => { $("#pred-text").value = EXAMPLES[+c.dataset.ex][1]; analyse(); });
  $("#pred-go", el).onclick = run;
  $("#case-go", el).onclick = analyse;
  $("#pred-text", el).addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) analyse(); });

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
