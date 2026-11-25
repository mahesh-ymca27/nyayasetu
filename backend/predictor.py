"""Section Predictor service: loads the trained model (if present) and maps IPC predictions to BNS.

If the model file or scikit-learn is missing, `status()` says so and the API falls back to
search-based suggestions, so the rest of the app is never affected.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from .config import ROOT
from .corpus import get_corpus
from .detector import convert
from .search import expand_query, search

MODELS_DIR = Path(os.environ.get("NYAYASETU_MODELS_DIR", ROOT / "models"))
MODEL_PATH = MODELS_DIR / "section_predictor.joblib"
METRICS_PATH = MODELS_DIR / "section_predictor_metrics.json"

_lock = threading.Lock()
_state: dict = {"model": None, "vectorizer": None, "error": None, "mtime": None}


def _load():
    """Loads (or reloads after retraining) the model. Returns (model, vectorizer) or (None, None)."""
    with _lock:
        if not MODEL_PATH.exists():
            _state.update(model=None, vectorizer=None, error="not_trained", mtime=None)
            return None, None
        mtime = MODEL_PATH.stat().st_mtime
        if _state["model"] is not None and _state["mtime"] == mtime:
            return _state["model"], _state["vectorizer"]
        try:
            from .ml import section_model

            model = section_model.load(MODEL_PATH)
            vec = section_model.rebuild_vectorizer(model)
            _state.update(model=model, vectorizer=vec, error=None, mtime=mtime)
        except ImportError:
            _state.update(model=None, vectorizer=None, error="missing_dependencies", mtime=None)
        except Exception as e:  # noqa: BLE001 - corrupt or incompatible file
            _state.update(model=None, vectorizer=None, error=f"load_failed: {e}", mtime=None)
        return _state["model"], _state["vectorizer"]


def metrics() -> dict | None:
    try:
        return json.loads(METRICS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def status() -> dict:
    model, _ = _load()
    messages = {
        "not_trained": "The model has not been trained yet. Run: python -m ml.train_section_predictor",
        "missing_dependencies": "scikit-learn is not installed. Run: pip install -r requirements.txt",
    }
    err = _state["error"]
    return {
        "available": model is not None,
        "error": err,
        "message": messages.get(err, err) if err else None,
        "labels": len(model["labels"]) if model else 0,
        "threshold": model.get("threshold") if model else None,
        "metrics": metrics(),
    }


def predict(text: str, k: int = 5) -> dict:
    t0 = time.perf_counter()
    corpus = get_corpus()
    # Hindi/Hinglish words get English legal terms, since the model was trained on English facts.
    expanded, added = expand_query(text)
    out: dict = {"text": text, "added_terms": added, "model": status()}

    model, vec = _load()
    predictions = []
    if model is not None:
        from .ml import section_model

        P = section_model.scores(model, [expanded], vectorizer=vec)[0]
        order = P.argsort()[::-1][:k]
        for i in order:
            number = model["labels"][i]
            ipc = corpus.get("IPC", number)
            predictions.append({
                "ipc": f"IPC {number}",
                "ipc_id": f"IPC-{number}",
                "ipc_heading": ipc["heading"] if ipc else "",
                "probability": round(float(P[i]), 4),
                "above_threshold": bool(P[i] >= model["threshold"]),
                "bns": [{**c, "classification": corpus.classification_for(c["id"])[:1]}
                        for c in convert("IPC", number)],
            })
    out["predictions"] = predictions

    # Independent second opinion from the search engine (BNS only), to show agreement.
    found = search(text, method="hybrid", k=k, acts=["BNS"])["results"]
    model_bns = {b["id"] for p in predictions for b in p["bns"]}
    out["search_suggestions"] = [{**r, "agrees_with_model": r["id"] in model_bns} for r in found]
    out["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return out
