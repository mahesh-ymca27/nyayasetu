// Force-directed knowledge-graph renderer on <canvas> (no libraries).
// Supports pan (drag background), zoom (wheel), node drag, hover highlight and click selection.

const ACT_COLORS = { BNS: "#ff9933", BNSS: "#f59e0b", BSA: "#fb7185", IPC: "#818cf8", CrPC: "#38bdf8", IEA: "#2dd4bf" };

export function nodeColor(n) {
  if (n.is_new) return "#22c55e";
  return ACT_COLORS[n.act || n.id] || "#a78bfa";
}

export class ForceGraph {
  constructor(canvas, { onSelect } = {}) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.onSelect = onSelect;
    this.nodes = [];
    this.edges = [];
    this.view = { x: 0, y: 0, k: 1 };
    this.hover = null;
    this.selected = null;
    this.alpha = 1;
    this._bind();
    this._resize();
    this._ro = new ResizeObserver(() => this._resize());
    this._ro.observe(canvas);
    this._loop = this._loop.bind(this);
    this._raf = requestAnimationFrame(this._loop);
  }

  destroy() { cancelAnimationFrame(this._raf); this._ro.disconnect(); }

  setData({ nodes, edges }) {
    const w = this.w, h = this.h;
    const byId = new Map();
    this.nodes = nodes.map((n, i) => {
      const a = (i / Math.max(1, nodes.length)) * Math.PI * 2;
      const rad = 60 + Math.random() * Math.min(w, h) * 0.35;
      const node = { ...n, x: Math.cos(a) * rad, y: Math.sin(a) * rad, vx: 0, vy: 0,
        r: n.type === "act" ? 14 + Math.sqrt(n.size || 1) * 0.7 : n.type === "chapter" ? 7 + Math.sqrt(n.size || 1) * 1.2 : n.focus ? 11 : 6 };
      byId.set(n.id, node);
      return node;
    });
    this.byId = byId;
    this.edges = edges.map((e) => ({ ...e, s: byId.get(e.source), t: byId.get(e.target) })).filter((e) => e.s && e.t);
    this.neighbors = new Map(this.nodes.map((n) => [n.id, new Set()]));
    this.edges.forEach((e) => { this.neighbors.get(e.s.id).add(e.t.id); this.neighbors.get(e.t.id).add(e.s.id); });
    this.view = { x: 0, y: 0, k: nodes.length > 100 ? 0.75 : nodes.length > 50 ? 0.9 : 1.1 };
    this.alpha = 1;
    this.selected = null;
  }

  focus(id) {
    const n = this.byId?.get(id);
    if (!n) return;
    this.selected = n;
    this.view.x = -n.x * this.view.k;
    this.view.y = -n.y * this.view.k;
    this.onSelect?.(n);
  }

  _resize() {
    const dpr = window.devicePixelRatio || 1;
    const r = this.canvas.getBoundingClientRect();
    this.w = r.width; this.h = r.height;
    this.canvas.width = r.width * dpr; this.canvas.height = r.height * dpr;
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  _tick() {
    const N = this.nodes, a = this.alpha;
    if (a < 0.005) return;
    const rep = N.length > 150 ? 900 : 1600;
    for (let i = 0; i < N.length; i++) {
      const p = N[i];
      for (let j = i + 1; j < N.length; j++) {
        const q = N[j];
        let dx = p.x - q.x, dy = p.y - q.y, d2 = dx * dx + dy * dy + 0.01;
        if (d2 > 160000) continue;
        const f = (rep * a) / d2;
        dx *= f; dy *= f;
        p.vx += dx; p.vy += dy; q.vx -= dx; q.vy -= dy;
      }
    }
    for (const e of this.edges) {
      const dx = e.t.x - e.s.x, dy = e.t.y - e.s.y, d = Math.sqrt(dx * dx + dy * dy) || 1;
      const L = e.type === "contains" ? 70 : e.type === "replaced_by" ? 55 : 80;
      const f = ((d - L) / d) * 0.06 * a;
      e.s.vx += dx * f; e.s.vy += dy * f; e.t.vx -= dx * f; e.t.vy -= dy * f;
    }
    for (const n of N) {
      n.vx -= n.x * 0.004 * a; n.vy -= n.y * 0.004 * a;
      if (n === this.dragNode) { n.vx = n.vy = 0; continue; }
      n.vx *= 0.82; n.vy *= 0.82;
      n.x += Math.max(-30, Math.min(30, n.vx)); n.y += Math.max(-30, Math.min(30, n.vy));
    }
    this.alpha *= 0.985;
  }

  _draw() {
    const { ctx, w, h, view } = this;
    const light = document.documentElement.classList.contains("light");
    ctx.clearRect(0, 0, w, h);
    ctx.save();
    ctx.translate(w / 2 + view.x, h / 2 + view.y);
    ctx.scale(view.k, view.k);
    const active = this.hover || this.selected;
    const near = active ? this.neighbors.get(active.id) : null;
    for (const e of this.edges) {
      const on = active && (e.s === active || e.t === active);
      ctx.globalAlpha = active ? (on ? 0.95 : 0.08) : 0.35;
      ctx.strokeStyle = e.type === "replaced_by" ? (e.mapping === "auto-aligned" ? "#38bdf8" : "#ff9933") : light ? "#9aa3c7" : "#5f6a91";
      ctx.lineWidth = (e.type === "replaced_by" ? 1.6 : 1) / Math.sqrt(view.k) * (on ? 1.6 : 1);
      if (e.type === "same_chapter") ctx.setLineDash([4, 4]); else ctx.setLineDash([]);
      ctx.beginPath(); ctx.moveTo(e.s.x, e.s.y); ctx.lineTo(e.t.x, e.t.y); ctx.stroke();
      if (e.type === "replaced_by") {
        const ang = Math.atan2(e.t.y - e.s.y, e.t.x - e.s.x), tx = e.t.x - Math.cos(ang) * (e.t.r + 3), ty = e.t.y - Math.sin(ang) * (e.t.r + 3);
        ctx.beginPath(); ctx.moveTo(tx, ty);
        ctx.lineTo(tx - Math.cos(ang - 0.4) * 7, ty - Math.sin(ang - 0.4) * 7);
        ctx.lineTo(tx - Math.cos(ang + 0.4) * 7, ty - Math.sin(ang + 0.4) * 7);
        ctx.closePath(); ctx.fillStyle = ctx.strokeStyle; ctx.fill();
      }
    }
    ctx.setLineDash([]);
    for (const n of this.nodes) {
      const dim = active && n !== active && !near.has(n.id);
      ctx.globalAlpha = dim ? 0.15 : 1;
      const c = nodeColor(n);
      if (n === active || n.focus) {
        ctx.beginPath(); ctx.arc(n.x, n.y, n.r + 7, 0, Math.PI * 2); ctx.fillStyle = c + "33"; ctx.fill();
      }
      ctx.beginPath(); ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
      const g = ctx.createRadialGradient(n.x - n.r / 3, n.y - n.r / 3, 1, n.x, n.y, n.r);
      g.addColorStop(0, "#ffffff"); g.addColorStop(0.25, c); g.addColorStop(1, c);
      ctx.fillStyle = n.type === "section" && n.era === "old" ? c : g;
      ctx.fill();
      ctx.lineWidth = 1.5; ctx.strokeStyle = light ? "#fff" : "#0b1020"; ctx.stroke();
      const showLabel = n.type !== "section" || view.k > 0.9 || n === active || (near && near.has(n.id)) || this.nodes.length < 90;
      if (showLabel) {
        ctx.font = `${n.type === "act" ? 700 : 600} ${n.type === "act" ? 13 : 10.5}px Inter, sans-serif`;
        ctx.textAlign = "center";
        ctx.fillStyle = light ? "#141a33" : "#e8ecfb";
        ctx.fillText(n.label, n.x, n.y + n.r + 13);
      }
    }
    ctx.restore();
    ctx.globalAlpha = 1;
  }

  _loop() { this._tick(); this._draw(); this._raf = requestAnimationFrame(this._loop); }

  _toWorld(ev) {
    const r = this.canvas.getBoundingClientRect();
    return { x: (ev.clientX - r.left - this.w / 2 - this.view.x) / this.view.k, y: (ev.clientY - r.top - this.h / 2 - this.view.y) / this.view.k };
  }

  _pick(ev) {
    const p = this._toWorld(ev);
    let best = null, bd = Infinity;
    for (const n of this.nodes) {
      const d = (n.x - p.x) ** 2 + (n.y - p.y) ** 2;
      if (d < (n.r + 5) ** 2 && d < bd) { best = n; bd = d; }
    }
    return best;
  }

  _bind() {
    const c = this.canvas;
    let panning = null, moved = false;
    c.addEventListener("mousedown", (ev) => {
      moved = false;
      const n = this._pick(ev);
      if (n) { this.dragNode = n; this.alpha = Math.max(this.alpha, 0.3); }
      else panning = { x: ev.clientX - this.view.x, y: ev.clientY - this.view.y };
    });
    window.addEventListener("mousemove", (ev) => {
      if (this.dragNode) { const p = this._toWorld(ev); this.dragNode.x = p.x; this.dragNode.y = p.y; moved = true; this.alpha = Math.max(this.alpha, 0.2); }
      else if (panning) { this.view.x = ev.clientX - panning.x; this.view.y = ev.clientY - panning.y; moved = true; }
      else if (ev.target === c) { this.hover = this._pick(ev); c.style.cursor = this.hover ? "pointer" : "grab"; }
    });
    window.addEventListener("mouseup", (ev) => {
      if (!moved && ev.target === c) {
        const n = this._pick(ev);
        this.selected = n;
        this.onSelect?.(n);
      }
      this.dragNode = null; panning = null;
    });
    c.addEventListener("wheel", (ev) => {
      ev.preventDefault();
      const k = Math.max(0.25, Math.min(3, this.view.k * (ev.deltaY < 0 ? 1.12 : 0.89)));
      const r = c.getBoundingClientRect();
      const mx = ev.clientX - r.left - this.w / 2, my = ev.clientY - r.top - this.h / 2;
      this.view.x = mx - ((mx - this.view.x) * k) / this.view.k;
      this.view.y = my - ((my - this.view.y) * k) / this.view.k;
      this.view.k = k;
    }, { passive: false });
  }

  zoom(f) { this.view.k = Math.max(0.25, Math.min(3, this.view.k * f)); }
  reheat() { this.alpha = 1; }
  reset() { this.view = { x: 0, y: 0, k: 1 }; }
}
