import { get } from "../api.js";
import { areaChart, barChart, color, donut, sparkline } from "../charts.js";
import { $, animateCount, esc, fmt, icon, timeAgo } from "../ui.js";
import { auth } from "../api.js";

const KIND_ICON = { predict: ["target", "i-green"], ask: ["chat", "i-saffron"], document: ["file", "i-indigo"], convert: ["swap", "i-teal"], summary: ["sparkles", "i-rose"], user: ["user", "i-green"], settings: ["settings", "i-sky"] };

export async function render(el) {
  el.innerHTML = skeleton();
  const data = await get("/api/stats/overview");
  const { corpus, usage } = data;
  const name = (auth.user?.name || "there").split(" ")[0];
  const hour = new Date().getHours();
  const greet = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
  const perDay = usage.per_day.map((d) => d.queries);

  el.innerHTML = `
  <section class="hero">
    <div class="hindi">नमस्ते, ${esc(name)} 🙏</div>
    <h2>${greet}. ${data.llm_configured ? "Your AI legal workspace is ready." : "Your legal workspace is ready (offline mode)."}</h2>
    <p>India's three new criminal codes have been in force since <b>1 July 2024</b>. NyayaSetu indexes <b>${fmt(corpus.sections)}</b> sections from six codes and <b>${fmt(corpus.mappings)}</b> old→new mappings, so you can ask questions, convert IPC/CrPC sections, and analyse legal documents.</p>
    <div class="hero-actions">
      <a class="btn btn-primary" href="#/assistant">${icon("sparkles")} Ask the AI assistant</a>
      <a class="btn" href="#/documents">${icon("upload")} Analyse a PDF</a>
      <a class="btn" href="#/converter">${icon("swap")} Convert IPC 420</a>
    </div>
  </section>

  <div class="grid g-4 mt">
    ${stat("Sections indexed", corpus.sections, "database", "i-saffron", `${corpus.acts} codes · full text`)}
    ${stat("Old → new mappings", corpus.mappings, "swap", "i-indigo", `${fmt(corpus.official_mappings)} from the official NCRB table`)}
    ${stat("Questions answered", usage.totals.queries, "chat", "i-teal", usage.avg_latency_ms ? `avg ${fmt(Math.round(usage.avg_latency_ms))} ms response` : "Ask your first question", sparkline(perDay, { stroke: "#14b8a6" }))}
    ${stat("Documents analysed", usage.totals.documents, "file", "i-rose", `${fmt(usage.totals.pages)} pages · ${fmt(usage.totals.references)} references found`)}
  </div>

  <div class="grid g-main mt">
    <div class="card">
      <div class="card-head"><div><div class="card-title">${icon("layers")} BNS 2023: sections per chapter</div><div class="card-sub">All 20 chapters of the Bharatiya Nyaya Sanhita · click a bar to open it in the Library</div></div></div>
      <div id="chapters-chart"></div>
    </div>
    <div class="card">
      <div class="card-head"><div><div class="card-title">${icon("shield")} Offence classification</div><div class="card-sub">From the First Schedule of BNSS (${fmt(corpus.classified_offences)} entries)</div></div></div>
      <div id="cog-donut"></div>
      <div style="height:18px"></div>
      <div id="bail-donut"></div>
    </div>
  </div>

  <div class="grid g-3 mt">
    <div class="card span-2">
      <div class="card-head"><div><div class="card-title">${icon("activity")} Assistant usage, last 14 days</div><div class="card-sub">Questions asked per day</div></div>
        <div class="row"><span class="chip">${icon("target")} Citation grounding ${Math.round((usage.avg_citation_score || 0) * 100)}%</span></div></div>
      <div id="usage-chart"></div>
    </div>
    <div class="card">
      <div class="card-head"><div class="card-title">${icon("swap")} How the codes changed</div></div>
      <div id="mapping-donut"></div>
    </div>
  </div>

  <div class="grid g-3 mt">
    <div class="card">
      <div class="card-head"><div><div class="card-title">${icon("sparkles")} New offences in BNS 2023</div><div class="card-sub">No IPC predecessor in the NCRB table</div></div></div>
      <div class="list">${corpus.new_offences.filter((o) => o.number !== "358").slice(0, 7).map((o) => `
        <div class="list-item" data-section="${esc(o.id)}" style="cursor:pointer"><div class="list-icon i-green">${icon("zap")}</div>
        <div style="min-width:0"><b>BNS ${esc(o.number)}</b> · ${esc(o.heading)}<div class="faint" style="font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(o.snippet.slice(0, 90))}</div></div></div>`).join("")}</div>
    </div>
    <div class="card">
      <div class="card-head"><div><div class="card-title">${icon("target")} Most cited sections</div><div class="card-sub">Top sources behind your answers</div></div></div>
      <div id="top-sections">${usage.top_sections.length ? "" : empty("Ask a few questions and the sections the assistant relies on will appear here.")}</div>
    </div>
    <div class="card">
      <div class="card-head"><div class="card-title">${icon("clock")} Recent activity</div></div>
      <div class="list">${usage.activity.length ? usage.activity.slice(0, 7).map((a) => {
        const [ic, cls] = KIND_ICON[a.kind] || ["info", "i-sky"];
        return `<div class="list-item"><div class="list-icon ${cls}">${icon(ic)}</div><div style="min-width:0;flex:1"><div style="font-weight:600;font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(a.title)}</div><div class="faint" style="font-size:12px">${esc(a.detail || a.kind)} · ${timeAgo(a.created_at)}</div></div></div>`;
      }).join("") : empty("Your activity will appear here.")}</div>
    </div>
  </div>

  <div class="grid g-2 mt">
    <div class="card">
      <div class="card-head"><div><div class="card-title">${icon("book")} The six codes</div><div class="card-sub">Repealed codes and their 2023 replacements</div></div></div>
      <div class="table-wrap"><table><thead><tr><th>Code</th><th>Name</th><th>Year</th><th>Sections</th><th>Status</th></tr></thead><tbody>
      ${["BNS", "BNSS", "BSA", "IPC", "CrPC", "IEA"].map((c) => corpus.per_act[c] !== undefined ? row(c, corpus) : "").join("")}
      </tbody></table></div>
    </div>
    <div class="card">
      <div class="card-head"><div><div class="card-title">${icon("flask")} Trial courts for BNS offences</div><div class="card-sub">Which court tries each scheduled offence</div></div></div>
      <div id="courts-chart"></div>
    </div>
  </div>`;

  el.querySelectorAll("[data-count]").forEach((n) => animateCount(n, +n.dataset.count));

  barChart($("#chapters-chart", el), corpus.bns_chapters.map((c) => ({
    label: c.chapter.replace("CHAPTER ", ""), full: `${c.chapter} · ${title(c.name)}`, value: c.sections, chapter: c.chapter,
  })), { height: 250, valueLabel: "sections", onClick: (it) => { location.hash = `#/library?act=BNS&chapter=${encodeURIComponent(it.chapter)}`; } });

  const ordered = (obj, keys) => keys.filter((k) => obj[k]).map((k) => [k, obj[k]]);
  donut($("#cog-donut", el), ordered(corpus.cognizable, ["Cognizable", "Non-cognizable", "Depends"]).map(([k, v], i) => ({ label: k, value: v, color: ["#ff9933", "#8b5cf6", "#5f6a91"][i] })),
    { size: 130, thickness: 18, center: fmt(corpus.classified_offences), sub: "offences" });
  donut($("#bail-donut", el), ordered(corpus.bailable, ["Bailable", "Non-bailable", "Depends"]).map(([k, v], i) => ({ label: k, value: v, color: ["#14b8a6", "#f43f5e", "#5f6a91"][i] })),
    { size: 130, thickness: 18, center: `${Math.round(((corpus.bailable["Non-bailable"] || 0) / corpus.classified_offences) * 100)}%`, sub: "non-bailable" });

  areaChart($("#usage-chart", el), usage.per_day.map((d) => ({
    label: new Date(d.day).toLocaleDateString("en-IN", { day: "numeric", month: "short" }), full: d.day, value: d.queries,
  })), { label: "questions", height: 230 });

  const types = corpus.mapping_types;
  const sum = (suffix) => Object.entries(types).filter(([k]) => k.endsWith(suffix)).reduce((a, [, v]) => a + v, 0);
  donut($("#mapping-donut", el), [
    { label: "Carried over (1 → 1)", value: sum(":direct"), color: "#ff9933" },
    { label: "Merged (many → 1)", value: sum(":merged"), color: "#8b5cf6" },
    { label: "Modified", value: sum(":modified"), color: "#38bdf8" },
    { label: "Brand-new provisions", value: sum(":new_provision"), color: "#22c55e" },
  ], { size: 150, center: fmt(corpus.mappings), sub: "sections" });

  if (usage.top_sections.length) {
    barChart($("#top-sections", el), usage.top_sections.map(([id, n]) => ({ label: id.replace("-", " "), value: n })), { horizontal: true, valueLabel: "answers" });
  }
  barChart($("#courts-chart", el), Object.entries(corpus.courts).map(([k, v], i) => ({ label: k, value: v, color: color(i) })), { horizontal: true, valueLabel: "offences" });
}

