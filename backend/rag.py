"""Retrieval-augmented answering with citation verification."""
from __future__ import annotations

import json
import re
import time
from typing import Iterator

from . import llm
from .corpus import get_corpus
from .search import search

LANG_NAMES = {"en": "English", "hi": "Hindi (Devanagari script)", "hinglish": "Hinglish (Hindi in Roman script)"}

SYSTEM_PROMPT = """You are NyayaSetu, an assistant that explains India's new criminal laws:
the Bharatiya Nyaya Sanhita 2023 (BNS), Bharatiya Nagarik Suraksha Sanhita 2023 (BNSS) and
Bharatiya Sakshya Adhiniyam 2023 (BSA), which replaced the IPC, CrPC and Indian Evidence Act on 1 July 2024.

Rules:
1. Answer ONLY from the numbered legal context provided. If the context is not enough, say so plainly.
2. Cite every legal claim with the section tag exactly as given, e.g. [BNS 318] or [BNSS 173].
3. When an old IPC/CrPC/IEA section is relevant, give its 2023 equivalent too.
4. Use short paragraphs and bullet points. Start with a one-line direct answer.
5. Mention punishment, cognizable/bailable status and the trial court when the context gives them.
6. End with: "This is legal information, not legal advice."
7. Write the whole answer in {language}."""

CITE = re.compile(r"\[(BNSS|BNS|BSA|IPC|CrPC|IEA)\s+([0-9]{1,3}[A-Z]{0,2})(?:\([^\]]*\))?\]")


def _context_block(results: list[dict]) -> str:
    corpus = get_corpus()
    lines = []
    for i, r in enumerate(results, 1):
        sec = corpus.by_id[r["id"]]
        block = [f"({i}) [{sec['act']} {sec['number']}] {sec['heading']}", sec["text"][:1800]]
        for c in corpus.classification_for(sec["id"])[:3]:
            block.append(f"  Schedule: {c['provision']} - punishment: {c['punishment']}; {c['cognizable']}; "
                         f"{c['bailable']}; triable by {c['triable_by']}")
        mapping = corpus.old_from_new.get((sec["act"], sec["number"]))
        if mapping and mapping["old"]:
            block.append(f"  Replaces: {mapping['old_act']} " + ", ".join(mapping["old"]))
        lines.append("\n".join(block))
    return "\n\n".join(lines)


def verify_citations(answer: str, retrieved_ids: list[str]) -> dict:
    corpus = get_corpus()
    cited, seen = [], set()
    for act, num in CITE.findall(answer):
        sid = f"{act}-{num}"
        if sid in seen:
            continue
        seen.add(sid)
        cited.append({
            "id": sid,
            "exists": sid in corpus.by_id,
            "grounded": sid in retrieved_ids,
            "heading": corpus.by_id.get(sid, {}).get("heading"),
        })
    valid = sum(1 for c in cited if c["exists"])
    grounded = sum(1 for c in cited if c["grounded"])
    return {"citations": cited, "total": len(cited), "valid": valid, "grounded": grounded,
            "score": round(grounded / len(cited), 3) if cited else 0.0}


def rewrite_query(question: str) -> str:
    """Uses the LLM to turn a Hindi/colloquial question into English statutory keywords."""
    try:
        out = llm.chat([
            {"role": "system", "content": "Rewrite the user's legal question as 6-12 English keywords that would "
                                          "appear in the text of Indian criminal statutes. Keep any section numbers "
                                          "and act names. Output keywords only."},
            {"role": "user", "content": question},
        ], max_tokens=60, temperature=0)
        return out.strip().replace("\n", " ")
    except llm.LLMError:
        return ""


def offline_answer(question: str, results: list[dict]) -> str:
    corpus = get_corpus()
    if not results:
        return "I could not find a matching provision. Try different words or a section number."
    top = results[0]
    parts = [f"**Most relevant provision: [{top['act']} {top['number']}] {top['heading']}.**", ""]
    for r in results[:4]:
        sec = corpus.by_id[r["id"]]
        line = f"- [{sec['act']} {sec['number']}] **{sec['heading']}**: {sec['text'][:260].strip()}..."
        parts.append(line)
        cls = corpus.classification_for(sec["id"])
        if cls:
            c = cls[0]
            parts.append(f"  - Punishment: {c['punishment']} · {c['cognizable']} · {c['bailable']} · "
                         f"Triable by {c['triable_by']}")
        m = corpus.old_from_new.get((sec["act"], sec["number"]))
        if m and m["old"]:
            parts.append(f"  - Replaces {m['old_act']} " + ", ".join(m["old"]))
    parts += ["", "_Offline mode: add a GROQ_API_KEY to get a written AI explanation._", "",
              "This is legal information, not legal advice."]
    return "\n".join(parts)


