"""Trains the Section Predictor on the IL-TUR Legal Statute Identification (LSI) dataset.

Usage (from the project folder, with the virtual environment active):
    pip install -r requirements-ml.txt
    python -m ml.train_section_predictor                 # downloads IL-TUR from Hugging Face
    python -m ml.train_section_predictor --data-dir D    # or: local train.json / dev.json / test.json
    python -m ml.train_section_predictor --quick         # 5,000 training cases, for a fast trial run

Output:
    models/section_predictor.joblib        the trained model
    models/section_predictor_metrics.json  test-set results, shown on the Evaluation Lab page
"""
from __future__ import annotations

import argparse
import json
import platform
import re
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.ml import section_model  # noqa: E402
from backend.predictor import METRICS_PATH, MODEL_PATH  # noqa: E402

HF_DATASET = "Exploration-Lab/IL-TUR"
TEXT_FIELDS = ("text", "facts", "document", "input", "fact")
LABEL_FIELDS = ("labels", "statutes", "label", "sections", "output")
SPLIT_NAMES = {"train": ("train",), "dev": ("dev", "validation", "valid", "val"), "test": ("test",)}


def pick(row: dict, names: tuple[str, ...], what: str):
    for n in names:
        if n in row:
            return row[n]
    raise SystemExit(f"Could not find the {what} column. Columns in the data: {list(row)}")


SECTION_WORD = re.compile(r"(?i)\bsection\b|\bs\.\s*\d|_\d")


def statute_lookup(rows) -> dict[str, str]:
    """Maps statute IDs to names using the dataset's 'statutes' table.

    IL-TUR's labels can be IDs into that table instead of section names. For each row the name is
    the shortest text that looks like a section ("Section 302"); every other value is treated as an ID."""
    lookup: dict[str, str] = {}
    for index, row in enumerate(rows or []):
        values = [v for v in row.values() if isinstance(v, (str, int)) and not isinstance(v, bool)]
        texts = [v for v in values if isinstance(v, str) and section_model.normalize_label(v)]
        named = [v for v in texts if SECTION_WORD.search(v)] or texts
        if not named:
            continue
        name = min(named, key=len)
        others = [v for v in values if v is not name]
        for v in others:
            lookup[str(v).strip()] = name
        if not any(isinstance(v, int) or (isinstance(v, str) and len(v) <= 12) for v in others):
            lookup.setdefault(str(index), name)  # no ID column: labels refer to the row position
    return lookup


def resolve(label, lookup: dict[str, str]) -> str | None:
    key = str(label).strip()
    return section_model.normalize_label(lookup.get(key, key))


def to_examples(rows, lookup: dict[str, str] | None = None) -> tuple[list[str], list[list[str]]]:
    lookup = lookup or {}
    texts, labels = [], []
    for row in rows:
        raw = pick(row, LABEL_FIELDS, "labels")
        raw = raw if isinstance(raw, (list, tuple)) else [raw]
        ls = sorted({x for x in (resolve(l, lookup) for l in raw) if x})
        text = section_model.join_text(pick(row, TEXT_FIELDS, "text"))
        if ls and text.strip():
            texts.append(text)
            labels.append(ls)
    return texts, labels


def load_from_hub() -> dict:
    try:
        from datasets import get_dataset_config_names, load_dataset
    except ImportError:
        raise SystemExit("The 'datasets' package is missing. Run: pip install -r requirements-ml.txt")
    try:
        configs = get_dataset_config_names(HF_DATASET)
    except Exception as e:  # noqa: BLE001
        raise SystemExit(
            f"Could not open {HF_DATASET} on Hugging Face ({e}).\n"
            f"If the dataset asks you to accept terms: open https://huggingface.co/datasets/{HF_DATASET} in the\n"
            "browser, accept, then run:  huggingface-cli login   and paste a token from\n"
            "https://huggingface.co/settings/tokens")
    config = next((c for c in configs if "lsi" in c.lower()), None)
    if not config:
        raise SystemExit(f"No LSI task found in {HF_DATASET}. Available tasks: {configs}")
    print(f"  dataset: {HF_DATASET}, task '{config}'")
    ds = load_dataset(HF_DATASET, config)
    out = {}
    for split, names in SPLIT_NAMES.items():
        name = next((n for n in names if n in ds), None)
        if name:
            out[split] = list(ds[name])
    if "statutes" in ds:
        out["statutes"] = list(ds["statutes"])
    return out


def load_from_dir(d: Path) -> dict:
    out = {}
    for split, names in SPLIT_NAMES.items():
        for n in names:
            f = d / f"{n}.json"
            if f.exists():
                data = json.loads(f.read_text(encoding="utf-8"))
                out[split] = data["data"] if isinstance(data, dict) and "data" in data else data
                break
    return out


