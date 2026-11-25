"""NyayaSetu API server (FastAPI)."""
from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from typing import List, Optional

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import db, graph, llm, pdf_service, predictor, rag
from .config import FRONTEND_DIR, settings
from .corpus import OLD_TO_NEW, get_corpus, norm_number, roman_to_int
from .detector import convert, convert_text, detect_references, reverse
from .evaluation import run_benchmark
from .search import ChunkIndex, search

app = FastAPI(
    title="NyayaSetu API",
    version="1.0.0",
    description="AI legal assistant for India's new criminal laws (BNS, BNSS, BSA 2023).",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def startup() -> None:
    db.init()
    get_corpus()


# --------------------------------------------------------------------------- auth
class RegisterIn(BaseModel):
    name: str
    email: str
    password: str


class LoginIn(BaseModel):
    email: str
    password: str


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Please sign in.")
    uid = db.read_token(authorization.split(" ", 1)[1].strip())
    user = db.get_user(uid) if uid else None
    if not user:
        raise HTTPException(401, "Your session has expired. Please sign in again.")
    return user


@app.post("/api/auth/register", tags=["auth"])
def register(body: RegisterIn):
    if len(body.name.strip()) < 2:
        raise HTTPException(400, "Please enter your name.")
    if not EMAIL_RE.match(body.email.strip()):
        raise HTTPException(400, "Please enter a valid email address.")
    if len(body.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters.")
    if db.get_user_by_email(body.email):
        raise HTTPException(409, "An account with this email already exists.")
    user = db.create_user(body.name, body.email, body.password)
    db.log_activity(user["id"], "user", f"{user['name']} joined NyayaSetu")
    return {"token": db.make_token(user["id"]), "user": user}


@app.post("/api/auth/login", tags=["auth"])
def login(body: LoginIn):
    row = db.get_user_by_email(body.email)
    if not row or not db.verify_password(body.password, row["password_hash"]):
        raise HTTPException(401, "Incorrect email or password.")
    user = db.get_user(row["id"])
    return {"token": db.make_token(user["id"]), "user": user}


@app.get("/api/auth/me", tags=["auth"])
def me(user: dict = Depends(current_user)):
    return user


# --------------------------------------------------------------------------- system
@app.get("/api/health", tags=["system"])
def health():
    c = get_corpus()
    return {"status": "ok", "sections": len(c.sections), "llm_configured": llm.available(),
            "model": settings.groq_model if llm.available() else None}


@app.get("/api/llm/status", tags=["system"])
def llm_status(user: dict = Depends(current_user)):
    return llm.ping()


@app.get("/api/llm/models", tags=["system"])
def llm_models(user: dict = Depends(current_user)):
    if not llm.available():
        return {"models": [], "current": None}
    try:
        return {"models": llm.list_models(), "current": settings.groq_model}
    except llm.LLMError as e:
        raise HTTPException(502, str(e))


class ModelIn(BaseModel):
    model: str


@app.post("/api/llm/model", tags=["system"])
def set_model(body: ModelIn, user: dict = Depends(current_user)):
    llm.save_model(body.model.strip())
    db.log_activity(user["id"], "settings", f"AI model set to {settings.groq_model}")
    return {"current": settings.groq_model}


@app.get("/api/stats/overview", tags=["dashboard"])
def overview(user: dict = Depends(current_user)):
    return {"corpus": get_corpus().stats(), "usage": db.usage_stats(), "llm_configured": llm.available(),
            "model": settings.groq_model}


# --------------------------------------------------------------------------- search & sections
@app.get("/api/search", tags=["law"])
def api_search(q: str = Query(..., min_length=1, max_length=500), method: str = "hybrid", k: int = 10,
               act: Optional[List[str]] = Query(None), user: dict = Depends(current_user)):
    if method not in ("keyword", "bm25", "hybrid"):
        raise HTTPException(400, "method must be keyword, bm25 or hybrid")
    return search(q, method=method, k=min(max(k, 1), 50), acts=act)


@app.get("/api/sections/{section_id}", tags=["law"])
def section_detail(section_id: str, user: dict = Depends(current_user)):
    c = get_corpus()
    act, _, num = section_id.partition("-")
    sec = c.by_id.get(f"{act}-{norm_number(num)}")
    if not sec:
        raise HTTPException(404, "Section not found")
    meta = c.act_meta[sec["act"]]
    return {
        **sec,
        "act_name": meta["name"],
        "act_year": meta["year"],
        "era": meta["era"],
        "classification": c.classification_for(sec["id"]),
        "successors": convert(sec["act"], sec["number"]),
        "predecessors": reverse(sec["act"], sec["number"]),
        "cross_references": [r["section_id"] for r in detect_references(sec["text"], default_act=sec["act"])
                             if r["exists"] and r["section_id"] != sec["id"]][:12],
    }


@app.get("/api/acts", tags=["law"])
def acts(user: dict = Depends(current_user)):
    return get_corpus().acts


@app.get("/api/acts/{code}/chapters", tags=["law"])
def act_chapters(code: str, user: dict = Depends(current_user)):
    c = get_corpus()
    if code not in c.act_meta:
        raise HTTPException(404, "Unknown act")
    chapters: dict[str, dict] = {}
    for s in c.sections:
        if s["act"] != code:
            continue
        key = s["chapter"] or s["chapter_name"] or "General"
        ch = chapters.setdefault(key, {"chapter": s["chapter"], "name": s["chapter_name"], "count": 0,
                                       "first": s["number"]})
        ch["count"] += 1
    items = list(chapters.values())
    if all(i["chapter"] for i in items):
        items.sort(key=lambda i: roman_to_int(i["chapter"]))
    return items


@app.get("/api/acts/{code}/sections", tags=["law"])
def act_sections(code: str, chapter: Optional[str] = None, user: dict = Depends(current_user)):
    c = get_corpus()
    out = []
    for s in c.sections:
        if s["act"] != code:
            continue
        if chapter and chapter not in (s["chapter"], s["chapter_name"]):
            continue
        item = c.summary(s, 160)
        m = c.old_from_new.get((s["act"], s["number"]))
        item["is_new"] = bool(m and not m["old"] and m["source"] == "official")
        item["predecessors"] = [f"{m['old_act']} {o}" for o in m["old"]] if m else []
        item["successors"] = [f"{x['act']} {x['number']}" for x in convert(s["act"], s["number"])]
        out.append(item)
    return out


@app.get("/api/mappings", tags=["converter"])
def mappings(act: str = "BNS", q: str = "", type: str = "", page: int = 1, size: int = 25,
             user: dict = Depends(current_user)):
    c = get_corpus()
    rows = []
    ql = q.lower().strip()
    for m in c.mappings:
        if m["new_act"] != act or (type and m["type"] != type):
            continue
        new = c.by_id.get(f"{m['new_act']}-{m['new']}")
        olds = [c.by_id.get(f"{m['old_act']}-{o}") for o in m["old"]]
        row = {
            "new_id": f"{m['new_act']}-{m['new']}", "new": f"{m['new_act']} {m['new']}",
            "new_heading": new["heading"] if new else "",
            "old": [f"{m['old_act']} {o}" for o in m["old"]],
            "old_headings": [o["heading"] if o else "" for o in olds],
            "type": m["type"], "source": m["source"], "confidence": m["confidence"],
        }
        hay = " ".join([row["new"], row["new_heading"], *row["old"], *row["old_headings"]]).lower()
        if ql and ql not in hay:
            continue
        rows.append(row)
    total = len(rows)
    start = (max(page, 1) - 1) * size
    return {"total": total, "page": page, "size": size, "rows": rows[start:start + size]}


@app.get("/api/convert", tags=["converter"])
def convert_one(act: str, number: str, user: dict = Depends(current_user)):
    c = get_corpus()
    act_code = c.resolve_act(act) or act
    if act_code not in c.act_meta:
        raise HTTPException(400, "Unknown act. Use IPC, CrPC, IEA, BNS, BNSS or BSA.")
    sec = c.get(act_code, number)
    if not sec:
        raise HTTPException(404, f"{act_code} section {number} was not found.")
    results = convert(act_code, number) if act_code in OLD_TO_NEW else reverse(act_code, number)
    db.log_activity(user["id"], "convert", f"{act_code} {number} → " +
                    (", ".join(f"{r['act']} {r['number']}" for r in results) or "no equivalent"))
    detailed = []
    for r in results:
        target = c.by_id.get(r["id"])
        # Order Schedule entries so the one closest to the old heading comes first
        # (e.g. IPC 420 -> BNS 318(4), not 318(2)).
        query_terms = set(re.findall(r"[a-z]+", sec["heading"].lower()))
        cls = sorted(c.classification_for(r["id"]),
                     key=lambda e: -len(query_terms & set(re.findall(r"[a-z]+", e["offence"].lower()))))
        detailed.append({**r, "text": target["text"] if target else "", "classification": cls})
    return {"query": {"act": act_code, "number": sec["number"], "heading": sec["heading"], "text": sec["text"],
                      "era": c.act_meta[act_code]["era"], "classification": c.classification_for(sec["id"])},
            "results": detailed}


class TextIn(BaseModel):
    text: str


@app.post("/api/convert/text", tags=["converter"])
def convert_passage(body: TextIn, user: dict = Depends(current_user)):
    if len(body.text) > 100_000:
        raise HTTPException(413, "Text is too long (max 100,000 characters).")
    out = convert_text(body.text)
    db.log_activity(user["id"], "convert", f"Converted a passage with {out['old_references']} old references")
    return out


# --------------------------------------------------------------------------- AI assistant
class AskIn(BaseModel):
    question: str
    language: str = "en"
    history: List[dict] = []


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@app.post("/api/ask", tags=["assistant"])
def ask(body: AskIn, user: dict = Depends(current_user)):
    question = body.question.strip()
    if not question:
        raise HTTPException(400, "Please type a question.")
    if len(question) > 2000:
        raise HTTPException(413, "Question is too long.")

    def gen():
        sources: list[str] = []
        for ev in rag.answer_stream(question, body.language, body.history):
            if ev["type"] == "sources":
                sources = [s["id"] for s in ev["sources"]]
            if ev["type"] == "done":
                db.log_query(user["id"], question, body.language, ev["mode"], sources,
                             ev["verification"]["score"], ev["latency_ms"])
                db.log_activity(user["id"], "ask", question[:120],
                                f"{ev['verification']['grounded']}/{ev['verification']['total']} citations grounded")
            yield _sse(ev)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/history", tags=["assistant"])
def history(user: dict = Depends(current_user)):
    return db.recent_queries(user["id"])


# --------------------------------------------------------------------------- documents (PDF extraction)
@app.post("/api/documents", tags=["documents"])
async def upload_document(file: UploadFile = File(...), user: dict = Depends(current_user)):
    name = file.filename or "document"
    data = await file.read()
    if not data:
        raise HTTPException(400, "The file is empty.")
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"File is larger than {settings.max_upload_mb} MB.")
    lower = name.lower()
    try:
        if lower.endswith(".pdf") or data[:5] == b"%PDF-":
            extraction = pdf_service.extract_pdf(data)
        elif lower.endswith((".txt", ".md")):
            extraction = pdf_service.extract_text_file(data)
        else:
            raise HTTPException(415, "Please upload a PDF or a .txt file.")
    except pdf_service.ExtractionError as e:
        raise HTTPException(422, str(e))
    analysis = pdf_service.analyze(extraction)
    analysis["metadata"] = extraction["metadata"]
    analysis["is_scanned"] = extraction["is_scanned"]
    doc_id = hashlib.sha1(data).hexdigest()[:10] + uuid.uuid4().hex[:6]
    doc = {
        "id": doc_id, "user_id": user["id"], "filename": name, "size_bytes": len(data),
        "pages": extraction["page_count"], "words": analysis["stats"]["words"],
        "doc_type": analysis["doc_type"]["type"], "references_count": len(analysis["references"]),
        "analysis": analysis, "page_text": [{"page": p["page"], "text": p["text"]} for p in extraction["pages"]],
    }
    db.save_document(doc)
    db.log_activity(user["id"], "document", f"Analysed {name}",
                    f"{doc['pages']} pages · {doc['references_count']} legal references · {doc['doc_type']}")
    return {"id": doc_id, "filename": name, "size_bytes": len(data), "analysis": analysis,
            "pages": doc["page_text"], "summary": None}


@app.get("/api/documents", tags=["documents"])
def documents(user: dict = Depends(current_user)):
    return db.list_documents(user["id"])


def _owned_doc(doc_id: str, user: dict) -> dict:
    doc = db.get_document(doc_id)
    if not doc or doc["user_id"] != user["id"]:
        raise HTTPException(404, "Document not found")
    return doc


@app.get("/api/documents/{doc_id}", tags=["documents"])
def document(doc_id: str, user: dict = Depends(current_user)):
    d = _owned_doc(doc_id, user)
    return {"id": d["id"], "filename": d["filename"], "size_bytes": d["size_bytes"], "analysis": d["analysis"],
            "pages": d["page_text"], "summary": d["summary"], "created_at": d["created_at"]}


@app.delete("/api/documents/{doc_id}", tags=["documents"])
def remove_document(doc_id: str, user: dict = Depends(current_user)):
    _owned_doc(doc_id, user)
    db.delete_document(doc_id, user["id"])
    return {"deleted": True}


@app.post("/api/documents/{doc_id}/summary", tags=["documents"])
def summarize(doc_id: str, user: dict = Depends(current_user)):
    d = _owned_doc(doc_id, user)
    text = "\n".join(p["text"] for p in d["page_text"])
    t0 = time.perf_counter()
    summary = rag.summarize_document(text, d["analysis"]["references"], d["analysis"]["doc_type"]["type"])
    summary["latency_ms"] = round((time.perf_counter() - t0) * 1000)
    db.update_summary(doc_id, summary)
    db.log_activity(user["id"], "summary", f"AI summary for {d['filename']}", summary.get("mode", ""))
    return summary


class DocAskIn(BaseModel):
    question: str
    language: str = "en"


@app.post("/api/documents/{doc_id}/ask", tags=["documents"])
def ask_document(doc_id: str, body: DocAskIn, user: dict = Depends(current_user)):
    d = _owned_doc(doc_id, user)
    chunks = pdf_service.chunk_pages(d["page_text"])
    if not chunks:
        raise HTTPException(422, "No text was extracted from this document.")
    hits = ChunkIndex(chunks).search(body.question, k=4)
    if not llm.available():
        return {"answer": "Most relevant passages from the document are shown below. Add a GROQ_API_KEY for a "
                          "written answer.", "passages": hits, "mode": "offline"}
    context = "\n\n".join(f"[Page {h['page']}] {h['text']}" for h in hits)
    lang = rag.LANG_NAMES.get(body.language, "English")
    try:
        answer = llm.chat([
            {"role": "system", "content": "Answer the question using only the document excerpts. Cite pages as "
                                          f"(p. N). If the excerpts do not contain the answer, say so. Reply in {lang}."},
            {"role": "user", "content": f"Excerpts:\n{context}\n\nQuestion: {body.question}"},
        ], max_tokens=700)
    except llm.LLMError as e:
        raise HTTPException(502, str(e))
    return {"answer": answer, "passages": hits, "mode": "groq"}


@app.get("/api/documents/{doc_id}/export", tags=["documents"])
def export_document(doc_id: str, format: str = "txt", user: dict = Depends(current_user)):
    d = _owned_doc(doc_id, user)
    base = re.sub(r"[^\w.-]+", "_", d["filename"].rsplit(".", 1)[0])[:60] or "document"
    if format == "json":
        payload = {"filename": d["filename"], "analysis": d["analysis"], "summary": d["summary"], "pages": d["page_text"]}
        return JSONResponse(payload, headers={"Content-Disposition": f'attachment; filename="{base}_analysis.json"'})
    if format == "md":
        a = d["analysis"]
        lines = [f"# NyayaSetu analysis: {d['filename']}", "",
                 f"- Document type: {a['doc_type']['type']}",
                 f"- Pages: {a['stats']['pages']} · Words: {a['stats']['words']}",
                 f"- Legal references: {len(a['references'])} ({a['outdated_references']} under repealed codes)", "",
                 "## Legal references", "", "| Reference | Heading | 2023 equivalent | Pages |", "|---|---|---|---|"]
        for r in a["references"]:
            eq = ", ".join(f"{c['act']} {c['number']}" for c in r["converted"]) or "-"
            lines.append(f"| {r['label']} | {r['heading'] or '-'} | {eq} | {', '.join(map(str, r['pages']))} |")
        if d["summary"]:
            lines += ["", "## Summary", "", str(d["summary"].get("summary", ""))]
        lines += ["", "_Generated by NyayaSetu. Legal information, not legal advice._"]
        return PlainTextResponse("\n".join(lines), headers={"Content-Disposition": f'attachment; filename="{base}_report.md"'})
    text = "\n\n".join(f"===== Page {p['page']} =====\n{p['text']}" for p in d["page_text"])
    return PlainTextResponse(text, headers={"Content-Disposition": f'attachment; filename="{base}_extracted.txt"'})


# --------------------------------------------------------------------------- graph & evaluation
@app.get("/api/graph/overview", tags=["graph"])
def graph_overview(user: dict = Depends(current_user)):
    return graph.overview()


@app.get("/api/graph/chapter", tags=["graph"])
def graph_chapter(act: str = "BNS", chapter: str = "CHAPTER VI", user: dict = Depends(current_user)):
    return graph.chapter_graph(act, chapter)


@app.get("/api/graph/section/{section_id}", tags=["graph"])
def graph_section(section_id: str, user: dict = Depends(current_user)):
    return graph.section_graph(section_id)


@app.get("/api/evaluation", tags=["evaluation"])
def evaluation(user: dict = Depends(current_user)):
    return run_benchmark()


# --------------------------------------------------------------------------- section predictor (own ML model)
class PredictIn(BaseModel):
    text: str
    k: int = 5


@app.get("/api/predict/status", tags=["predictor"])
def predict_status(user: dict = Depends(current_user)):
    return predictor.status()


@app.post("/api/predict", tags=["predictor"])
def predict_sections(body: PredictIn, user: dict = Depends(current_user)):
    text = body.text.strip()
    if len(text) < 15:
        raise HTTPException(400, "Please describe what happened in at least one full sentence.")
    if len(text) > 20000:
        raise HTTPException(413, "Text is too long (max 20,000 characters).")
    out = predictor.predict(text, k=min(max(body.k, 1), 10))
    top = out["predictions"][0] if out["predictions"] else None
    db.log_activity(user["id"], "predict", f"Section prediction: {text[:80]}",
                    f"top: {top['ipc']} ({round(top['probability'] * 100)}%)" if top else "search only")
    return out


# --------------------------------------------------------------------------- frontend
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
