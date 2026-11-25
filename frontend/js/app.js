// App shell: authentication, layout, hash router and command palette.
import { auth, get, post } from "./api.js";
import { $, esc, icon, openSection, toast } from "./ui.js";
import * as dashboard from "./pages/dashboard.js";
import * as assistant from "./pages/assistant.js";
import * as converter from "./pages/converter.js";
import * as predictorPage from "./pages/predictor.js";
import * as documents from "./pages/documents.js";
import * as library from "./pages/library.js";
import * as graphPage from "./pages/graph.js";
import * as evaluation from "./pages/evaluation.js";
import * as settingsPage from "./pages/settings.js";

const ROUTES = {
  dashboard: { page: dashboard, title: "Dashboard", crumb: "Overview of the legal corpus and your activity", icon: "dashboard", group: "Workspace" },
  assistant: { page: assistant, title: "AI Legal Assistant", crumb: "Ask in English, Hindi or Hinglish. Answers cite the exact section", icon: "chat", group: "Workspace", badge: "AI" },
  converter: { page: converter, title: "IPC → BNS Converter", crumb: "Old section numbers to the 2023 codes, with a word-level diff", icon: "swap", group: "Workspace" },
  predictor: { page: predictorPage, title: "Section Predictor", crumb: "Describe an incident; a trained ML model suggests the sections that may apply", icon: "target", group: "Workspace", badge: "ML" },
  documents: { page: documents, title: "Document Analyzer", crumb: "Extract text from FIRs, judgments and notices; detect and convert sections", icon: "file", group: "Workspace", badge: "PDF" },
  library: { page: library, title: "Law Library", crumb: "Browse all 2,354 sections of the six criminal codes", icon: "book", group: "Explore" },
  graph: { page: graphPage, title: "Knowledge Graph", crumb: "How the old codes map onto BNS, BNSS and BSA", icon: "graph", group: "Explore" },
  evaluation: { page: evaluation, title: "Evaluation Lab", crumb: "Benchmark of retrieval methods on a labelled question set", icon: "flask", group: "Research" },
  settings: { page: settingsPage, title: "Settings", crumb: "AI model, connection status and account", icon: "settings", group: "Research" },
};

let current = null;
export const state = { health: null };

// ------------------------------------------------------------------ theme
const savedTheme = localStorage.getItem("nyayasetu.theme");
if (savedTheme === "light") document.documentElement.classList.add("light");
function toggleTheme() {
  const light = document.documentElement.classList.toggle("light");
  localStorage.setItem("nyayasetu.theme", light ? "light" : "dark");
  route();
}

