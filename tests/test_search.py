"""Retrieval quality. Thresholds lock in today's results so a later change cannot quietly lower them."""
import pytest

from backend.evaluation import run_benchmark
from backend.search import expand_query, search


@pytest.fixture(scope="module")
def report():
    return run_benchmark()


def test_hybrid_benchmark_does_not_regress(report):
    h = report["methods"]["hybrid"]
    assert h["mrr"] >= 0.82
    assert h["hit@3"] >= 0.92
    assert h["hit@5"] >= 0.97


def test_hybrid_beats_baselines(report):
    m = report["methods"]
    assert m["hybrid"]["mrr"] > m["bm25"]["mrr"] > m["keyword"]["mrr"]


@pytest.mark.parametrize("query, expected", [
    ("IPC 420 ka naya section kya hai", "BNS-318"),
    ("chain snatching", "BNS-304"),
    ("हत्या की सजा क्या है", "BNS-103"),
    ("how to get anticipatory bail", "BNSS-482"),
])
def test_known_queries_in_top_3(query, expected):
    top = [r["id"] for r in search(query, k=3)["results"]]
    assert expected in top


def test_hindi_vocabulary_expansion():
    _, added = expand_query("दहेज के लिए पत्नी")
    assert "dowry" in added and "wife" in added


def test_act_filter():
    res = search("theft", k=5, acts=["IPC"])["results"]
    assert res and all(r["act"] == "IPC" for r in res)