function stat(label, value, ic, cls, sub, extra = "") {
  return `<div class="card stat"><div class="stat-icon ${cls}">${icon(ic)}</div><div><div class="stat-value" data-count="${value}">0</div><div class="stat-label">${label}</div><div class="faint" style="font-size:12px;margin-top:4px">${sub}</div></div><div class="sparkline">${extra}</div></div>`;
}

function row(code, corpus) {
  const meta = { BNS: ["Bharatiya Nyaya Sanhita", 2023, "new"], BNSS: ["Bharatiya Nagarik Suraksha Sanhita", 2023, "new"], BSA: ["Bharatiya Sakshya Adhiniyam", 2023, "new"],
    IPC: ["Indian Penal Code", 1860, "old"], CrPC: ["Code of Criminal Procedure", 1973, "old"], IEA: ["Indian Evidence Act", 1872, "old"] }[code];
  return `<tr><td><a class="link" href="#/library?act=${code}">${code}</a></td><td>${meta[0]}</td><td>${meta[1]}</td><td>${fmt(corpus.per_act[code])}</td><td><span class="tag ${meta[2] === "new" ? "tag-new" : "tag-old"}">${meta[2] === "new" ? "In force" : "Repealed"}</span></td></tr>`;
}

const title = (s) => (s || "").toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());
const empty = (t) => `<div class="empty" style="padding:24px 10px">${icon("info")}<div style="font-size:12.5px">${t}</div></div>`;
const skeleton = () => `<div class="skeleton" style="height:180px;border-radius:22px"></div><div class="grid g-4 mt">${'<div class="skeleton" style="height:110px"></div>'.repeat(4)}</div><div class="grid g-main mt"><div class="skeleton" style="height:320px"></div><div class="skeleton" style="height:320px"></div></div>`;
