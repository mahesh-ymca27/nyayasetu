import { get, stream } from "../api.js";
import { $, esc, icon, markdown, toast } from "../ui.js";

const KEY = "nyayasetu.chat";
const SUGGESTIONS = [
  ["What replaced IPC 420?", "Cheating under the new BNS"],
  ["Mob lynching ki saza kya hai naye kanoon mein?", "Hinglish question"],
  ["दहेज के लिए पत्नी के साथ क्रूरता पर कौन सी धारा लगती है?", "Hindi question"],
  ["Police is refusing to register my FIR. What can I do?", "Procedure under BNSS"],
  ["Is a WhatsApp chat valid evidence in court?", "Electronic evidence under BSA"],
  ["How do I get anticipatory bail?", "BNSS section 482"],
];

let controller = null;
let messages = [];

export function unmount() { controller?.abort(); window.speechSynthesis?.cancel(); }

export async function render(el, params) {
  messages = JSON.parse(sessionStorage.getItem(KEY) || "[]");
  el.innerHTML = `
  <div class="chat-layout">
    <div class="card chat-card">
      <div class="row between" style="padding:14px 18px;border-bottom:1px solid var(--border)">
        <div class="row"><div class="list-icon i-saffron">${icon("sparkles")}</div><div><b>NyayaSetu Assistant</b><div class="faint" style="font-size:12px">Retrieval-augmented answers from the statute text</div></div></div>
        <div class="row">
          <select class="select" id="lang" style="width:auto;padding:8px 12px">
            <option value="en">English</option><option value="hi">हिन्दी (Hindi)</option><option value="hinglish">Hinglish</option>
          </select>
          <button class="btn btn-sm" id="export" title="Print or save as PDF">${icon("printer")}</button>
          <button class="btn btn-sm" id="clear" title="New chat">${icon("refresh")} New chat</button>
        </div>
      </div>
      <div class="chat-scroll" id="chat"></div>
      <form class="composer" id="composer">
        <button type="button" class="icon-btn" id="mic" title="Speak your question">${icon("mic")}</button>
        <textarea class="textarea" id="q" rows="1" placeholder="Ask about BNS, BNSS or BSA… e.g. 'What is the punishment for snatching?'"></textarea>
        <button class="btn btn-primary" id="send" type="submit" style="height:48px">${icon("send")} Ask</button>
      </form>
    </div>
    <div class="stack" style="overflow-y:auto">
      <div class="card">
        <div class="card-title" style="margin-bottom:12px">${icon("zap")} Answer pipeline</div>
        <div class="pipeline" id="pipeline">${pipeline(0)}</div>
        <div id="pipe-meta" class="faint" style="font-size:12px;margin-top:12px"></div>
      </div>
      <div class="card">
        <div class="card-head" style="margin-bottom:10px"><div class="card-title">${icon("book")} Retrieved sources</div><span class="chip" id="src-count">0</span></div>
        <div class="stack" id="sources"><div class="faint" style="font-size:12.5px">Sources used for the latest answer will appear here. Click one to read the full section.</div></div>
      </div>
    </div>
  </div>`;

  const lang = $("#lang", el);
  lang.value = localStorage.getItem("nyayasetu.lang") || "en";
  lang.onchange = () => localStorage.setItem("nyayasetu.lang", lang.value);
  const q = $("#q", el);
  q.addEventListener("input", () => { q.style.height = "auto"; q.style.height = Math.min(160, q.scrollHeight) + "px"; });
  q.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#composer").requestSubmit(); } });
  $("#composer", el).onsubmit = (e) => { e.preventDefault(); ask(q.value); };
  $("#clear", el).onclick = () => { controller?.abort(); messages = []; persist(); draw(); resetSide(); };
  $("#export", el).onclick = () => window.print();
  setupMic($("#mic", el), q, lang);
  draw();
  const preset = params.get("q");
  if (preset) ask(preset);
}

function persist() { sessionStorage.setItem(KEY, JSON.stringify(messages.slice(-30))); }

