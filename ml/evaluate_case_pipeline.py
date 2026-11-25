"""Compares three ways of finding the applicable IPC sections on IL-TUR test cases (known answers):

  1. model     NyayaSetu's trained Section Predictor alone
  2. groq      Groq alone: the LLM is asked which IPC sections apply
  3. hybrid    the Case Analyzer's idea: the model proposes 10 candidates, Groq picks among them

Usage (Groq key in .env, trained model in models/):
    python -m ml.evaluate_case_pipeline            # 60 test cases, about 120 Groq calls
    python -m ml.evaluate_case_pipeline --n 30     # fewer cases, faster

Output: models/case_pipeline_eval.json, shown on the Evaluation Lab page.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import llm, predictor  # noqa: E402
from backend.corpus import get_corpus  # noqa: E402
from backend.ml import section_model  # noqa: E402

OUT_PATH = predictor.MODELS_DIR / "case_pipeline_eval.json"
FACTS_CHARS = 3000  # long judgments are cut for the LLM (the model reads the full text)

GROQ_ONLY = """You are an expert in Indian criminal law. Read the facts of a case and list the sections of the
Indian Penal Code (IPC) that apply. Return JSON: {"sections": ["302", "34"]} with bare section numbers."""

HYBRID = """You are an expert in Indian criminal law. Read the facts of a case. From the CANDIDATE sections of the
Indian Penal Code below, choose every one that applies to these facts. Return JSON: {"sections": ["302", "34"]}.
Choose only from the candidates."""


def ask(prompt: str, user: str) -> list[str]:
    out = llm.chat_json([{"role": "system", "content": prompt}, {"role": "user", "content": user}], max_tokens=600)
    found = []
    for s in out.get("sections") or []:
        n = section_model.normalize_label(str(s))
        if n and n not in found:
            found.append(n)
    return found


def prf(pred: set[str], gold: set[str]) -> tuple[float, float, float]:
    tp = len(pred & gold)
    p = tp / len(pred) if pred else 0.0
    r = tp / len(gold) if gold else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def summarize(rows: list[dict], method: str, labels: set[str], corpus) -> dict:
    ps, rs, fs, tp, npred, ngold, invalid, outside = [], [], [], 0, 0, 0, 0, 0
    for row in rows:
        pred, gold = set(row[method]), set(row["gold"])
        p, r, f = prf(pred, gold)
        ps.append(p); rs.append(r); fs.append(f)
        tp += len(pred & gold); npred += len(pred); ngold += len(gold)
        invalid += sum(1 for s in pred if not corpus.get("IPC", s))
        outside += sum(1 for s in pred if s not in labels)
    mp = tp / npred if npred else 0.0
    mr = tp / ngold if ngold else 0.0
    n = len(rows) or 1
    return {
        "precision": round(sum(ps) / n, 4), "recall": round(sum(rs) / n, 4), "f1": round(sum(fs) / n, 4),
        "micro_f1": round(2 * mp * mr / (mp + mr), 4) if mp + mr else 0.0,
        "sections_per_case": round(npred / n, 2),
        "not_a_real_ipc_section": invalid,
        "outside_the_100_labels": outside,
    }


def run(cases: list[tuple[str, list[str]]], model: dict, k: int = 10, log=print) -> dict:
    corpus = get_corpus()
    vec = section_model.rebuild_vectorizer(model)
    labels = set(model["labels"])
    rows, errors, t0 = [], 0, time.time()
    for i, (text, gold) in enumerate(cases, 1):
        P = section_model.scores(model, [text], vectorizer=vec)[0]
        order = P.argsort()[::-1]
        model_pred = [model["labels"][j] for j in order if P[j] >= model["threshold"]] or [model["labels"][order[0]]]
        cands = [model["labels"][j] for j in order[:k]]
        facts = text[:FACTS_CHARS]
        cand_lines = "\n".join(f"- IPC {c}: {(corpus.get('IPC', c) or {}).get('heading', '')}" for c in cands)
        try:
            groq_pred = ask(GROQ_ONLY, f"FACTS:\n{facts}")
            hybrid_pred = [s for s in ask(HYBRID, f"FACTS:\n{facts}\n\nCANDIDATES:\n{cand_lines}") if s in cands]
        except llm.LLMError as e:
            errors += 1
            log(f"  case {i}: Groq error, skipped ({str(e)[:80]})")
            continue
        rows.append({"gold": gold, "model": model_pred, "groq": groq_pred, "hybrid": hybrid_pred or cands[:1],
                     "gold_in_candidates": len(set(gold) & set(cands)) / len(gold) if gold else 0.0})
        if i % 10 == 0 or i == len(cases):
            log(f"  {i}/{len(cases)} cases done ({time.time() - t0:.0f}s)")
    return {
        "cases": len(rows),
        "skipped_errors": errors,
        "candidates_k": k,
        "candidate_recall": round(sum(r["gold_in_candidates"] for r in rows) / max(1, len(rows)), 4),
        "methods": {m: summarize(rows, m, labels, corpus) for m in ("model", "groq", "hybrid")},
        "rows": rows,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=60, help="number of test cases (default 60)")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    if not llm.available():
        raise SystemExit("A Groq key is needed: put GROQ_API_KEY=... in .env")
    if not predictor.MODEL_PATH.exists():
        raise SystemExit("Train the model first: python -m ml.train_section_predictor")
    from ml.train_section_predictor import load_from_hub, statute_lookup, to_examples

    print("\n[1/3] Loading the model and the IL-TUR test set")
    model = section_model.load(predictor.MODEL_PATH)
    splits = load_from_hub()
    texts, labels = to_examples(splits["test"], statute_lookup(splits.get("statutes")))
    idx = random.Random(args.seed).sample(range(len(texts)), min(args.n, len(texts)))
    cases = [(texts[i], labels[i]) for i in idx]
    print(f"  {len(cases)} random test cases (seed {args.seed}); Groq model: {llm.settings.groq_model}")

    print("\n[2/3] Running model, Groq and hybrid on each case (2 Groq calls per case)")
    report = run(cases, model)

    print("\n[3/3] Results (example-based precision / recall / F1, averaged over cases)")
    print(f"  {'method':8} {'precision':>9} {'recall':>7} {'F1':>6} {'microF1':>8} {'per case':>8} {'not real IPC':>12}")
    for m, v in report["methods"].items():
        print(f"  {m:8} {v['precision']:9.3f} {v['recall']:7.3f} {v['f1']:6.3f} {v['micro_f1']:8.3f} "
              f"{v['sections_per_case']:8} {v['not_a_real_ipc_section']:12}")
    print(f"  model's top-{report['candidates_k']} candidates contain {report['candidate_recall']:.1%} of the correct sections")
    report.update(groq_model=llm.settings.groq_model, seed=args.seed, facts_chars=FACTS_CHARS,
                  evaluated_at=time.strftime("%Y-%m-%d %H:%M"))
    OUT_PATH.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"\n  saved {OUT_PATH}\n")


if __name__ == "__main__":
    main()
