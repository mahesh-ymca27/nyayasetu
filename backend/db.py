"""SQLite persistence: users, query log, analysed documents and activity feed."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager

from .config import settings

_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL DEFAULT 'citizen',
    password_hash TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS queries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    question TEXT NOT NULL,
    language TEXT,
    mode TEXT,
    top_section TEXT,
    sources TEXT,
    citation_score REAL,
    latency_ms REAL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    user_id INTEGER,
    filename TEXT NOT NULL,
    size_bytes INTEGER,
    pages INTEGER,
    words INTEGER,
    doc_type TEXT,
    references_count INTEGER,
    analysis TEXT,
    page_text TEXT,
    summary TEXT,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    detail TEXT,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_queries_time ON queries(created_at);
CREATE INDEX IF NOT EXISTS idx_activity_time ON activity(created_at);
"""


@contextmanager
def connect():
    with _lock:
        conn = sqlite3.connect(settings.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def init() -> None:
    with connect() as c:
        c.executescript(SCHEMA)
    if not get_user_by_email("demo@nyayasetu.in"):
        create_user("Demo User", "demo@nyayasetu.in", "demo1234", role="admin")


# ------------------------------------------------------------------ passwords & tokens
def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return f"pbkdf2_sha256$200000${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations))
    return hmac.compare_digest(digest.hex(), digest_hex)


def make_token(user_id: int) -> str:
    exp = int(time.time() + settings.token_ttl_hours * 3600)
    payload = f"{user_id}.{exp}"
    sig = hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(f"{payload}.{sig.hex()}".encode()).decode()


def read_token(token: str) -> int | None:
    try:
        user_id, exp, sig = base64.urlsafe_b64decode(token.encode()).decode().split(".")
    except (ValueError, UnicodeDecodeError):
        return None
    expected = hmac.new(settings.secret_key.encode(), f"{user_id}.{exp}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig) or int(exp) < time.time():
        return None
    return int(user_id)


# ------------------------------------------------------------------ users
def create_user(name: str, email: str, password: str, role: str = "citizen") -> dict:
    with connect() as c:
        cur = c.execute(
            "INSERT INTO users(name, email, role, password_hash, created_at) VALUES (?,?,?,?,?)",
            (name.strip(), email.strip().lower(), role, hash_password(password), time.time()),
        )
        uid = cur.lastrowid
    return get_user(uid)


def get_user(user_id: int) -> dict | None:
    with connect() as c:
        row = c.execute("SELECT id, name, email, role, created_at FROM users WHERE id=?", (user_id,)).fetchone()
    return dict(row) if row else None


def get_user_by_email(email: str) -> dict | None:
    with connect() as c:
        row = c.execute("SELECT * FROM users WHERE email=?", (email.strip().lower(),)).fetchone()
    return dict(row) if row else None


# ------------------------------------------------------------------ logging
def log_activity(user_id: int | None, kind: str, title: str, detail: str = "") -> None:
    with connect() as c:
        c.execute("INSERT INTO activity(user_id, kind, title, detail, created_at) VALUES (?,?,?,?,?)",
                  (user_id, kind, title[:200], detail[:500], time.time()))


def log_query(user_id: int | None, question: str, language: str, mode: str, sources: list[str],
              citation_score: float, latency_ms: float) -> None:
    with connect() as c:
        c.execute(
            "INSERT INTO queries(user_id, question, language, mode, top_section, sources, citation_score, latency_ms,"
            " created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (user_id, question[:1000], language, mode, sources[0] if sources else None, json.dumps(sources),
             citation_score, latency_ms, time.time()),
        )


def save_document(doc: dict) -> None:
    with connect() as c:
        c.execute(
            "INSERT OR REPLACE INTO documents(id, user_id, filename, size_bytes, pages, words, doc_type,"
            " references_count, analysis, page_text, summary, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (doc["id"], doc.get("user_id"), doc["filename"], doc["size_bytes"], doc["pages"], doc["words"],
             doc["doc_type"], doc["references_count"], json.dumps(doc["analysis"]), json.dumps(doc["page_text"]),
             json.dumps(doc.get("summary")) if doc.get("summary") else None, time.time()),
        )