function draw() {
  const chat = $("#chat");
  if (!chat) return;
  if (!messages.length) {
    chat.innerHTML = `<div style="margin:auto;max-width:720px;width:100%;text-align:center;padding:20px 0">
      <div class="brand-logo" style="margin:0 auto 14px;width:58px;height:58px;border-radius:16px">${icon("scale")}</div>
      <h2 style="margin:0 0 6px;letter-spacing:-.02em">Ask anything about India's new criminal laws</h2>
      <p class="muted" style="margin:0">Every answer is grounded in the official text and cites the exact section. You can ask in English, हिन्दी or Hinglish.</p>
      <div class="suggestions">${SUGGESTIONS.map(([s, sub]) => `<button class="suggestion" data-q="${esc(s)}"><b>${esc(s)}</b><span class="faint" style="font-size:12px">${esc(sub)}</span></button>`).join("")}</div></div>`;
    chat.querySelectorAll(".suggestion").forEach((b) => b.onclick = () => ask(b.dataset.q));
    return;
  }
  chat.innerHTML = messages.map((m, i) => bubble(m, i)).join("");
  chat.querySelectorAll("[data-copy]").forEach((b) => b.onclick = () => { navigator.clipboard?.writeText(messages[+b.dataset.copy].content); toast("Answer copied"); });
  chat.querySelectorAll("[data-speak]").forEach((b) => b.onclick = () => speak(messages[+b.dataset.speak]));
  chat.scrollTop = chat.scrollHeight;
}

function bubble(m, i) {
  if (m.role === "user") return `<div class="msg user"><div class="msg-avatar">${icon("user")}</div><div class="bubble">${esc(m.content)}</div></div>`;
  const ids = m.sources ? new Set(m.sources.map((s) => s.id)) : null;
  const v = m.verification;
  const body = m.content ? markdown(m.content, ids) : `<div class="typing"><span></span><span></span><span></span></div>`;
  const meta = v ? `<div class="msg-meta">
      <span class="chip" style="border-color:${v.total && v.grounded === v.total ? "rgba(34,197,94,.5)" : "rgba(245,158,11,.5)"}">${icon("shield")} ${v.grounded}/${v.total} citations verified</span>
      <span class="chip">${icon("clock")} ${(m.latency_ms / 1000).toFixed(1)}s</span>
      <span class="chip">${icon("zap")} ${m.mode === "groq" ? "Groq AI" : "Offline"}</span>
      <button class="chip click" data-copy="${i}">${icon("copy")} Copy</button>
      <button class="chip click" data-speak="${i}">${icon("mic")} Listen</button></div>` : "";
  const err = m.error ? `<div class="chip" style="margin-top:8px;border-color:rgba(244,63,94,.5)">${icon("alert")} ${esc(m.error)}</div>` : "";
  return `<div class="msg bot"><div class="msg-avatar">${icon("scale")}</div><div style="min-width:0"><div class="bubble">${body}</div>${err}${meta}</div></div>`;
}

function pipeline(stage) {
  const steps = ["Understand query (Hindi/Hinglish vocabulary, LLM rewrite)", "Hybrid retrieval: BM25 + section references + old→new mapping", "Groq LLM drafts an answer from the retrieved sections", "Verify every citation against the corpus"];
  return steps.map((s, i) => `<div class="pipe-step ${i < stage ? "done" : i === stage && stage > 0 ? "run" : ""}"><span class="dot">${i < stage ? "✓" : i + 1}</span>${s}</div>`).join("");
}

function resetSide() {
  $("#pipeline").innerHTML = pipeline(0);
  $("#pipe-meta").innerHTML = "";
  $("#sources").innerHTML = `<div class="faint" style="font-size:12.5px">Sources used for the latest answer will appear here.</div>`;
  $("#src-count").textContent = "0";
}

