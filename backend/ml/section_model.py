"""Section Predictor model: case facts -> applicable IPC sections (multi-label).

Model: TF-IDF features (word 1-2 grams) + one logistic-regression classifier per section
(one-vs-rest), with class weighting for the heavy label imbalance and a decision threshold tuned
on the dev set for macro-F1.

The trained model is stored as plain arrays (vocabulary, idf, weight matrix, biases) so that
prediction needs only numpy and scikit-learn's TfidfVectorizer, and the file stays small.
numpy / scikit-learn are imported inside functions, so the rest of the app works without them.
"""
from __future__ import annotations

import re
import time
from typing import Iterable

LABEL_NUMBER = re.compile(r"(?<!\d)(\d{1,4})(?:\s*[-‐–]?\s*([A-Za-z]{1,2}))?(?![A-Za-z\d])")


def normalize_label(label: str) -> str | None:
    """'Section 302', 'IPC_302', 'Section 120-B', 'Section 498 A', '1860_Section 34' -> '302', '302', '120B', '498A', '34'.

    Takes the last section number in the string; 4-digit numbers are years (e.g. 1860), not sections."""
    found = [(n + s).upper() for n, s in LABEL_NUMBER.findall(str(label)) if len(n) <= 3]
    return found[-1] if found else None


def join_text(text) -> str:
    if isinstance(text, (list, tuple)):
        text = " ".join(str(t) for t in text)
    return str(text or "")[:20000]


def build_vectorizer(max_features: int = 60000, min_df: int = 3):
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer

    return TfidfVectorizer(lowercase=True, stop_words="english", ngram_range=(1, 2), sublinear_tf=True,
                           min_df=min_df, max_df=0.9, max_features=max_features, dtype=np.float32)


def train(texts: list[str], labels: list[list[str]], C: float = 4.0, max_features: int = 60000,
          min_df: int = 3, n_jobs: int = -1, log=print) -> dict:
    """Fits the model and returns it as a dict of arrays (see module docstring)."""
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.multiclass import OneVsRestClassifier
    from sklearn.preprocessing import MultiLabelBinarizer

    t0 = time.time()
    mlb = MultiLabelBinarizer()
    Y = mlb.fit_transform(labels)
    keep = Y.sum(axis=0) > 0
    vec = build_vectorizer(max_features=max_features, min_df=min_df)
    X = vec.fit_transform(texts)
    # Canonical CSR (sorted indices, no duplicates). Otherwise the parallel workers, which receive X
    # as a read-only memory map, try to sort it in place and fail with
    # "WRITEBACKIFCOPY base is read-only" (seen on Windows).
    X.sum_duplicates()
    X.sort_indices()
    log(f"  features: {X.shape[1]:,} terms, {X.shape[0]:,} documents, {Y.shape[1]} sections")

    def fit(jobs):
        c = OneVsRestClassifier(
            LogisticRegression(C=C, solver="liblinear", class_weight="balanced", max_iter=300), n_jobs=jobs)
        c.fit(X, Y[:, keep])
        return c

    try:
        clf = fit(n_jobs)
    except ValueError as e:
        if n_jobs == 1 or "read-only" not in str(e):
            raise
        log("  parallel training failed on this machine; retrying on one CPU core (slower)")
        clf = fit(1)
    W = np.vstack([e.coef_.ravel() for e in clf.estimators_]).astype(np.float32)
    b = np.array([e.intercept_[0] for e in clf.estimators_], dtype=np.float32)
    log(f"  trained in {time.time() - t0:.0f}s")
    return {
        "vocabulary": {k: int(v) for k, v in vec.vocabulary_.items()},
        "idf": vec.idf_.astype(np.float32),
        "vectorizer_params": {"ngram_range": (1, 2), "stop_words": "english", "sublinear_tf": True},
        "W": W,
        "b": b,
        "labels": [str(x) for x in np.array(mlb.classes_)[keep]],
        "threshold": 0.5,
    }


def rebuild_vectorizer(model: dict):
    """Recreates the fitted TfidfVectorizer from stored arrays."""
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer

    p = model["vectorizer_params"]
    vec = TfidfVectorizer(lowercase=True, stop_words=p["stop_words"], ngram_range=tuple(p["ngram_range"]),
                          sublinear_tf=p["sublinear_tf"], dtype=np.float32, vocabulary=model["vocabulary"])
    vec.idf_ = np.asarray(model["idf"], dtype=np.float64)
    return vec


def scores(model: dict, texts: Iterable[str], vectorizer=None):
    """Probability per section for each text: sigmoid(X W^T + b)."""
    import numpy as np

    vec = vectorizer or rebuild_vectorizer(model)
    X = vec.transform(list(texts))
    z = X @ model["W"].T + model["b"]
    return 1.0 / (1.0 + np.exp(-np.asarray(z)))


def predict_sets(P, threshold: float):
    """Sections above the threshold; always at least the single best one."""
    import numpy as np

    out = P >= threshold
    out[np.arange(len(P)), P.argmax(axis=1)] = True
    return out


def evaluate(model: dict, texts: list[str], labels: list[list[str]], threshold: float | None = None) -> dict:
    import numpy as np
    from sklearn.metrics import f1_score

    P = scores(model, texts)
    index = {l: i for i, l in enumerate(model["labels"])}
    Y = np.zeros(P.shape, dtype=bool)
    for r, ls in enumerate(labels):
        for l in ls:
            if l in index:
                Y[r, index[l]] = True
    pred = predict_sets(P, model["threshold"] if threshold is None else threshold)
    order = np.argsort(-P, axis=1)
    has = Y.any(axis=1)
    top1 = Y[np.arange(len(Y)), order[:, 0]]
    hit3 = np.array([Y[r, order[r, :3]].any() for r in range(len(Y))])
    rec5 = np.array([Y[r, order[r, :5]].sum() / max(1, Y[r].sum()) for r in range(len(Y))])
    return {
        "documents": int(len(texts)),
        "macro_f1": round(float(f1_score(Y, pred, average="macro", zero_division=0)), 4),
        "micro_f1": round(float(f1_score(Y, pred, average="micro", zero_division=0)), 4),
        "precision_at_1": round(float(top1[has].mean()) if has.any() else 0.0, 4),
        "hit_at_3": round(float(hit3[has].mean()) if has.any() else 0.0, 4),
        "recall_at_5": round(float(rec5[has].mean()) if has.any() else 0.0, 4),
    }


def tune_threshold(model: dict, texts: list[str], labels: list[list[str]]) -> tuple[float, list[dict]]:
    """Picks the decision threshold with the best macro-F1 on held-out data."""
    curve = []
    for t in [round(0.05 * i, 2) for i in range(1, 20)]:
        m = evaluate(model, texts, labels, threshold=t)
        curve.append({"threshold": t, "macro_f1": m["macro_f1"], "micro_f1": m["micro_f1"]})
    best = max(curve, key=lambda c: (c["macro_f1"], c["micro_f1"]))
    model["threshold"] = best["threshold"]
    return best["threshold"], curve


def save(model: dict, path) -> int:
    import joblib

    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, path, compress=3)
    return path.stat().st_size


def load(path) -> dict:
    import joblib

    return joblib.load(path)