def update_summary(doc_id: str, summary: dict) -> None:
    with connect() as c:
        c.execute("UPDATE documents SET summary=? WHERE id=?", (json.dumps(summary), doc_id))


def get_document(doc_id: str) -> dict | None:
    with connect() as c:
        row = c.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["analysis"] = json.loads(d["analysis"])
    d["page_text"] = json.loads(d["page_text"])
    d["summary"] = json.loads(d["summary"]) if d["summary"] else None
    return d


def list_documents(user_id: int | None, limit: int = 50) -> list[dict]:
    with connect() as c:
        rows = c.execute(
            "SELECT id, filename, size_bytes, pages, words, doc_type, references_count, created_at FROM documents"
            " WHERE user_id IS ? OR ? IS NULL ORDER BY created_at DESC LIMIT ?", (user_id, user_id, limit)
        ).fetchall()
    return [dict(r) for r in rows]


def delete_document(doc_id: str, user_id: int | None) -> bool:
    with connect() as c:
        cur = c.execute("DELETE FROM documents WHERE id=? AND (user_id IS ? OR ? IS NULL)", (doc_id, user_id, user_id))
    return cur.rowcount > 0


def recent_queries(user_id: int | None, limit: int = 20) -> list[dict]:
    with connect() as c:
        rows = c.execute(
            "SELECT question, language, mode, top_section, citation_score, latency_ms, created_at FROM queries"
            " WHERE user_id IS ? OR ? IS NULL ORDER BY created_at DESC LIMIT ?", (user_id, user_id, limit)
        ).fetchall()
    return [dict(r) for r in rows]


def usage_stats(days: int = 14) -> dict:
    now = time.time()
    start = now - days * 86400
    with connect() as c:
        q_rows = c.execute("SELECT created_at, latency_ms, citation_score, language, sources FROM queries "
                           "WHERE created_at >= ?", (start,)).fetchall()
        totals = {
            "queries": c.execute("SELECT COUNT(*) FROM queries").fetchone()[0],
            "documents": c.execute("SELECT COUNT(*) FROM documents").fetchone()[0],
            "pages": c.execute("SELECT COALESCE(SUM(pages),0) FROM documents").fetchone()[0],
            "references": c.execute("SELECT COALESCE(SUM(references_count),0) FROM documents").fetchone()[0],
            "users": c.execute("SELECT COUNT(*) FROM users").fetchone()[0],
            "conversions": c.execute("SELECT COUNT(*) FROM activity WHERE kind='convert'").fetchone()[0],
        }
        doc_types = c.execute("SELECT doc_type, COUNT(*) n FROM documents GROUP BY doc_type ORDER BY n DESC").fetchall()
        activity = c.execute("SELECT kind, title, detail, created_at FROM activity ORDER BY created_at DESC LIMIT 12"
                             ).fetchall()
        avg = c.execute("SELECT AVG(latency_ms), AVG(citation_score) FROM queries").fetchone()
    by_day: dict[str, dict] = {}
    for i in range(days):
        day = time.strftime("%Y-%m-%d", time.localtime(start + (i + 1) * 86400))
        by_day[day] = {"day": day, "queries": 0}
    langs: dict[str, int] = {}
    section_hits: dict[str, int] = {}
    for r in q_rows:
        day = time.strftime("%Y-%m-%d", time.localtime(r["created_at"]))
        if day in by_day:
            by_day[day]["queries"] += 1
        langs[r["language"] or "en"] = langs.get(r["language"] or "en", 0) + 1
        for sid in json.loads(r["sources"] or "[]")[:3]:
            section_hits[sid] = section_hits.get(sid, 0) + 1
    return {
        "totals": totals,
        "per_day": list(by_day.values()),
        "languages": langs,
        "top_sections": sorted(section_hits.items(), key=lambda x: -x[1])[:8],
        "doc_types": {r["doc_type"]: r["n"] for r in doc_types},
        "activity": [dict(r) for r in activity],
        "avg_latency_ms": round(avg[0] or 0, 1),
        "avg_citation_score": round(avg[1] or 0, 3),
    }
