import { get } from "../api.js";
import { gauge, groupedBars } from "../charts.js";
import { $, esc, icon } from "../ui.js";

const SERIES = [
  { key: "keyword", label: "TF-IDF keyword", color: "#5f6a91" },
  { key: "bm25", label: "BM25", color: "#8b5cf6" },
  { key: "hybrid", label: "NyayaSetu Hybrid", color: "#ff9933" },
];

export async function render(el) {
  el.innerHTML = `<div class="skeleton" style="height:200px"></div><div class="skeleton mt" style="height:360px"></div>`;
  const r = await get("/api/evaluation");
  const h = r.methods.hybrid, b = r.methods.bm25;
  const lift = b.mrr ? ((h.mrr - b.mrr) / b.mrr) * 100 : 0;
  const al = r.alignment;
  el.innerHTML = `
  <section class="hero">
    <div class="hindi">Research results</div>
    <h2>Hybrid retrieval finds the right section first ${Math.round(h["hit@1"] * 100)}% of the time</h2>
    <p>Benchmark of ${r.questions} labelled questions (English, Hindi, Hinglish, colloquial and section-number queries) against the 2,354-section corpus. Each method returns its top ${r.k}; a question counts as a hit if a gold section appears within rank k. MRR is the mean reciprocal rank of the first correct section.</p>
  </section>

  <div class="grid g-4 mt">
    <div class="card" style="text-align:center"><div id="g1"></div><div class="stat-label">Hit@1 (Hybrid)</div></div>
    <div class="card" style="text-align:center"><div id="g3"></div><div class="stat-label">Hit@3 (Hybrid)</div></div>
    <div class="card" style="text-align:center"><div id="g5"></div><div class="stat-label">Hit@5 (Hybrid)</div></div>
    <div class="card stat"><div class="stat-icon i-green">${icon("zap")}</div><div><div class="stat-value">+${Math.round(lift)}%</div><div class="stat-label">MRR improvement over BM25</div><div class="faint" style="font-size:12px;margin-top:4px">${b.mrr.toFixed(3)} → ${h.mrr.toFixed(3)} · ${h.latency_ms} ms per query</div></div></div>
  </div>

  <div class="grid g-main mt">
    <div class="card">
      <div class="card-head"><div><div class="card-title">${icon("flask")} Method comparison</div><div class="card-sub">Higher is better</div></div>
        <div class="row" style="gap:12px;font-size:12px">${SERIES.map((s) => `<span><span class="legend-dot" style="background:${s.color}"></span>${s.label}</span>`).join("")}</div></div>
      <div id="cmp"></div>
    </div>
    <div class="card">
      <div class="card-title" style="margin-bottom:12px">${icon("layers")} Results table</div>
      <div class="table-wrap"><table><thead><tr><th>Method</th><th>Hit@1</th><th>Hit@3</th><th>Hit@5</th><th>MRR</th><th>ms</th></tr></thead><tbody>
      ${SERIES.map((s) => { const m = r.methods[s.key]; return `<tr style="${s.key === "hybrid" ? "background:rgba(255,153,51,.07)" : ""}"><td><b>${esc(s.label)}</b></td><td>${pct(m["hit@1"])}</td><td>${pct(m["hit@3"])}</td><td>${pct(m["hit@5"])}</td><td>${m.mrr.toFixed(3)}</td><td>${m.latency_ms}</td></tr>`; }).join("")}
      </tbody></table></div>
      <div class="card-title mt" style="margin-bottom:10px">${icon("swap")} Automatic code alignment</div>
      <div class="muted" style="font-size:12.5px;margin-bottom:10px">CrPC→BNSS and IEA→BSA mappings are produced by NyayaSetu's aligner (TF-IDF heading + body similarity with a positional prior), checked against well-known transitions:</div>
      ${Object.entries(al).map(([k, v]) => `<div style="margin-bottom:10px"><div class="row between" style="font-size:12.5px"><b>${esc(k)}</b><span>${v.correct}/${v.total} · ${pct(v.accuracy)}</span></div><div class="bar-track"><div class="bar-fill" style="width:${v.accuracy * 100}%"></div></div></div>`).join("")}
    </div>
  </div>

  <div class="card mt">
    <div class="card-head"><div><div class="card-title">${icon("globe")} Hit@3 by query type</div><div class="card-sub">Where each technique helps: Hindi vocabulary, section-reference resolution, mapping boost</div></div></div>
    <div id="kind"></div>
  </div>

  <div class="card mt">
    <div class="card-head"><div class="card-title">${icon("book")} Per-question results</div><span class="faint" style="font-size:12px">Rank of the first correct section (— = not in top ${r.k})</span></div>
    <div class="table-wrap"><table><thead><tr><th>#</th><th>Question</th><th>Type</th><th>Gold</th><th>TF-IDF</th><th>BM25</th><th>Hybrid</th></tr></thead><tbody>
    ${r.rows.map((x, i) => `<tr><td class="faint">${i + 1}</td><td>${esc(x.q)}</td><td><span class="tag tag-violet">${esc(x.kind)}</span></td><td>${x.gold.map((g) => `<span class="link" data-section="${esc(g)}">${esc(g.replace("-", " "))}</span>`).join(", ")}</td>
      ${["keyword", "bm25", "hybrid"].map((m) => `<td>${rank(x.ranks[m])}</td>`).join("")}</tr>`).join("")}
    </tbody></table></div>
    <div class="faint mt" style="font-size:12px">Method: ${esc(h.label)}. The question set is in data/eval_questions.json and can be extended.</div>
  </div>`;

  get("/api/predict/status").then((s) => {
    const m = s.metrics;
    const box = document.createElement("div");
    box.className = "card mt";
    if (!m) {
      box.innerHTML = `<div class="card-title">${icon("zap")} Section Predictor (trained model)</div><div class="muted mt" style="font-size:12.5px">Not trained yet. Run <span class="mono">python -m ml.train_section_predictor</span> to add its results here.</div>`;
    } else {
      const t = m.test;
      box.innerHTML = `<div class="card-head"><div><div class="card-title">${icon("zap")} Section Predictor (trained model)</div>
        <div class="card-sub">${esc(m.model)} · trained on ${m.train_cases.toLocaleString("en-IN")} cases, tested on ${m.test_cases.toLocaleString("en-IN")} unseen cases (${esc(m.dataset)})</div></div></div>
        <div class="table-wrap"><table><thead><tr><th>Model</th><th>Macro-F1</th><th>Micro-F1</th><th>Top-1 correct</th><th>Hit@3</th><th>Recall@5</th></tr></thead><tbody>
        <tr style="background:rgba(255,153,51,.07)"><td><b>NyayaSetu Section Predictor</b></td><td>${pct(t.macro_f1)}</td><td>${pct(t.micro_f1)}</td><td>${pct(t.precision_at_1)}</td><td>${pct(t.hit_at_3)}</td><td>${pct(t.recall_at_5)}</td></tr>
        <tr><td>${esc(m.reference.name)}</td><td>${pct(m.reference.macro_f1)}</td><td class="faint">—</td><td class="faint">—</td><td class="faint">—</td><td class="faint">—</td></tr>
        </tbody></table></div>
        <div class="card-sub mt">Threshold tuning on the dev set (macro-F1 by decision threshold)</div><div id="thr"></div>`;
      el.appendChild(box);
      const pe = s.pipeline_eval;
      const cmp = document.createElement("div");
      cmp.className = "card mt";
      if (pe) {
        const names = { model: "Trained model only", groq: `Groq only (${pe.groq_model})`, hybrid: "Hybrid: model proposes, Groq chooses" };
        cmp.innerHTML = `<div class="card-head"><div><div class="card-title">${icon("layers")} Why the model matters: model vs Groq vs hybrid</div>
          <div class="card-sub">${pe.cases} random IL-TUR test cases with known answers (seed ${pe.seed}); the model's top-${pe.candidates_k} candidates contain ${pct(pe.candidate_recall)} of the correct sections</div></div></div>
          <div class="table-wrap"><table><thead><tr><th>Method</th><th>Precision</th><th>Recall</th><th>F1</th><th>Micro-F1</th><th>Sections per case</th><th>Not a real IPC section</th></tr></thead><tbody>
          ${["model", "groq", "hybrid"].map((k) => { const m = pe.methods[k]; return `<tr${k === "hybrid" ? ' style="background:rgba(255,153,51,.07)"' : ""}><td><b>${esc(names[k])}</b></td><td>${pct(m.precision)}</td><td>${pct(m.recall)}</td><td>${pct(m.f1)}</td><td>${pct(m.micro_f1)}</td><td>${m.sections_per_case}</td><td>${m.not_a_real_ipc_section}</td></tr>`; }).join("")}
          </tbody></table></div><div class="faint mt" style="font-size:12px">Example-based scores averaged over cases. Facts were cut to ${pe.facts_chars} characters for Groq. Evaluated ${esc(pe.evaluated_at)}.</div>`;
      } else {
        cmp.innerHTML = `<div class="card-title">${icon("layers")} Model vs Groq vs hybrid</div><div class="muted mt" style="font-size:12.5px">Not run yet. Run <span class="mono">python -m ml.evaluate_case_pipeline</span> (needs the Groq key).</div>`;
      }
      el.appendChild(cmp);
      groupedBars(box.querySelector("#thr"), m.threshold_curve.filter((_, i) => i % 2 === 0).map((c) => ({ label: String(c.threshold), values: { macro: c.macro_f1, micro: c.micro_f1 } })),
        [{ key: "macro", label: "Macro-F1", color: "#ff9933" }, { key: "micro", label: "Micro-F1", color: "#8b5cf6" }], { height: 200 });
      return;
    }
    el.appendChild(box);
  }).catch(() => {});

  gauge($("#g1"), h["hit@1"], { label: `BM25: ${pct(b["hit@1"])}`, colorA: "#ff9933" });
  gauge($("#g3"), h["hit@3"], { label: `BM25: ${pct(b["hit@3"])}`, colorA: "#8b5cf6" });
  gauge($("#g5"), h["hit@5"], { label: `BM25: ${pct(b["hit@5"])}`, colorA: "#22c55e" });
  groupedBars($("#cmp"), ["hit@1", "hit@3", "hit@5", "mrr"].map((k) => ({ label: k.toUpperCase(), values: Object.fromEntries(SERIES.map((s) => [s.key, r.methods[s.key][k]])) })), SERIES);
  groupedBars($("#kind"), Object.entries(r.by_kind).map(([k, v]) => ({ label: k, values: v })), SERIES, { height: 240 });
}

const pct = (v) => `${Math.round(v * 100)}%`;
const rank = (r) => r == null ? '<span class="faint">—</span>' : `<span class="tag ${r === 1 ? "tag-new" : r <= 3 ? "tag-off" : "tag-auto"}">${r}</span>`;
