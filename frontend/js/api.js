// API client: JSON requests with bearer token, file upload and server-sent-event streaming.
const TOKEN_KEY = "nyayasetu.token";
const USER_KEY = "nyayasetu.user";

export const auth = {
  get token() { return localStorage.getItem(TOKEN_KEY); },
  get user() { try { return JSON.parse(localStorage.getItem(USER_KEY)); } catch { return null; } },
  save(token, user) { localStorage.setItem(TOKEN_KEY, token); localStorage.setItem(USER_KEY, JSON.stringify(user)); },
  clear() { localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(USER_KEY); },
};

export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

function headers(extra = {}) {
  const h = { ...extra };
  if (auth.token) h.Authorization = `Bearer ${auth.token}`;
  return h;
}

async function handle(res) {
  if (res.status === 401 && auth.token) {
    auth.clear();
    window.dispatchEvent(new Event("auth:expired"));
  }
  if (!res.ok) {
    let msg = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      msg = typeof body.detail === "string" ? body.detail : (body.detail?.[0]?.msg || msg);
    } catch { /* not JSON */ }
    throw new ApiError(msg, res.status);
  }
  const type = res.headers.get("content-type") || "";
  return type.includes("application/json") ? res.json() : res.text();
}

export async function get(path, params) {
  const url = new URL(path, location.origin);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (Array.isArray(v)) v.forEach((x) => url.searchParams.append(k, x));
      else if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, v);
    }
  }
  return handle(await fetch(url, { headers: headers() }));
}

export async function post(path, body) {
  return handle(await fetch(path, {
    method: "POST", headers: headers({ "Content-Type": "application/json" }), body: JSON.stringify(body ?? {}),
  }));
}

export async function del(path) {
  return handle(await fetch(path, { method: "DELETE", headers: headers() }));
}

export function upload(path, file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", path);
    if (auth.token) xhr.setRequestHeader("Authorization", `Bearer ${auth.token}`);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(e.loaded / e.total);
    xhr.onload = () => {
      let body = null;
      try { body = JSON.parse(xhr.responseText); } catch { /* ignore */ }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body);
      else reject(new ApiError(body?.detail || `Upload failed (${xhr.status})`, xhr.status));
    };
    xhr.onerror = () => reject(new ApiError("Network error during upload", 0));
    const fd = new FormData();
    fd.append("file", file);
    xhr.send(fd);
  });
}

export async function download(path, filename) {
  const res = await fetch(path, { headers: headers() });
  if (!res.ok) throw new ApiError(`Download failed (${res.status})`, res.status);
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

// POST that returns text/event-stream; calls onEvent(obj) for every `data:` line.
export async function stream(path, body, onEvent, signal) {
  const res = await fetch(path, {
    method: "POST", headers: headers({ "Content-Type": "application/json" }), body: JSON.stringify(body), signal,
  });
  if (!res.ok) return handle(res);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const chunk = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      for (const line of chunk.split("\n")) {
        if (line.startsWith("data:")) {
          try { onEvent(JSON.parse(line.slice(5).trim())); } catch { /* partial */ }
        }
      }
    }
  }
}
