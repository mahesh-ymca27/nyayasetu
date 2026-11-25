"""Detects statutory references in free text and converts old-code references to the 2023 codes.

Handles forms such as:
  "Section 420 IPC", "u/s 420/406/34 IPC", "Sections 302, 120B of the Indian Penal Code",
  "S. 154 Cr.P.C.", "section 65B of the Evidence Act", "IPC 498A", "BNS 318(4)", "धारा 302 आईपीसी"
"""
from __future__ import annotations

import re

from .corpus import OLD_TO_NEW, get_corpus, norm_number

ACT_PATTERN = (
    r"(?P<act>Bharatiya\s+Nagarik\s+Suraksha\s+Sanhita|Bharatiya\s+Nyaya\s+Sanhita|Bharatiya\s+Sakshya\s+Adhiniyam|"
    r"Indian\s+Penal\s+Code|Penal\s+Code|Code\s+of\s+Criminal\s+Procedure|Criminal\s+Procedure\s+Code|"
    r"Indian\s+Evidence\s+Act|Evidence\s+Act|B\.?N\.?S\.?S\.?|B\.?N\.?S\.?|B\.?S\.?A\.?|I\.?P\.?C\.?|"
    r"Cr\.?\s?P\.?\s?C\.?|I\.?E\.?A\.?|आईपीसी|बीएनएस|सीआरपीसी)"
)
NUM = r"\d{1,3}[A-Z]{0,2}(?:\s?\(\d+\))?(?:\s?\([a-z]\))?"
NUM_LIST = rf"{NUM}(?:\s*(?:,|/|&|and|or|r/w|read\s+with)\s*{NUM})*"

# "Section 420 IPC" / "u/s 420/34 of the IPC" / "धारा 302 आईपीसी"
FORWARD = re.compile(
    rf"(?:\bu/s\.?|\bunder\s+sections?|\bsections?|\bsecs?\.?|\bss?\.|धारा)\s*(?P<nums>{NUM_LIST})"
    rf"(?:\s*,?\s*(?:of\s+)?(?:the\s+)?{ACT_PATTERN})?",
    re.IGNORECASE,
)
# "IPC 420" / "BNS 318(4)" / "420 IPC"
ACT_FIRST = re.compile(rf"\b{ACT_PATTERN}\s*(?:section|sec\.?|s\.)?\s*(?P<nums>{NUM_LIST})\b", re.IGNORECASE)
NUM_FIRST = re.compile(rf"\b(?P<nums>{NUM})\s+(?:of\s+)?(?:the\s+)?{ACT_PATTERN}", re.IGNORECASE)

HINDI_ACTS = {"आईपीसी": "IPC", "बीएनएस": "BNS", "सीआरपीसी": "CrPC"}
NEXT_ACT = re.compile(rf"\s*(?:of\s+)?(?:the\s+)?{ACT_PATTERN}", re.IGNORECASE)
SEPARATOR = re.compile(r"\s*(?:,|/|&|\band\b|\bor\b|r/w|read\s+with)\s*", re.IGNORECASE)

# Judgments define a short name once ("Code of Criminal Procedure, 1973 (in short 'the Code')")
# and then write "Section 154 of the Code" for the rest of the document.
OF_THE_CODE = re.compile(
    rf"(?:\bu/s\.?|\bsections?|\bsecs?\.?|\bss?\.)\s*(?P<nums>{NUM_LIST})\s*,?\s*of\s+the\s+(?:said\s+)?(?:Code|Sanhita)\b(?!\s+of)",
    re.IGNORECASE,
)
CODE_DEFINITION = re.compile(
    rf"{ACT_PATTERN}[^()]{{0,25}}\((?:[^()]{{0,40}})[\"'‘“]\s*(?:the\s+)?(?:Code|Sanhita)\s*[\"'’”]",
    re.IGNORECASE,
)


def infer_code_act(text: str, refs: list[dict] | None = None) -> str | None:
    """Works out which act 'the Code' means in a document."""
    m = CODE_DEFINITION.search(text)
    if m:
        act = _act_code(m.group("act"))
        if act:
            return act
    counts: dict[str, int] = {}
    for r in refs or []:
        if r["act"] in ("CrPC", "IPC", "BNSS", "BNS"):
            counts[r["act"]] = counts.get(r["act"], 0) + r["count"]
    if not counts:
        lowered = text.lower()
        if "criminal procedure" in lowered or "cr.p.c" in lowered or "crpc" in lowered:
            return "CrPC"
        if "penal code" in lowered:
            return "IPC"
        return None
    return max(counts, key=counts.get)


def _act_code(raw: str | None) -> str | None:
    if not raw:
        return None
    if raw in HINDI_ACTS:
        return HINDI_ACTS[raw]
    key = re.sub(r"[\s.]", "", raw.lower())
    return get_corpus().resolve_act(key) or {"crpc": "CrPC"}.get(key)


def _split_nums(nums: str) -> list[str]:
    parts = re.split(r"\s*(?:,|/|&|\band\b|\bor\b|r/w|read\s+with)\s*", nums, flags=re.IGNORECASE)
    return [p.strip() for p in parts if p.strip()]


