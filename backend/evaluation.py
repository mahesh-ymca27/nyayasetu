"""Retrieval benchmark: compares keyword (TF-IDF), BM25 and NyayaSetu hybrid retrieval."""
from __future__ import annotations

import json
import statistics
from functools import lru_cache

from .config import DATA_DIR
from .corpus import get_corpus
from .search import search

METHODS = {
    "keyword": "TF-IDF keyword (baseline)",
    "bm25": "Okapi BM25",
    "hybrid": "NyayaSetu Hybrid (BM25 + Hindi vocab + reference resolution + mapping boost)",
}


def load_questions() -> list[dict]:
    return json.loads((DATA_DIR / "eval_questions.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def run_benchmark(k: int = 10) -> dict:
    questions = load_questions()
    report = {"questions": len(questions), "k": k, "methods": {}, "by_kind": {}, "rows": []}
    rows = {i: {"q": q["q"], "lang": q["lang"], "kind": q["kind"], "gold": q["gold"], "ranks": {}}
            for i, q in enumerate(questions)}
    for method in METHODS:
        hits1 = hits3 = hits5 = 0
        rr, lat = [], []
        kinds: dict[str, list[int]] = {}
        for i, q in enumerate(questions):
            res = search(q["q"], method=method, k=k)
            ids = [r["id"] for r in res["results"]]
            rank = next((pos + 1 for pos, sid in enumerate(ids) if sid in q["gold"]), None)
            rows[i]["ranks"][method] = rank
            hits1 += rank == 1
            hits3 += bool(rank and rank <= 3)
            hits5 += bool(rank and rank <= 5)
            rr.append(1 / rank if rank else 0.0)
            lat.append(res["latency_ms"])
            kinds.setdefault(q["kind"], []).append(1 if rank and rank <= 3 else 0)
        n = len(questions)
        report["methods"][method] = {
            "label": METHODS[method],
            "hit@1": round(hits1 / n, 3),
            "hit@3": round(hits3 / n, 3),
            "hit@5": round(hits5 / n, 3),
            "mrr": round(sum(rr) / n, 3),
            "latency_ms": round(statistics.mean(lat), 2),
        }
        for kind, vals in kinds.items():
            report["by_kind"].setdefault(kind, {})[method] = round(sum(vals) / len(vals), 3)
    report["rows"] = list(rows.values())
    report["alignment"] = get_corpus().alignment_report
    return report
