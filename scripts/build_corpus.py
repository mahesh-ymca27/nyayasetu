"""Build NyayaSetu's legal corpus from the open datasets.

Sources (both CC0 / public domain, statutes reproducible under Copyright Act 1957 s.52(1)(q)):
  * kanoonhq/open-laws            -> full text of IPC, CrPC, IEA, BNS, BNSS, BSA
  * JasonTKG/bns-sections         -> official NCRB BNS<->IPC table + BNSS First Schedule classification

Usage:
    python scripts/build_corpus.py --open-laws <path to open-laws/data> --bns <path to bns-sections>

Outputs JSON files into data/.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data"

ACTS = {
    "A1860-45": {"code": "IPC", "name": "Indian Penal Code", "year": 1860, "era": "old", "successor": "BNS"},
    "A1974-2": {"code": "CrPC", "name": "Code of Criminal Procedure", "year": 1973, "era": "old", "successor": "BNSS"},
    "A1872-1": {"code": "IEA", "name": "Indian Evidence Act", "year": 1872, "era": "old", "successor": "BSA"},
    "A2023-45": {"code": "BNS", "name": "Bharatiya Nyaya Sanhita", "year": 2023, "era": "new", "predecessor": "IPC"},
    "A2023-46": {"code": "BNSS", "name": "Bharatiya Nagarik Suraksha Sanhita", "year": 2023, "era": "new", "predecessor": "CrPC"},
    "A2023-47": {"code": "BSA", "name": "Bharatiya Sakshya Adhiniyam", "year": 2023, "era": "new", "predecessor": "IEA"},
}

TOKEN = re.compile(r"[a-z]+")
STOP = set(
    "the of and or to in a an by for on with as at be is any which that this from such other under who whose "
    "shall may where when his her it its not person persons section sections etc".split()
)


def clean(value):
    return None if value in (None, "None", "") else value


def tokens(text: str) -> list[str]:
    return [t for t in TOKEN.findall(text.lower()) if t not in STOP and len(t) > 2]


def load_acts(open_laws: Path) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    with gzip.open(open_laws / "indian_central_acts_complete.jsonl.gz", "rt", encoding="utf-8") as fh:
        for line in fh:
            act = json.loads(line)
            meta = ACTS.get(act["act_id"])
            if not meta:
                continue
            code = meta["code"]
            secs = []
            for s in act["sections"]:
                if s.get("structural_unit") not in (None, "section"):
                    continue
                number = (s.get("slug") or "").upper()
                if not number:
                    continue
                secs.append(
                    {
                        "id": f"{code}-{number}",
                        "act": code,
                        "number": number,
                        "heading": (s.get("heading") or "").strip().rstrip("."),
                        "chapter": clean(s.get("chapter_id")) or "",
                        "chapter_name": clean(s.get("chapter_name")) or "",
                        "text": (s.get("full_text") or "").strip(),
                    }
                )
            out[code] = secs
    return out


def load_bns_ipc(bns_dir: Path) -> list[dict]:
    rows = []
    with open(bns_dir / "bns_ipc_mapping.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            # NCRB writes the literal word "new" for offences with no IPC predecessor.
            ipc = [x for x in r["ipc_provisions_listed_by_government_table"].split() if x.lower() != "new"]
            rows.append(
                {
                    "old_act": "IPC",
                    "new_act": "BNS",
                    "new": r["bns_section"].upper(),
                    "old": [x.upper() for x in ipc],
                    "source": "official",
                    "confidence": 1.0,
                    "type": "new_provision" if not ipc else ("merged" if len(ipc) > 1 else "direct"),
                }
            )
    return rows


def load_classification(bns_dir: Path) -> list[dict]:
    rows = []
    with open(bns_dir / "bns_classification.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            m = re.match(r"(\d+)", r["provision"])
            if not m:
                continue
            rows.append(
                {
                    "provision": r["provision"],
                    "section": m.group(1),
                    "offence": r["offence"],
                    "punishment": r["punishment"],
                    "cognizable": r["cognizable"],
                    "bailable": r["bailable"],
                    "triable_by": r["triable_by"],
                    "status": r["status"],
                }
            )
    return rows


def tfidf_vectors(docs: list[list[str]]) -> list[dict[str, float]]:
    df = Counter()
    for d in docs:
        df.update(set(d))
    n = len(docs)
    vecs = []
    for d in docs:
        tf = Counter(d)
        v = {t: (1 + math.log(c)) * math.log((n + 1) / (df[t] + 1)) for t, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vecs.append({t: x / norm for t, x in v.items()})
    return vecs


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(w * b.get(t, 0.0) for t, w in a.items())


def align(old: list[dict], new: list[dict], old_code: str, new_code: str) -> list[dict]:
    """Automatic cross-code alignment: heading similarity (weight 0.6) + body TF-IDF cosine (0.4).

    Also uses a small positional prior: replacement codes keep the overall order of the old code.
    """
    heads = tfidf_vectors([tokens(s["heading"]) * 3 + tokens(s["chapter_name"]) for s in old + new])
    bodies = tfidf_vectors([tokens(s["text"][:1500]) for s in old + new])
    ho, hn = heads[: len(old)], heads[len(old):]
    bo, bn = bodies[: len(old)], bodies[len(old):]
    rows = []
    for j, s in enumerate(new):
        best, best_i = 0.0, -1
        rel_new = j / max(1, len(new) - 1)
        for i in range(len(old)):
            score = 0.6 * cosine(hn[j], ho[i]) + 0.4 * cosine(bn[j], bo[i])
            rel_old = i / max(1, len(old) - 1)
            score *= 1.0 - 0.25 * min(1.0, abs(rel_new - rel_old) * 4)
            if score > best:
                best, best_i = score, i
        if best >= 0.35:
            rows.append(
                {
                    "old_act": old_code,
                    "new_act": new_code,
                    "new": s["number"],
                    "old": [old[best_i]["number"]],
                    "source": "auto-aligned",
                    "confidence": round(min(best, 1.0), 3),
                    "type": "direct" if best >= 0.6 else "modified",
                }
            )
        else:
            rows.append(
                {
                    "old_act": old_code,
                    "new_act": new_code,
                    "new": s["number"],
                    "old": [],
                    "source": "auto-aligned",
                    "confidence": round(best, 3),
                    "type": "new_provision",
                }
            )
    return rows


# Well-known transitions used to measure the aligner's accuracy (reported on the Evaluation page).
GOLD_ALIGN = {
    ("CrPC", "BNSS"): {"154": "173", "438": "482", "41": "35", "125": "144", "144": "163", "482": "528",
                       "161": "180", "164": "183", "173": "193", "167": "187", "437": "480", "439": "483",
                       "200": "223", "313": "351", "156": "175", "41A": "35", "50": "47", "57": "58"},
    ("IEA", "BSA"): {"65B": "63", "32": "26", "25": "23", "45": "39", "113A": "117", "113B": "118",
                     "3": "2", "101": "104", "106": "109", "24": "22", "60": "55", "74": "74"},
}

# Well-known transitions the aligner cannot find on its own, because the new code merged two old
# sections into one (the aligner links each new section to a single old one).
CURATED = {
    ("CrPC", "BNSS"): {"35": ["41", "41A"]},
    ("IEA", "BSA"): {"2": ["3"]},
}


def apply_curated(rows: list[dict], old_code: str, new_code: str) -> None:
    for new, olds in CURATED.get((old_code, new_code), {}).items():
        row = next((r for r in rows if r["new"] == new), None)
        if row is None:
            continue
        merged = list(dict.fromkeys(row["old"] + olds))
        row.update({"old": merged, "source": "curated", "confidence": 1.0,
                    "type": "merged" if len(merged) > 1 else "direct"})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--open-laws", required=True, type=Path)
    ap.add_argument("--bns", required=True, type=Path)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    acts = load_acts(args.open_laws)
    mappings = load_bns_ipc(args.bns)
    gold_report = {}
    for old_code, new_code in (("CrPC", "BNSS"), ("IEA", "BSA")):
        rows = align(acts[old_code], acts[new_code], old_code, new_code)
        # Accuracy is measured on the aligner's own output, before curated fixes are applied.
        gold = GOLD_ALIGN[(old_code, new_code)]
        new_to_old = {r["new"]: set(r["old"]) for r in rows}
        hits = sum(1 for o, n in gold.items() if o in new_to_old.get(n, set()))
        gold_report[f"{old_code}->{new_code}"] = {"correct": hits, "total": len(gold), "accuracy": round(hits / len(gold), 3)}
        apply_curated(rows, old_code, new_code)
        mappings.extend(rows)

    meta = []
    for act_id, m in ACTS.items():
        meta.append({**m, "act_id": act_id, "sections": len(acts[m["code"]])})

    (OUT / "acts.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False))
    all_secs = [s for code in ("BNS", "BNSS", "BSA", "IPC", "CrPC", "IEA") for s in acts[code]]
    (OUT / "sections.json").write_text(json.dumps(all_secs, ensure_ascii=False))
    (OUT / "mappings.json").write_text(json.dumps(mappings, ensure_ascii=False))
    (OUT / "classification.json").write_text(json.dumps(load_classification(args.bns), ensure_ascii=False))
    (OUT / "alignment_report.json").write_text(json.dumps(gold_report, indent=1))
    print("sections:", len(all_secs), "mappings:", len(mappings))
    print("aligner accuracy:", json.dumps(gold_report))


if __name__ == "__main__":
    main()