// ------------------------------------------------------------------ auth screen
function renderAuth(mode = "login") {
  const root = $("#root");
  root.innerHTML = `
  <div class="auth">
    <div class="auth-art">
      <div class="orbit"></div>
      <div class="brand" style="padding:0">
        <div class="brand-logo">${icon("scale")}</div>
        <div><div class="brand-name">NyayaSetu</div><div class="brand-sub" style="color:#aab4d8">न्याय सेतु · Bridge to Justice</div></div>
      </div>
      <div style="position:relative;z-index:1">
        <h1>India changed its criminal laws. <span>Understand them in seconds.</span></h1>
        <p>On 1 July 2024 the IPC, CrPC and Evidence Act were replaced by the Bharatiya Nyaya Sanhita, Bharatiya Nagarik Suraksha Sanhita and Bharatiya Sakshya Adhiniyam. NyayaSetu answers legal questions in English and Hindi with verified citations, converts old sections, and reads your legal documents.</p>
        <div class="auth-feats">
          <div class="auth-feat"><b>2,354 sections</b>Full text of all six codes</div>
          <div class="auth-feat"><b>1,059 mappings</b>Old → new, official NCRB table</div>
          <div class="auth-feat"><b>Groq-powered AI</b>Streaming answers with citations</div>
          <div class="auth-feat"><b>PDF analyzer</b>Detects & converts sections in FIRs</div>
        </div>
      </div>
      <div style="font-size:12px;color:#7d88b0;position:relative">Legal information, not legal advice. Statutory text: Gazette of India.</div>
    </div>
    <div class="auth-form">
      <form class="auth-box" id="auth-form" autocomplete="on">
        <h2>${mode === "login" ? "Welcome back" : "Create your account"}</h2>
        <p class="muted" style="margin:0 0 22px">${mode === "login" ? "Sign in to continue to your legal workspace." : "It takes less than a minute."}</p>
        ${mode === "register" ? `<label class="label">Full name</label><input class="input" name="name" required minlength="2" placeholder="Aarav Sharma"/><div style="height:14px"></div>` : ""}
        <label class="label">Email</label>
        <input class="input" name="email" type="email" required placeholder="you@example.com" value="${mode === "login" ? "demo@nyayasetu.in" : ""}"/>
        <div style="height:14px"></div>
        <label class="label">Password</label>
        <input class="input" name="password" type="password" required minlength="6" placeholder="••••••••" value="${mode === "login" ? "demo1234" : ""}"/>
        <button class="btn btn-primary" style="width:100%;margin-top:20px;padding:13px" type="submit">${mode === "login" ? "Sign in" : "Create account"} ${icon("arrow")}</button>
        <p class="muted" style="text-align:center;margin-top:16px">${mode === "login" ? "New here?" : "Already have an account?"} <a class="link" id="switch">${mode === "login" ? "Create an account" : "Sign in"}</a></p>
        ${mode === "login" ? `<div class="demo-box"><b>Demo account</b> is pre-filled: demo@nyayasetu.in / demo1234</div>` : ""}
      </form>
    </div>
  </div>`;
  $("#switch").onclick = () => renderAuth(mode === "login" ? "register" : "login");
  $("#auth-form").onsubmit = async (e) => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    const btn = e.target.querySelector("button[type=submit]");
    btn.disabled = true; btn.innerHTML = `<span class="spinner"></span>`;
    try {
      const res = await post(`/api/auth/${mode === "login" ? "login" : "register"}`, fd);
      auth.save(res.token, res.user);
      toast(`Welcome, ${res.user.name.split(" ")[0]}!`);
      boot();
    } catch (err) {
      toast(err.message, "error");
      btn.disabled = false; btn.innerHTML = `${mode === "login" ? "Sign in" : "Create account"} ${icon("arrow")}`;
    }
  };
}

// ------------------------------------------------------------------ layout
function renderShell() {
  const user = auth.user || { name: "User" };
  const groups = {};
  for (const [key, r] of Object.entries(ROUTES)) (groups[r.group] ||= []).push([key, r]);
  $("#root").innerHTML = `
  <div class="app">
    <aside class="sidebar">
      <div class="brand"><div class="brand-logo">${icon("scale")}</div><div><div class="brand-name">NyayaSetu</div><div class="brand-sub">न्याय सेतु · Legal AI</div></div></div>
      ${Object.entries(groups).map(([g, items]) => `<div class="nav-label">${g}</div>${items.map(([key, r]) => `<a class="nav-item" href="#/${key}" data-route="${key}">${icon(r.icon)}<span>${r.title.replace(" → ", " → ")}</span>${r.badge ? `<span class="nav-badge">${r.badge}</span>` : ""}</a>`).join("")}`).join("")}
      <div class="sidebar-foot"><div class="status-card" id="status-card"><span class="status-dot"></span>Checking AI engine…</div></div>
    </aside>
    <div class="main">
      <header class="topbar">
        <div><h1 id="page-title">Dashboard</h1><div class="crumb" id="page-crumb"></div></div>
        <div class="search-trigger" id="palette-btn">${icon("search")}<span>Search sections, e.g. "IPC 420" or "dowry"</span><span class="kbd">Ctrl K</span></div>
        <button class="icon-btn" id="theme-btn" title="Toggle theme">${icon(document.documentElement.classList.contains("light") ? "moon" : "sun")}</button>
        <div class="avatar" id="avatar" title="${esc(user.name)}">${esc((user.name || "U").trim()[0].toUpperCase())}</div>
      </header>
      <main class="view" id="view"></main>
    </div>
  </div>`;
  $("#theme-btn").onclick = toggleTheme;
  $("#palette-btn").onclick = openPalette;
  $("#avatar").onclick = () => { location.hash = "#/settings"; };
  refreshStatus();
}

