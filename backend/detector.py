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


def detect_references(text: str, default_act: str | None = None) -> list[dict]:
    """Returns unique references found in text, each resolved against the corpus."""
    corpus = get_corpus()
    found: dict[str, dict] = {}
    spans: list[tuple[int, int]] = []

    def add(act: str | None, nums: str, start: int, end: int, raw: str) -> None:
        act = act or default_act
        if not act:
            return
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
                "start": start,
                "end": end,
                "spans": [(start, end)],
                "count": 1,
            }

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
            spans.append((m.start(), m.end()))
            add(act, m.group("nums"), m.start(), m.end(), m.group(0))
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
