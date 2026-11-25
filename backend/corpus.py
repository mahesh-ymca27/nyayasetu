"""Loads the legal corpus (sections, mappings, offence classification) into memory once."""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from functools import lru_cache

from .config import DATA_DIR

OLD_TO_NEW = {"IPC": "BNS", "CrPC": "BNSS", "IEA": "BSA"}
NEW_TO_OLD = {v: k for k, v in OLD_TO_NEW.items()}


def norm_number(number: str) -> str:
    """'420', '65-B', '41 A', '103(1)' -> '420', '65B', '41A', '103'."""
    n = re.sub(r"\(.*?\)", "", str(number)).replace("-", "").replace(" ", "").upper()
    return n.strip(".")


def roman_to_int(r: str) -> int:
    vals = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
    r = r.upper().replace("CHAPTER", "").strip()
    total, prev = 0, 0
    for ch in reversed(r):
        v = vals.get(ch, 0)
        total = total - v if v < prev else total + v
        prev = max(prev, v)
    return total


class Corpus:
    def __init__(self) -> None:
        self.acts: list[dict] = json.loads((DATA_DIR / "acts.json").read_text(encoding="utf-8"))
        self.sections: list[dict] = json.loads((DATA_DIR / "sections.json").read_text(encoding="utf-8"))
        self.mappings: list[dict] = json.loads((DATA_DIR / "mappings.json").read_text(encoding="utf-8"))
        self.classification: list[dict] = json.loads((DATA_DIR / "classification.json").read_text(encoding="utf-8"))
        self.alignment_report: dict = json.loads((DATA_DIR / "alignment_report.json").read_text(encoding="utf-8"))

        self.by_id: dict[str, dict] = {s["id"]: s for s in self.sections}
        self.act_meta: dict[str, dict] = {a["code"]: a for a in self.acts}

        # old -> new and new -> old lookups
        self.new_from_old: dict[tuple[str, str], list[dict]] = defaultdict(list)
        self.old_from_new: dict[tuple[str, str], dict] = {}
        for m in self.mappings:
            self.old_from_new[(m["new_act"], m["new"])] = m
            for o in m["old"]:
                self.new_from_old[(m["old_act"], o)].append(m)

        self.class_by_section: dict[str, list[dict]] = defaultdict(list)
        for c in self.classification:
            self.class_by_section[c["section"]].append(c)

    # ------------------------------------------------------------------ lookups
    def get(self, act: str, number: str) -> dict | None:
        return self.by_id.get(f"{act}-{norm_number(number)}")

    def resolve_act(self, name: str) -> str | None:
        return ACT_ALIASES.get(re.sub(r"[\s.]", "", name.lower()))

    def classification_for(self, section_id: str) -> list[dict]:
        act, _, num = section_id.partition("-")
        return self.class_by_section.get(num, []) if act == "BNS" else []

    def summary(self, section: dict, text_chars: int = 320) -> dict:
        return {
            "id": section["id"],
            "act": section["act"],
            "number": section["number"],
            "heading": section["heading"],
            "chapter": section["chapter"],
            "chapter_name": section["chapter_name"],
            "snippet": section["text"][:text_chars],
        }

    # ---------------------------------------------------------------- statistics
    @lru_cache(maxsize=1)
    def stats(self) -> dict:
        per_act = Counter(s["act"] for s in self.sections)
        bns_chapters: dict[str, dict] = {}
        for s in self.sections:
            if s["act"] != "BNS" or not s["chapter"]:
                continue
            ch = bns_chapters.setdefault(
                s["chapter"], {"chapter": s["chapter"], "name": s["chapter_name"], "sections": 0}
            )
            ch["sections"] += 1
        chapters = sorted(bns_chapters.values(), key=lambda c: roman_to_int(c["chapter"]))
        types = Counter((m["new_act"], m["type"]) for m in self.mappings)
        cog = Counter("Cognizable" if c["cognizable"].lower().startswith("cognizable") else
                      "Non-cognizable" if c["cognizable"].lower().startswith("non") else "Depends"
                      for c in self.classification)
        bail = Counter("Bailable" if c["bailable"].lower().startswith("bailable") else
                       "Non-bailable" if c["bailable"].lower().startswith("non") else "Depends"
                       for c in self.classification)
        courts = Counter(_court(c["triable_by"]) for c in self.classification)
        new_offences = [
            self.summary(self.by_id[f"BNS-{m['new']}"], 200)
            for m in self.mappings
            if m["new_act"] == "BNS" and m["type"] == "new_provision" and f"BNS-{m['new']}" in self.by_id
        ]
        return {
            "acts": len(self.acts),
            "sections": len(self.sections),
            "per_act": dict(per_act),
            "mappings": len(self.mappings),
            "official_mappings": sum(1 for m in self.mappings if m["source"] == "official"),
            "classified_offences": len(self.classification),
            "bns_chapters": chapters,
            "mapping_types": {f"{a}:{t}": n for (a, t), n in types.items()},
            "cognizable": dict(cog),
            "bailable": dict(bail),
            "courts": dict(courts.most_common(6)),
            "new_offences": new_offences,
            "alignment": self.alignment_report,
        }


def _court(text: str) -> str:
    t = text.lower()
    if "court of session" in t:
        return "Court of Session"
    if "any magistrate" in t:
        return "Any Magistrate"
    if "first class" in t:
        return "Magistrate First Class"
    if "according as" in t or "by which" in t:
        return "As per offence abetted"
    return "Other"


ACT_ALIASES = {
    "ipc": "IPC", "indianpenalcode": "IPC", "penalcode": "IPC", "i.p.c": "IPC",
    "crpc": "CrPC", "codeofcriminalprocedure": "CrPC", "criminalprocedurecode": "CrPC",
    "iea": "IEA", "evidenceact": "IEA", "indianevidenceact": "IEA",
    "bns": "BNS", "bharatiyanyayasanhita": "BNS", "nyayasanhita": "BNS",
    "bnss": "BNSS", "bharatiyanagariksurakshasanhita": "BNSS", "nagariksurakshasanhita": "BNSS",
    "bsa": "BSA", "bharatiyasakshyaadhiniyam": "BSA", "sakshyaadhiniyam": "BSA",
}


@lru_cache(maxsize=1)
def get_corpus() -> Corpus:
    return Corpus()
