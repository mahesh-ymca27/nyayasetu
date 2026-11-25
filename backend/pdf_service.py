"""PDF text extraction and legal document analysis."""
from __future__ import annotations

import io
import re
import time
from collections import Counter

from .detector import detect_references
from .search import STOP, tokenize

DOC_TYPES = {
    "FIR": ["first information report", "f.i.r", "fir no", "police station", "informant", "complainant",
            "occurrence", "प्रथम सूचना"],
    "Judgment / Order": ["judgment", "hon'ble", "petitioner", "respondent", "appellant", "bench", "order",
                         "court", "dismissed", "allowed", "learned counsel"],
    "Chargesheet": ["charge sheet", "chargesheet", "final report", "investigating officer", "accused",
                    "witness", "section 173", "section 193"],
    "Legal Notice": ["legal notice", "notice is hereby", "my client", "within 15 days", "within fifteen days",
                     "failing which"],
    "Bail Application": ["bail application", "anticipatory bail", "regular bail", "applicant", "custody",
                         "section 438", "section 439", "section 482", "section 483"],
    "Bare Act / Statute": ["be it enacted", "short title", "commencement", "chapter", "this act may be called",
                           "sanhita"],
    "Complaint": ["complaint", "complainant", "prays", "humbly submitted", "respectfully"],
}

DATE = re.compile(
    r"\b(\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|"
    r"Sept|Oct|Nov|Dec)[a-z]*\.?,?\s+\d{4}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4})\b",
    re.IGNORECASE,
)
MONEY = re.compile(r"(?:₹|Rs\.?|INR)\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:lakh|lakhs|crore|crores))?|\d[\d,]*\s?(?:lakh|crore)s?\b",
                   re.IGNORECASE)
PHONE = re.compile(r"(?<!\d)(?:\+91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")
FIR_NO = re.compile(r"\b(?:FIR|F\.I\.R\.?|Crime)\s*(?:No\.?|Number)\s*[:\-]?\s*([\w/-]{2,20})", re.IGNORECASE)
POLICE_STATION = re.compile(
    r"(?:\bP\.S\.|\bPS\b|\bPolice\s+Station)\s*[:\-]?\s*"
    r"((?!(?:Date|Dated|Year|District|FIR|On|At|In)\b)[A-Z][A-Za-z]+\b(?!\s*:)"
    r"(?:\s+(?!(?:Date|Dated|Year|District|FIR|On|At|In)\b)[A-Z][A-Za-z]+\b(?!\s*:)){0,2})")
COURT = re.compile(r"\b(?:IN\s+THE\s+)?((?:HIGH\s+COURT|SUPREME\s+COURT|COURT\s+OF|DISTRICT\s+COURT|SESSIONS\s+COURT)"
                   r"[A-Za-z ,.]{0,60})", re.IGNORECASE)


class ExtractionError(RuntimeError):
    pass


def extract_pdf(data: bytes) -> dict:
    try:
        from pypdf import PdfReader
    except ImportError as e:  # pragma: no cover - dependency missing
        raise ExtractionError("pypdf is not installed. Run: pip install -r requirements.txt") from e
    t0 = time.perf_counter()
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as e:  # noqa: BLE001
                raise ExtractionError("This PDF is password protected.") from e
        pages = []
        for i, page in enumerate(reader.pages, 1):
            try:
                text = page.extract_text() or ""
            except Exception:  # noqa: BLE001 - malformed page
                text = ""
            text = re.sub(r"[ \t]+", " ", text).strip()
            pages.append({"page": i, "text": text, "words": len(text.split()), "chars": len(text)})
        meta = {}
        if reader.metadata:
            for key in ("title", "author", "creator", "producer", "subject"):
                val = getattr(reader.metadata, key, None)
                if val:
                    meta[key] = str(val)[:200]
    except ExtractionError:
        raise
    except Exception as e:  # noqa: BLE001
        raise ExtractionError(f"Could not read this PDF: {e}") from e
    empty = sum(1 for p in pages if p["words"] < 5)
    return {
        "pages": pages,
        "page_count": len(pages),
        "metadata": meta,
        "scanned_pages": empty,
        "is_scanned": bool(pages) and empty == len(pages),
        "extract_ms": round((time.perf_counter() - t0) * 1000, 1),
    }