function showSources(ev) {
  $("#src-count").textContent = ev.sources.length;
  $("#sources").innerHTML = ev.sources.map((s, i) => `<div class="source-card" data-section="${esc(s.id)}">
    <div class="row between"><span class="h"><span class="act-${esc(s.act)}">${esc(s.act)} ${esc(s.number)}</span> · ${esc(s.heading)}</span><span class="tag ${["BNS", "BNSS", "BSA"].includes(s.act) ? "tag-new" : "tag-old"}">#${i + 1}</span></div>
    <div class="s">${esc(s.snippet)}</div></div>`).join("");
  const bits = [`Retrieval took <b>${ev.retrieval_ms} ms</b>`];
  if (ev.added_terms?.length) bits.push(`Vocabulary added: <i>${esc(ev.added_terms.join(", "))}</i>`);
  if (ev.rewritten) bits.push(`LLM rewrite: <i>${esc(ev.rewritten)}</i>`);
  if (ev.references?.length) bits.push(`Detected references: ${ev.references.map((r) => `<b>${esc(r.label)}</b>${r.converted.length ? " → " + r.converted.map((c) => esc(c.id.replace("-", " "))).join(", ") : ""}`).join("; ")}`);
  $("#pipe-meta").innerHTML = bits.join("<br>");
}

async function ask(text) {
  text = (text || "").trim();
  if (!text || controller) return;
  const q = $("#q");
  q.value = ""; q.style.height = "auto";
  const history = messages.map(({ role, content }) => ({ role, content }));
  messages.push({ role: "user", content: text });
  const bot = { role: "assistant", content: "" };
  messages.push(bot);
  draw();
  $("#pipeline").innerHTML = pipeline(1);
  const send = $("#send");
  send.disabled = true; send.innerHTML = `<span class="spinner"></span>`;
  controller = new AbortController();
  let pending = false;
  const redraw = () => { if (!pending) { pending = true; requestAnimationFrame(() => { pending = false; draw(); }); } };
  try {
    await stream("/api/ask", { question: text, language: $("#lang").value, history }, (ev) => {
      if (ev.type === "sources") { bot.sources = ev.sources; showSources(ev); $("#pipeline").innerHTML = pipeline(2); }
      else if (ev.type === "token") { bot.content += ev.text; redraw(); }
      else if (ev.type === "error") { bot.error = ev.message; }
      else if (ev.type === "done") { bot.verification = ev.verification; bot.latency_ms = ev.latency_ms; bot.mode = ev.mode; $("#pipeline").innerHTML = pipeline(4); }
    }, controller.signal);
  } catch (e) {
    if (e.name !== "AbortError") { bot.content = bot.content || "Sorry, I could not answer that."; bot.error = e.message; toast(e.message, "error"); }
  } finally {
    controller = null;
    persist();
    draw();
    if (send.isConnected) { send.disabled = false; send.innerHTML = `${icon("send")} Ask`; }
  }
}

function setupMic(btn, input, lang) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { btn.title = "Voice input is not supported in this browser"; btn.style.opacity = 0.4; btn.onclick = () => toast("Voice input needs Chrome or Edge.", "info"); return; }
  let rec = null;
  btn.onclick = () => {
    if (rec) { rec.stop(); return; }
    rec = new SR();
    rec.lang = lang.value === "hi" ? "hi-IN" : "en-IN";
    rec.interimResults = true;
    rec.onresult = (e) => { input.value = [...e.results].map((r) => r[0].transcript).join(" "); };
    rec.onend = () => { rec = null; btn.style.color = ""; if (input.value.trim()) toast("Voice captured. Press Ask to send.", "info"); };
    rec.onerror = (e) => toast(`Voice input error: ${e.error}`, "error");
    btn.style.color = "var(--saffron)";
    rec.start();
  };
}

function speak(m) {
  const synth = window.speechSynthesis;
  if (!synth) return toast("Text-to-speech is not supported here.", "info");
  synth.cancel();
  const text = m.content.replace(/\[(\w+)\s+([\w()]+)\]/g, "$1 section $2").replace(/[*_`#]/g, "");
  const u = new SpeechSynthesisUtterance(text);
  u.lang = /[\u0900-\u097F]/.test(text) ? "hi-IN" : "en-IN";
  synth.speak(u);
}