def answer_stream(question: str, language: str = "en", history: list[dict] | None = None,
                  k: int = 6) -> Iterator[dict]:
    """Yields events: {'type': 'sources'|'token'|'done'|'error', ...}."""
    t0 = time.perf_counter()
    rewritten = rewrite_query(question) if llm.available() else ""
    retrieval = search(f"{question} {rewritten}".strip(), method="hybrid", k=k)
    # Keep explicit references from the original question visible
    results = retrieval["results"]
    ids = [r["id"] for r in results]
    yield {"type": "sources", "sources": results, "rewritten": rewritten,
           "added_terms": retrieval["added_terms"], "references": retrieval["references"],
           "retrieval_ms": retrieval["latency_ms"]}

    if not llm.available():
        text = offline_answer(question, results)
        for i in range(0, len(text), 24):
            yield {"type": "token", "text": text[i:i + 24]}
        yield {"type": "done", "verification": verify_citations(text, ids), "mode": "offline",
               "latency_ms": round((time.perf_counter() - t0) * 1000)}
        return

    messages = [{"role": "system", "content": SYSTEM_PROMPT.format(language=LANG_NAMES.get(language, "English"))}]
    for turn in (history or [])[-6:]:
        if turn.get("role") in ("user", "assistant") and turn.get("content"):
            messages.append({"role": turn["role"], "content": str(turn["content"])[:2000]})
    messages.append({"role": "user", "content": f"Legal context:\n{_context_block(results)}\n\nQuestion: {question}"})

    full = []
    try:
        for tok in llm.stream_chat(messages):
            full.append(tok)
            yield {"type": "token", "text": tok}
    except llm.LLMError as e:
        yield {"type": "error", "message": str(e)}
        text = offline_answer(question, results)
        yield {"type": "token", "text": "\n\n" + text}
        full.append(text)
    answer = "".join(full)
    yield {"type": "done", "verification": verify_citations(answer, ids), "mode": "groq",
           "latency_ms": round((time.perf_counter() - t0) * 1000)}


def summarize_document(text: str, refs: list[dict], doc_type: str) -> dict:
    """Structured summary of an uploaded legal document."""
    if not llm.available():
        return {"mode": "offline", **extractive_summary(text)}
    ref_lines = "; ".join(
        f"{r['label']} ({r['heading'] or 'unknown'})" + (" -> " + ", ".join(c['id'] for c in r['converted']) if r['converted'] else "")
        for r in refs[:25]
    )
    excerpt, coverage = select_excerpts(text)
    prompt = (
        f"Document type (detected): {doc_type}\nLegal references found: {ref_lines or 'none'}\n\n"
        f"Document text ({coverage}):\n{excerpt}\n\n"
        "Return a JSON object with keys: title (string), summary (3-5 sentences), parties (list of strings), "
        "key_facts (list of up to 6 strings), timeline (list of {date, event}), offences (list of "
        "{old_section, new_section, description}), next_steps (list of up to 4 strings for the citizen), "
        "risk_level ('low'|'medium'|'high'). Use the 2023 codes (BNS/BNSS/BSA) for new_section. "
        "For a court judgment, the summary must state the court's final holding and any directions."
    )
    try:
        raw = llm.chat([{"role": "system", "content": "You analyse Indian legal documents. Output valid JSON only."},
                        {"role": "user", "content": prompt}], json_mode=True, max_tokens=1500)
        data = json.loads(raw)
        data["mode"] = "groq"
        return data
    except (llm.LLMError, ValueError) as e:
        return {"mode": "offline", "error": str(e), **extractive_summary(text)}


SECTION_HINT = re.compile(r"\b(?:section|sections|u/s|s\.)\s*\d", re.IGNORECASE)
CONCLUSION_HINT = re.compile(r"\b(?:held|direct|directions|conclusion|accordingly|dismissed|allowed|we hold|"
                             r"in view of the above|ordered)\b", re.IGNORECASE)


def select_excerpts(text: str, budget: int = 12000) -> tuple[str, str]:
    """Picks what a long document's summary should see: the opening (facts, parties), the end
    (judgments put their conclusions and directions last) and the middle passages that cite
    the most sections or state holdings. Short documents are sent whole."""
    text = re.sub(r"[ \t]+", " ", text)
    if len(text) <= budget:
        return text, "complete"
    head, tail = text[:3500], text[-3500:]
    middle = text[3500:-3500]
    size = 1200
    blocks = [middle[i:i + size] for i in range(0, len(middle), size)]
    scored = sorted(range(len(blocks)),
                    key=lambda i: -(len(SECTION_HINT.findall(blocks[i])) * 2 + len(CONCLUSION_HINT.findall(blocks[i]))))
    keep = sorted(scored[: max(1, (budget - 7000) // size)])
    parts = [head] + [f"[... {blocks[i]} ...]" for i in keep] + [tail]
    pct = round(100 * (7000 + len(keep) * size) / len(text))
    return "\n\n".join(parts), f"long document: opening, conclusion and key passages, about {pct}% of the text"


def extractive_summary(text: str, n: int = 4) -> dict:
    """Frequency-based sentence scoring (fallback when no LLM is configured)."""
    from collections import Counter

    from .search import analyze

    flat = re.sub(r"\s+", " ", text)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?।])\s+(?=[A-Z\u0900-\u097F(])", flat) if 40 <= len(s.strip()) <= 400]
    if len(sentences) > 3000:  # very long documents: keep scoring fast
        sentences = sentences[:1500] + sentences[-1500:]
    if not sentences:
        return {"summary": text[:500], "key_facts": []}
    freq = Counter(t for s in sentences for t in analyze(s))
    scored = sorted(
        ((sum(freq[t] for t in analyze(s)) / (len(analyze(s)) + 5), i, s) for i, s in enumerate(sentences)),
        reverse=True,
    )[:n]
    chosen = [s for _, _, s in sorted(scored, key=lambda x: x[1])]
    return {"summary": " ".join(chosen), "key_facts": chosen}