def extract_text_file(data: bytes) -> dict:
    text = data.decode("utf-8", errors="ignore")
    chunks = [text[i:i + 3000] for i in range(0, len(text), 3000)] or [""]
    pages = [{"page": i + 1, "text": c, "words": len(c.split()), "chars": len(c)} for i, c in enumerate(chunks)]
    return {"pages": pages, "page_count": len(pages), "metadata": {}, "scanned_pages": 0, "is_scanned": False,
            "extract_ms": 0}


def classify(text: str) -> dict:
    t = text.lower()
    scores = {k: sum(t.count(w) for w in words) for k, words in DOC_TYPES.items()}
    total = sum(scores.values()) or 1
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        best = "General Document"
    ranked = sorted(({"type": k, "score": round(v / total, 3)} for k, v in scores.items() if v), key=lambda x: -x["score"])
    return {"type": best, "confidence": ranked[0]["score"] if ranked else 0.0, "candidates": ranked[:4]}


def _uniq(items, limit=15):
    seen, out = set(), []
    for it in items:
        if isinstance(it, str):
            it = re.sub(r"\s+", " ", it)
        key = it.strip().lower() if isinstance(it, str) else it
        if key and key not in seen:
            seen.add(key)
            out.append(it.strip() if isinstance(it, str) else it)
        if len(out) >= limit:
            break
    return out


def analyze(extraction: dict) -> dict:
    pages = extraction["pages"]
    full = "\n".join(p["text"] for p in pages)
    words = full.split()
    refs = []
    highlights: dict[int, list[dict]] = {}
    for p in pages:
        spans: dict[tuple[int, int], list[str]] = {}
        for r in detect_references(p["text"]):
            r["page"] = p["page"]
            for span in r.pop("spans"):
                spans.setdefault(tuple(span), []).append(r["section_id"])
            refs.append(r)
        highlights[p["page"]] = [{"start": s, "end": e, "ids": ids} for (s, e), ids in sorted(spans.items())]
    merged: dict[str, dict] = {}
    for r in refs:
        if r["section_id"] in merged:
            merged[r["section_id"]]["count"] += r["count"]
            if r["page"] not in merged[r["section_id"]]["pages"]:
                merged[r["section_id"]]["pages"].append(r["page"])
        else:
            merged[r["section_id"]] = {**r, "pages": [r["page"]]}
    # Old-code references first: those are the ones the user needs converted.
    references = sorted(merged.values(), key=lambda r: (r["era"] != "old", -r["count"], r["section_id"]))

    toks = [t for t in tokenize(full) if t not in STOP and not t.isdigit() and len(t) > 3]
    keywords = [{"word": w, "count": c} for w, c in Counter(toks).most_common(15)]
    acts_mentioned = Counter(r["act"] for r in references)
    old_refs = [r for r in references if r["era"] == "old"]

    return {
        "doc_type": classify(full),
        "stats": {
            "pages": extraction["page_count"],
            "words": len(words),
            "characters": len(full),
            "reading_minutes": max(1, round(len(words) / 200)),
            "unique_words": len(set(w.lower() for w in words)),
            "scanned_pages": extraction["scanned_pages"],
            "extract_ms": extraction["extract_ms"],
        },
        "references": references,
        "acts_mentioned": dict(acts_mentioned),
        "outdated_references": len(old_refs),
        "convertible_references": sum(1 for r in old_refs if r["converted"]),
        "entities": {
            "dates": _uniq(DATE.findall(full)),
            "amounts": _uniq(MONEY.findall(full)),
            "phones": _uniq(PHONE.findall(full), 8),
            "emails": _uniq(EMAIL.findall(full), 8),
            "fir_numbers": _uniq(FIR_NO.findall(full), 5),
            "police_stations": _uniq(POLICE_STATION.findall(full), 5),
            "courts": _uniq((c.strip(" ,.") for c in COURT.findall(full)), 5),
        },
        "keywords": keywords,
        "words_per_page": [{"page": p["page"], "words": p["words"]} for p in pages],
        "highlights": highlights,
    }


def chunk_pages(pages: list[dict], size: int = 180, overlap: int = 40) -> list[dict]:
    chunks = []
    for p in pages:
        words = p["text"].split()
        if not words:
            continue
        step = max(1, size - overlap)
        for i in range(0, len(words), step):
            piece = " ".join(words[i:i + size])
            chunks.append({"page": p["page"], "text": piece})
            if i + size >= len(words):
                break
    return chunks