export async function refreshStatus() {
  try {
    state.health = await get("/api/health");
    const el = $("#status-card");
    if (!el) return;
    el.innerHTML = state.health.llm_configured
      ? `<span class="status-dot ok"></span><b style="color:var(--text)">AI online</b><div style="margin-top:4px">Groq · ${esc(state.health.model)}</div>`
      : `<span class="status-dot"></span><b style="color:var(--text)">Offline mode</b><div style="margin-top:4px">Add GROQ_API_KEY in .env for AI answers</div>`;
  } catch { /* ignore */ }
}

async function route() {
  if (!auth.token) return renderAuth();
  if (!$(".app")) renderShell();
  const [path, query] = (location.hash.replace(/^#\/?/, "") || "dashboard").split("?");
  const key = ROUTES[path] ? path : "dashboard";
  const r = ROUTES[key];
  document.querySelectorAll(".nav-item").forEach((a) => a.classList.toggle("active", a.dataset.route === key));
  $("#page-title").textContent = r.title;
  $("#page-crumb").textContent = r.crumb;
  document.title = `${r.title} · NyayaSetu`;
  current?.page.unmount?.();
  current = r;
  const view = $("#view");
  view.scrollTop = 0;
  view.innerHTML = `<div class="view-inner"></div>`;
  try {
    await r.page.render(view.firstElementChild, new URLSearchParams(query || ""));
  } catch (e) {
    console.error(e);
    view.firstElementChild.innerHTML = `<div class="card empty">${icon("alert")}<div><b>Something went wrong</b></div><div>${esc(e.message)}</div></div>`;
  }
}

// ------------------------------------------------------------------ command palette
function openPalette() {
  const ov = document.createElement("div");
  ov.className = "overlay";
  ov.innerHTML = `<div class="palette"><input placeholder="Search 2,354 sections. Try: IPC 302, धोखाधड़ी, anticipatory bail" autofocus/><div class="palette-results"><div class="muted" style="padding:14px">Type to search all six codes. Press Enter to open the first result.</div></div></div>`;
  document.body.appendChild(ov);
  const input = ov.querySelector("input");
  const results = ov.querySelector(".palette-results");
  let items = [], sel = 0, timer;
  const close = () => ov.remove();
  ov.addEventListener("click", (e) => { if (e.target === ov) close(); });
  const draw = () => {
    results.innerHTML = items.length ? items.map((r, i) => `<div class="palette-item ${i === sel ? "sel" : ""}" data-i="${i}">
      <span class="tag ${["BNS", "BNSS", "BSA"].includes(r.act) ? "tag-new" : "tag-old"}">${esc(r.act)}</span>
      <div style="min-width:0"><b>${esc(r.act)} ${esc(r.number)}</b> · ${esc(r.heading)}<div class="faint" style="font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(r.snippet.slice(0, 120))}</div></div></div>`).join("")
      : `<div class="muted" style="padding:14px">No matches.</div>`;
    results.querySelectorAll(".palette-item").forEach((el) => el.onclick = () => { close(); openSection(items[+el.dataset.i].id); });
  };
  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      if (!input.value.trim()) return;
      try { items = (await get("/api/search", { q: input.value, k: 8 })).results; sel = 0; draw(); } catch (e) { toast(e.message, "error"); }
    }, 160);
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Escape") close();
    if (e.key === "ArrowDown") { sel = Math.min(items.length - 1, sel + 1); draw(); e.preventDefault(); }
    if (e.key === "ArrowUp") { sel = Math.max(0, sel - 1); draw(); e.preventDefault(); }
    if (e.key === "Enter" && items[sel]) { close(); openSection(items[sel].id); }
  });
  setTimeout(() => input.focus(), 10);
}

document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k" && auth.token) { e.preventDefault(); openPalette(); }
});

export function logout() {
  auth.clear();
  current?.page.unmount?.();
  current = null;
  renderAuth();
}

window.addEventListener("auth:expired", () => { toast("Session expired. Please sign in again.", "info"); renderAuth(); });
window.addEventListener("hashchange", route);

async function boot() {
  if (auth.token) {
    try { await get("/api/auth/me"); } catch { auth.clear(); }
  }
  $("#root").innerHTML = "";
  route();
}
boot();