def preview(splits: dict, lookup: dict[str, str]) -> None:
    """Prints what the raw labels look like, so a wrong label mapping is easy to spot."""
    rows = splits.get("train") or []
    if rows:
        first = rows[0]
        print(f"  columns: {list(first)}")
        raw = pick(first, LABEL_FIELDS, "labels")
        raw = raw if isinstance(raw, (list, tuple)) else [raw]
        print(f"  first case labels (raw): {raw[:6]}")
        print(f"  first case labels (read as): {[resolve(l, lookup) for l in raw[:6]]}")
    if lookup:
        sample = list(lookup.items())[:3]
        print(f"  statutes table: {len(lookup)} ID entries, e.g. {sample}")
        read = [section_model.normalize_label(n) for n in dict.fromkeys(lookup.values())]
        print(f"  {len(set(read))} distinct sections read from {len(read)} statute names")
        clashes = Counter(read)
        for sec, n in clashes.items():
            if n > 1:
                names = [v for v in dict.fromkeys(lookup.values()) if section_model.normalize_label(v) == sec]
                print(f"    WARNING: {names} are all read as IPC {sec}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", type=Path, help="folder with train.json, dev.json, test.json")
    ap.add_argument("--quick", action="store_true", help="train on 5,000 cases only (fast trial)")
    ap.add_argument("--check", action="store_true", help="only load the data and show the labels, then stop")
    ap.add_argument("--max-features", type=int, default=60000)
    ap.add_argument("--C", type=float, default=4.0)
    args = ap.parse_args()

    print("\n[1/5] Loading data")
    splits = load_from_dir(args.data_dir) if args.data_dir else load_from_hub()
    if "train" not in splits or "test" not in splits:
        raise SystemExit(f"Need train and test splits, found: {list(splits)}")
    lookup = statute_lookup(splits.pop("statutes", None))
    preview(splits, lookup)
    data = {s: to_examples(rows, lookup) for s, rows in splits.items()}
    if "dev" not in data:  # carve a dev set out of train if the dataset has none
        t, l = data["train"]
        cut = len(t) // 10
        data["dev"], data["train"] = (t[:cut], l[:cut]), (t[cut:], l[cut:])
    if args.quick:
        data["train"] = (data["train"][0][:5000], data["train"][1][:5000])
        data["dev"] = (data["dev"][0][:1500], data["dev"][1][:1500])
    for s in ("train", "dev", "test"):
        print(f"  {s:5}: {len(data[s][0]):,} cases")
    label_counts = Counter(l for ls in data["train"][1] for l in ls)
    from backend.corpus import get_corpus

    corpus = get_corpus()
    print(f"  sections in training data: {len(label_counts)}. Most common (check these look like real criminal cases):")
    for k, v in label_counts.most_common(10):
        sec = corpus.get("IPC", k)
        print(f"    IPC {k:5} {v:6,} cases   {sec['heading'][:60] if sec else '(not in the IPC text)'}")
    if args.check:
        print("\n--check given: stopping before training.")
        return

    print("\n[2/5] Training (TF-IDF + one logistic regression per section). This takes a few minutes.")
    t0 = time.time()
    model = section_model.train(*data["train"], C=args.C, max_features=args.max_features)
    train_seconds = round(time.time() - t0)

    print("\n[3/5] Tuning the decision threshold on the dev set")
    threshold, curve = section_model.tune_threshold(model, *data["dev"])
    print(f"  best threshold: {threshold}")

    print("\n[4/5] Evaluating on the test set (cases the model has never seen)")
    test = section_model.evaluate(model, *data["test"])
    for k, v in test.items():
        print(f"  {k:15} {v}")

    print("\n[5/5] Saving")
    size = section_model.save(model, MODEL_PATH)
    import sklearn

    report = {
        "model": "TF-IDF (1-2 grams) + one-vs-rest logistic regression, class-weighted",
        "dataset": f"{HF_DATASET} (LSI)" if not args.data_dir else str(args.data_dir),
        "quick_run": args.quick,
        "train_cases": len(data["train"][0]),
        "dev_cases": len(data["dev"][0]),
        "test_cases": len(data["test"][0]),
        "sections": len(model["labels"]),
        "features": len(model["vocabulary"]),
        "hyperparameters": {"C": args.C, "max_features": args.max_features, "ngram_range": [1, 2]},
        "threshold": threshold,
        "threshold_curve": curve,
        "test": test,
        "reference": {"name": "IL-TUR paper LSI baseline (macro-F1)", "macro_f1": 0.2808},
        "train_seconds": train_seconds,
        "model_size_mb": round(size / 1048576, 1),
        "trained_on": f"{platform.processor() or platform.machine()}, Python {platform.python_version()}, "
                      f"scikit-learn {sklearn.__version__}",
        "trained_at": time.strftime("%Y-%m-%d %H:%M"),
        "top_sections": [{"ipc": k, "train_cases": v} for k, v in label_counts.most_common(15)],
    }
    METRICS_PATH.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"  model:   {MODEL_PATH}  ({report['model_size_mb']} MB)")
    print(f"  metrics: {METRICS_PATH}")
    print("\nDone. Restart the app (python run.py) and open the Section Predictor page.\n")


if __name__ == "__main__":
    main()
