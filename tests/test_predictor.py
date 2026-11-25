"""Section Predictor: label parsing, the no-model fallback, and the full train -> save -> load -> predict
pipeline on a tiny synthetic dataset (the last part needs scikit-learn and runs in CI)."""
import pytest

from backend import predictor
from backend.ml import section_model
from ml.train_section_predictor import to_examples


@pytest.mark.parametrize("raw, expected", [
    ("Section 302", "302"), ("IPC_420", "420"), ("120B", "120B"), ("Section 498A", "498A"),
    ("Indian Penal Code, 1860_Section 34", "34"), ("no number", None),
    ("Section 120-B", "120B"), ("Section 304 B", "304B"), ("Section 304–A", "304A"), ("Section 2", "2"),
    ("Section 376(2)", "376"), ("IPC 498a", "498A"),
])
def test_normalize_label(raw, expected):
    assert section_model.normalize_label(raw) == expected


def test_training_data_columns_are_detected():
    rows = [{"id": 1, "facts": ["He stole", "a bike."], "statutes": ["Section 379"]},
            {"id": 2, "facts": "x", "statutes": []}]
    texts, labels = to_examples(rows)
    assert texts == ["He stole a bike."] and labels == [["379"]]


def test_labels_as_ids_into_statutes_table():
    from ml.train_section_predictor import resolve, statute_lookup

    with_ids = statute_lookup([{"id": 5, "name": "Section 302"}, {"id": 34, "name": "Section 34"},
                               {"id": "S12", "name": "Section 498A", "text": "Husband or relative of husband..."}])
    assert resolve(5, with_ids) == "302" and resolve("5", with_ids) == "302"
    assert resolve(34, with_ids) == "34" and resolve("S12", with_ids) == "498A"
    assert resolve("Section 307", with_ids) == "307"  # labels that are already names still work

    by_position = statute_lookup([{"name": "Section 302", "text": "Whoever commits murder shall be punished"},
                                  {"name": "Section 420", "text": "Whoever cheats and thereby dishonestly induces"}])
    assert resolve(0, by_position) == "302" and resolve(1, by_position) == "420"

    texts, labels = to_examples([{"text": ["He stabbed him."], "labels": [5, 34]}], with_ids)
    assert labels == [["302", "34"]]


def test_predict_without_model_falls_back_to_search(client, auth):
    s = client.get("/api/predict/status", headers=auth).json()
    assert s["available"] is False and s["error"] == "not_trained"
    r = client.post("/api/predict", json={"text": "Someone stole my motorcycle from outside my house."}, headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["predictions"] == []
    assert {"BNS-303", "BNS-305"} & {x["id"] for x in body["search_suggestions"]}  # theft sections
    assert client.post("/api/predict", json={"text": "short"}, headers=auth).status_code == 400


SYNTHETIC = {
    "379": ["the accused stole the motorcycle parked outside the house", "theft of mobile phone from the shop counter",
            "he dishonestly took away the bicycle without consent", "jewellery was stolen from the locked almirah"],
    "302": ["the accused stabbed the deceased with a knife causing death", "he shot the victim dead with a pistol",
            "the deceased was strangled to death by the accused", "murder of the wife by pouring kerosene and setting fire"],
    "420": ["he took money promising a government job and gave a fake letter", "cheated the complainant by selling fake gold",
            "induced the victim to invest money in a fraudulent scheme", "took advance payment for a flat and never delivered it"],
}


@pytest.fixture
def tiny_model(tmp_path, monkeypatch):
    pytest.importorskip("sklearn")
    texts, labels = [], []
    for sec, examples in SYNTHETIC.items():
        for t in examples * 3:
            texts.append(t)
            labels.append([sec])
    # n_jobs=2 exercises the parallel (threading) path used on the laptop.
    model = section_model.train(texts, labels, max_features=2000, min_df=1, n_jobs=2, log=lambda *_: None)
    threshold, curve = section_model.tune_threshold(model, texts, labels)
    path = tmp_path / "section_predictor.joblib"
    section_model.save(model, path)
    monkeypatch.setattr(predictor, "MODEL_PATH", path)
    monkeypatch.setitem(predictor._state, "model", None)
    yield model, curve
    predictor._state.update(model=None, vectorizer=None, error=None, mtime=None)


def test_train_evaluate_save_load_predict(tiny_model):
    model, curve = tiny_model
    assert sorted(model["labels"]) == ["302", "379", "420"]
    assert len(curve) == 19 and 0 < model["threshold"] < 1
    m = section_model.evaluate(model, ["someone stole my motorcycle"], [["379"]])
    assert m["precision_at_1"] == 1.0

    assert predictor.status()["available"] is True
    out = predictor.predict("Someone stole my motorcycle from outside the house")
    top = out["predictions"][0]
    assert top["ipc_id"] == "IPC-379"
    assert [b["id"] for b in top["bns"]] == ["BNS-303"]
    probs = [p["probability"] for p in out["predictions"]]
    assert probs == sorted(probs, reverse=True)

    hindi = predictor.predict("मेरा मोबाइल चोरी हो गया, किसी ने दुकान से उठा लिया")
    assert "theft" in " ".join(hindi["added_terms"])


def test_parallel_and_single_core_training_agree():
    pytest.importorskip("sklearn")
    texts = [t for ex in SYNTHETIC.values() for t in ex * 3]
    labels = [[sec] for sec, ex in SYNTHETIC.items() for _ in ex * 3]
    quiet = dict(max_features=2000, min_df=1, log=lambda *_: None)
    a = section_model.train(texts, labels, n_jobs=3, **quiet)
    b = section_model.train(texts, labels, n_jobs=1, **quiet)
    assert a["labels"] == b["labels"] and abs(a["W"] - b["W"]).max() < 1e-5


def test_threshold_tuning_scores_texts_once(tiny_model, monkeypatch):
    model, _ = tiny_model
    calls = []
    real = section_model.scores
    monkeypatch.setattr(section_model, "scores", lambda *a, **k: calls.append(1) or real(*a, **k))
    texts = [t for ex in SYNTHETIC.values() for t in ex]
    labels = [[sec] for sec, ex in SYNTHETIC.items() for _ in ex]
    threshold, curve = section_model.tune_threshold(model, texts, labels)
    assert len(calls) == 1 and len(curve) == 19
    best = max(curve, key=lambda c: (c["macro_f1"], c["micro_f1"]))
    assert threshold == best["threshold"]
    # same numbers as the full evaluate() at that threshold
    assert section_model.evaluate(model, texts, labels, threshold=threshold)["macro_f1"] == best["macro_f1"]


def test_resolve_jobs():
    import os

    cpus = os.cpu_count() or 1
    assert section_model.resolve_jobs(1) == 1
    assert 1 <= section_model.resolve_jobs(-1) <= cpus
    assert section_model.resolve_jobs(10_000) == cpus


def test_reloaded_model_gives_same_scores(tiny_model, tmp_path):
    model, _ = tiny_model
    path = tmp_path / "copy.joblib"
    section_model.save(model, path)
    again = section_model.load(path)
    a = section_model.scores(model, ["fake gold was sold to him"])
    b = section_model.scores(again, ["fake gold was sold to him"])
    assert abs(a - b).max() < 1e-6
