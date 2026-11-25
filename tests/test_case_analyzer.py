"""Case Analyzer: offline rules, the Groq judge (with a fake Groq), the API, and the evaluation script."""
import pytest

from backend import case_analyzer, llm

SCOOTY = ("Two friends and I were riding a scooty. I was drunk and we hit a car parked on the street. The car owner "
          "is suing us for the damage and also falsely claims we hit her and physically abused her.")


def by_id(result):
    return {c["id"]: c for c in result["candidates"]}


def test_offline_facts_and_role():
    f = case_analyzer.offline_facts(SCOOTY)
    assert f["user_role"] == "accused"
    on = {k for k, v in f["flags"].items() if v}
    assert {"vehicle", "intoxication", "property_damage", "false_accusation"} <= on
    assert not f["flags"]["death"]
    assert case_analyzer.offline_facts("Someone stole my bike from outside my office")["user_role"] == "complainant"
    assert case_analyzer.offline_facts("Mere pati mujhe maarte hain aur dahej maangte hain")["user_role"] == "complainant"


def test_offline_analysis_of_drunk_riding_case():
    r = case_analyzer.analyze(SCOOTY)
    c = by_id(r)
    assert c["BNS-281"]["verdict"] == "applies"           # rash riding
    assert c["BNS-324"]["verdict"] == "applies"           # mischief: damage to the car
    assert c["BNS-115"]["verdict"] == "needs_info"        # hurt: alleged and disputed
    for death_section in ("BNS-106", "BNS-103"):          # no death -> never "applies"
        assert death_section not in c or c[death_section]["verdict"] == "unlikely"
    relief = {x["id"] for x in r["relief"]}
    assert {"BNSS-482", "BNS-248", "BNSS-528"} <= relief  # anticipatory bail, false charge, quashing
    assert any(o["section"] == "185" for o in r["outside_corpus"])  # Motor Vehicles Act
    assert r["severity"]["charges"] >= 2 and r["pipeline"]["judge"] == "rules"
    assert all(c["classification"] for c in r["candidates"] if c["verdict"] == "applies")


def test_role_override_changes_relief():
    r = case_analyzer.analyze("My neighbour cheated me of Rs 2 lakh with a fake job letter", role="complainant")
    assert {x["id"] for x in r["relief"]} == {"BNSS-173", "BNSS-175"}
    assert by_id(r)["BNS-318"]["verdict"] == "applies"


def test_rules_rule_out_sections_needing_a_death():
    c = {"id": "BNS-106", "number": "106", "ipc": ["IPC 304A"]}
    assert case_analyzer.rule_check(c, {"death": False})[0] == "unlikely"
    assert case_analyzer.rule_check(c, {"death": True}) is None
    attempt = {"id": "BNS-109", "number": "109", "ipc": ["IPC 307"]}
    assert case_analyzer.rule_check(attempt, {"intent_to_kill": False, "weapon": False})[0] == "unlikely"
    assert case_analyzer.rule_check(attempt, {"intent_to_kill": False, "weapon": True}) is None


def test_groq_judge_is_restricted_to_real_sections(monkeypatch):
    calls = []

    def fake_chat_json(messages, **kw):
        prompt = messages[0]["content"]
        calls.append(prompt[:30])
        if prompt.startswith("You analyse incidents"):
            return {"summary": "The user rode a scooter drunk and hit a parked car.", "formal_facts": "The accused...",
                    "user_role": "accused", "flags": {"vehicle": True, "intoxication": True, "property_damage": True,
                                                       "false_accusation": True, "injury": True},
                    "allegations_against_user": ["hit the car owner"], "missing_info": ["Was anyone hurt?"]}
        return {"assessments": [{"id": "BNS-281", "verdict": "applies", "against": "user", "reason": "rash riding"},
                                {"id": "BNS-324", "verdict": "applies", "against": "user", "reason": "car damaged"}],
                "additional": [{"id": "BNS-9999", "reason": "invented"}, {"id": "BNS 356", "reason": "defamation"}],
                "outside_corpus": [{"law": "Motor Vehicles Act, 1988", "section": "185", "reason": "drunk riding"}]}

    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "chat_json", fake_chat_json)
    monkeypatch.setattr(llm, "chat", lambda *a, **k: "You may face [BNS 281] and [BNS 999]. This is legal information, not legal advice.")
    r = case_analyzer.analyze(SCOOTY)
    c = by_id(r)
    assert r["facts"]["source"] == "groq" and r["pipeline"]["judge"] == "groq"
    assert c["BNS-281"]["decided_by"] == "groq" and c["BNS-281"]["against"] == "user"
    assert "BNS-9999" not in c                               # invented section rejected
    assert c["BNS-356"]["sources"] == {"groq_added": True}   # real section accepted
    assert r["advice_verification"]["total"] == 2 and r["advice_verification"]["grounded"] == 1
    assert len(calls) == 2


def test_analyze_api(client, auth):
    r = client.post("/api/analyze", json={"text": SCOOTY}, headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["facts"]["user_role"] == "accused" and body["relief"]
    assert client.post("/api/analyze", json={"text": "too short"}, headers=auth).status_code == 400


def test_pipeline_evaluation_metrics(monkeypatch):
    pytest.importorskip("sklearn")
    from backend.ml import section_model
    from ml import evaluate_case_pipeline as ev
    from test_predictor import SYNTHETIC

    texts = [t for ex in SYNTHETIC.values() for t in ex * 3]
    labels = [[sec] for sec, ex in SYNTHETIC.items() for _ in ex * 3]
    model = section_model.train(texts, labels, max_features=2000, min_df=1, n_jobs=1, log=lambda *_: None)
    answers = iter([["379"], ["379", "411"],   # case 1: groq, hybrid (411 is not a candidate -> dropped)
                    ["302", "999"], ["302"]])   # case 2: groq invents 999
    monkeypatch.setattr(ev, "ask", lambda prompt, user: next(answers))
    report = ev.run([("the accused stole the motorcycle", ["379"]),
                     ("he shot the victim dead with a pistol", ["302"])], model, k=3, log=lambda *_: None)
    m = report["methods"]
    assert report["cases"] == 2 and m["hybrid"]["f1"] == 1.0
    assert m["groq"]["not_a_real_ipc_section"] == 1
    assert m["model"]["recall"] == 1.0