def convert(act: str, number: str) -> list[dict]:
    """Old-code section -> list of 2023-code sections (with headings)."""
    corpus = get_corpus()
    out = []
    if act in OLD_TO_NEW:
        for m in corpus.new_from_old.get((act, norm_number(number)), []):
            sec = corpus.by_id.get(f"{m['new_act']}-{m['new']}")
            if sec:
                out.append({"id": sec["id"], "act": sec["act"], "number": sec["number"], "heading": sec["heading"],
                            "source": m["source"], "confidence": m["confidence"], "type": m["type"]})
    return out


def reverse(act: str, number: str) -> list[dict]:
    """2023-code section -> old-code predecessor(s)."""
    corpus = get_corpus()
    m = corpus.old_from_new.get((act, norm_number(number)))
    if not m:
        return []
    out = []
    for o in m["old"]:
        sec = corpus.by_id.get(f"{m['old_act']}-{o}")
        out.append({"id": f"{m['old_act']}-{o}", "act": m["old_act"], "number": o,
                    "heading": sec["heading"] if sec else "", "source": m["source"],
                    "confidence": m["confidence"], "type": m["type"]})
    return out


def _add_refs(found: dict, corpus, act: str, nums: str, start: int, end: int, raw: str,
              inferred: bool = False) -> None:
    for n in _split_nums(nums):
        number = norm_number(n)
        if not number or not number[0].isdigit():
            continue
        sid = f"{act}-{number}"
        sec = corpus.by_id.get(sid)
        if sid in found:
            if (start, end) not in found[sid]["spans"]:
                found[sid]["count"] += 1
                found[sid]["spans"].append((start, end))
            continue
        found[sid] = {
            "section_id": sid,
            "act": act,
            "number": number,
            "label": f"{act} {n.strip()}",
            "heading": sec["heading"] if sec else None,
            "exists": sec is not None,
            "era": "old" if act in OLD_TO_NEW else "new",
            "converted": convert(act, number),
            "previous": reverse(act, number) if act not in OLD_TO_NEW else [],
            "raw": raw.strip(),
            "inferred": inferred,
            "start": start,
            "end": end,
            "spans": [(start, end)],
            "count": 1,
        }


def detect_references(text: str, default_act: str | None = None, code_act: str | None = None) -> list[dict]:
    """Returns unique references found in text, each resolved against the corpus.

    code_act: the act that "the Code" refers to in this document (see infer_code_act).
    """
    corpus = get_corpus()
    found: dict[str, dict] = {}
    spans: list[tuple[int, int]] = []

    if code_act:
        for m in OF_THE_CODE.finditer(text):
            spans.append((m.start(), m.end()))
            _add_refs(found, corpus, code_act, m.group("nums"), m.start(), m.end(), m.group(0), inferred=True)

    def add(act: str | None, nums: str, start: int, end: int, raw: str) -> None:
        act = act or default_act
        if act:
            _add_refs(found, corpus, act, nums, start, end, raw)

    for pattern in (FORWARD, ACT_FIRST, NUM_FIRST):
        for m in pattern.finditer(text):
            if any(s <= m.start() < e for s, e in spans):
                continue
            act = _act_code(m.groupdict().get("act"))
            if pattern is FORWARD and not act:
                # Look ahead a little for the act name ("sections 420 and 406 of the said Code (IPC)")
                tail = text[m.end(): m.end() + 40]
                am = re.search(ACT_PATTERN, tail, re.IGNORECASE)
                act = _act_code(am.group("act")) if am else None
            if not act and not default_act:
                continue
            nums, end = m.group("nums"), m.end()
            if pattern is ACT_FIRST:
                # "IPC 498A and 154 CrPC": the last number belongs to the act named right after it.
                if NEXT_ACT.match(text, end):
                    cut = list(SEPARATOR.finditer(nums))
                    if not cut:
                        continue  # "IPC 154 CrPC" is ambiguous; let NUM_FIRST read "154 CrPC"
                    nums = nums[:cut[-1].start()]
                    end = m.start("nums") + cut[-1].start()
            spans.append((m.start(), end))
            add(act, nums, m.start(), end, text[m.start():end])
    return sorted(found.values(), key=lambda r: r["start"])


def convert_text(text: str) -> dict:
    """Rewrites a passage, annotating every old-code reference with its 2023 equivalent."""
    refs = detect_references(text)
    # Several numbers can share one span ("u/s 420/406/34 IPC"): group them by span.
    spans: dict[tuple[int, int], list[str]] = {}
    for r in refs:
        targets = spans.setdefault((r["start"], r["end"]), [])
        for c in r["converted"]:
            label = f"{c['act']} {c['number']}"
            if label not in targets:
                targets.append(label)
    out, last = [], 0
    for (start, end), targets in sorted(spans.items()):
        if start < last:
            continue
        out.append(text[last:end])
        if targets:
            out.append(" [→ " + ", ".join(targets) + "]")
        last = end
    out.append(text[last:])
    return {"converted_text": "".join(out), "references": refs,
            "old_references": sum(1 for r in refs if r["era"] == "old"),
            "converted_count": sum(1 for r in refs if r["converted"])}
