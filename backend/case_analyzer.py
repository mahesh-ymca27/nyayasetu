"""Case Analyzer: a layered pipeline that turns an incident description into a structured analysis.

Each layer does the job it is best at, and the next layer checks it:

  1. Understand  (Groq, or keyword rules offline): summary, the user's role, fact flags such as
                 death / injury / property damage, and a formal court-style rewrite of the facts.
  2. Candidates  (NyayaSetu's trained model + BM25 search): sections that may apply. The model reads
                 the formal rewrite, which is closer to the judgment text it was trained on.
  3. Check       (fact rules, then Groq as a judge restricted to the candidates): applies / unlikely /
                 needs more facts, with a reason. Groq can only add sections that exist in the corpus.
  4. Facts       (official BNSS First Schedule): punishment, bailable, cognizable, trial court.
  5. Relief      (curated corpus sections, chosen by the user's role and the facts).
  6. Verify      (every cited section must exist in the corpus).

Without a Groq key, layers 1 and 3 use rules, so the feature still works offline.
"""
from __future__ import annotations

import re
import time

from . import llm, predictor
from .corpus import get_corpus
from .detector import reverse
from .search import search

FLAGS = {
    "death": r"\b(died|dies|dead|death|killed|kill(?:ed)? him|kill(?:ed)? her|murder(?:ed)?|deceased|maut|mar gay[ai]|mar diya|jaan chali)\b|मौत|मृत्यु|मर गय|हत्या",
    "injury": r"\b(injur\w*|hurt|wound\w*|bleed\w*|fractur\w*|beat(?:en|ing)?|hit (?:me|him|her|us)|slap\w*|punch\w*|chot|maar\w*|physical(?:ly)? abuse\w*|assault\w*)\b|चोट|मार",
    "serious_injury": r"\b(fractur\w*|grievous|serious(?:ly)? injur\w*|icu|hospitali[sz]ed|stitches|unconscious)\b",
    "property_damage": r"\b(damag\w*|broke|broken|dent\w*|scratch\w*|smash\w*|nuksan|tod\w*|vandal\w*)\b|नुकसान|तोड़",
    "intoxication": r"\b(drunk|alcohol|liquor|intoxicat\w*|sharab\w*|nash[ae]\w*|daru|drink(?:ing)? and driv\w*)\b|शराब|नशे",
    "vehicle": r"\b(car|scoot(?:y|er)|bike|motor ?cycle|truck|bus|auto|vehicle|gaadi|gadi|driving|drove|riding)\b|गाड़ी|गाडी",
    "weapon": r"\b(knife|gun|pistol|rod|lathi|chaku|sword|acid|weapon|firearm)\b|चाकू|हथियार",
    "sexual": r"\b(rape\w*|molest\w*|sexual\w*|modesty|touched (?:me|her) (?:wrongly|inappropriately)|chhed\w*|chhedchhad|harass\w* sexually)\b|छेड़|बलात्कार",
    "dowry": r"\b(dowry|dahej)\b|दहेज",
    "theft": r"\b(stole|stolen|steal\w*|theft|chori|snatch\w*|pickpocket\w*)\b|चोरी",
    "cheating": r"\b(cheat\w*|fraud\w*|scam\w*|dhokh\w*|thag\w*|fake (?:job|letter|receipt))\b|धोखा",
    "threat": r"\b(threat\w*|dhamki|intimidat\w*)\b|धमकी",
    "false_accusation": r"\b(false(?:ly)?|fake (?:claim|case|complaint)|jhoot\w*|jhooth\w*|lie|lying|lied|fabricat\w*|wrongly accus\w*)\b|झूठ",
    "intent_to_kill": r"\b(tried to kill|intention to kill|wanted to kill|maar dalung\w*|jaan se maar\w*)\b|जान से मार",
}
ACCUSED_CUES = r"\b(against (?:me|us)|sue[sd]? (?:me|us)|accus\w* (?:me|us)|blam\w* (?:me|us)|(?:i|we) (?:hit|damaged|broke|was drunk|were drunk)|complaint against (?:me|us)|fir against (?:me|us)|my fault|mere khilaf|humare khilaf|hum par|mujh par)\b|मेरे खिलाफ|मुझ पर"
COMPLAINANT_CUES = (r"\b((?:he|she|they|someone|somebody) (?:hit|beat|stole|cheated|threatened|attacked|harassed) "
                    r"(?:me|us|my)|stole my|cheated me|against (?:him|her|them)|my (?:money|phone|bike|car) was|"
                    r"mujhe (?:maar|pareshan|dhamki|dhokha)\w*|mujhse \w+|mera \w+ chori|mere saath|humein (?:maar|dhamki)\w*)\b"
                    r"|मुझे (?:मार|परेशान|धमकी)|मेरा .{0,20}चोरी|मेरे साथ")

# Sections that cannot apply unless a fact is present (checked on the IPC label or its BNS successor).
REQUIRES = {
    "death": {"IPC": {"299", "300", "302", "303", "304", "304A", "304B", "306", "396"},
              "BNS": {"100", "101", "103", "104", "105", "106", "80", "108"}},
    "intent_to_kill_or_weapon": {"IPC": {"307"}, "BNS": {"109"}},
    "dowry": {"IPC": {"304B", "498A"}, "BNS": {"80", "85", "86"}},
}
# Fact rules: well-known sections suggested directly by the facts (a third candidate source next to the
# model and search). Each: (condition on flags, section, verdict when used offline, reason).
FACT_SEEDS = [
    (lambda f: f["vehicle"] and (f["intoxication"] or f["property_damage"] or f["injury"]), "BNS-281", "applies",
     "Riding or driving rashly or negligently on a public way."),
    (lambda f: f["vehicle"] and f["intoxication"], "BNS-125", "needs_info",
     "A rash act endangering others' safety; depends on how dangerous the riding was."),
    (lambda f: f["property_damage"], "BNS-324", "applies", "Causing damage to someone else's property (mischief)."),
    (lambda f: f["injury"], "BNS-115", "needs_info", "Voluntarily causing hurt; depends on whether anyone was hurt."),
    (lambda f: f["vehicle"] and f["injury"] and not f["death"], "BNS-125", "needs_info",
     "Causing hurt by a rash or negligent act; depends on the injuries."),
    (lambda f: f["sexual"], "BNS-74", "needs_info", "Assault on a woman with intent to outrage her modesty."),
    (lambda f: f["threat"], "BNS-351", "needs_info", "Criminal intimidation."),
    (lambda f: f["theft"], "BNS-303", "applies", "Theft."),
    (lambda f: f["cheating"], "BNS-318", "applies", "Cheating."),
    (lambda f: f["dowry"], "BNS-85", "applies", "Cruelty by the husband or his relatives, including for dowry."),
    (lambda f: f["death"] and f["vehicle"], "BNS-106", "needs_info", "Causing death by negligence."),
]
DISPUTED_REASON = "Alleged by the other side and disputed by you; it depends on the evidence."

RULE_REASON = {
    "death": "No death is described, and this offence requires a death.",
    "intent_to_kill_or_weapon": "Nothing suggests an intention to kill or a deadly weapon.",
    "dowry": "No dowry demand or marriage cruelty is described.",
}

RELIEF = {
    "accused": [
        ("BNSS-482", "Anticipatory bail", "If you fear arrest, you can ask the Sessions Court or High Court in advance for bail."),
        ("BNSS-35", "Arrest only when needed", "For offences punishable with up to 7 years, police must justify an arrest and may instead give you a notice to appear (Section 35(3))."),
        ("BNSS-47", "Your rights on arrest", "Police must tell you the grounds of arrest and, for a bailable offence, that you can be released on bail."),
        ("BNSS-480", "Bail in non-bailable offences", "Even for a non-bailable offence, a court may grant bail."),
        ("BNSS-359", "Settlement (compounding)", "Some offences, such as mischief and simple hurt, can be settled with the other side, and the case then ends."),
    ],
    "false_accusation": [
        ("BNS-248", "Action for a false criminal charge", "Making a false criminal charge to injure someone is itself an offence."),
        ("BNS-217", "False information to police", "Giving false information to a public servant to make them act against you is an offence."),
        ("BNS-356", "Defamation", "False statements that harm your reputation can be challenged."),
        ("BNSS-528", "Quashing a false FIR", "The High Court can quash proceedings that are an abuse of the legal process."),
    ],
    "complainant": [
        ("BNSS-173", "Register an FIR", "The police must register an FIR for a cognizable offence. You can file a Zero FIR at any police station, or an e-FIR."),
        ("BNSS-175", "If police do not investigate", "A Magistrate can order the police to investigate a cognizable case."),
    ],
}

GENERIC_STEPS = {
    "vehicle": "Keep the vehicle papers, insurance, licence and photographs of both vehicles and the spot.",
    "property_damage": "Get a written repair estimate; paying or insuring the damage can help settle the matter.",
    "injury": "Keep medical records. If someone claims injury, ask whether a medical (MLC) report exists.",
    "false_accusation": "Collect evidence that contradicts the false claim: CCTV footage, witnesses, call logs, photographs.",
    "intoxication": "Drunk driving is also an offence under the Motor Vehicles Act (Section 185), outside this app's data.",
}


# --------------------------------------------------------------------------- layer 1: understand
def offline_facts(text: str) -> dict:
    low = text.lower()
    flags = {k: bool(re.search(p, low)) for k, p in FLAGS.items()}
    accused = bool(re.search(ACCUSED_CUES, low))
    complainant = bool(re.search(COMPLAINANT_CUES, low))
    role = "accused" if accused and not complainant else "complainant" if complainant and not accused else (
        "accused" if accused else "unclear")
    if flags["false_accusation"] and role == "unclear":
        role = "accused"
    return {"summary": text.strip()[:600], "formal_facts": "", "user_role": role, "flags": flags,
            "allegations_against_user": [], "allegations_by_user": [], "missing_info": [], "source": "rules"}


UNDERSTAND_PROMPT = """You analyse incidents for an Indian legal-information app. Read the user's description
(it may be in English, Hindi or Hinglish) and return a JSON object with exactly these keys:
- "summary": 2-4 neutral sentences in English describing what happened.
- "formal_facts": the facts rewritten in the third person in the formal style of an Indian court judgment
  (e.g. "The accused, while riding a scooter in an intoxicated state, collided with ..."). Facts only, no law.
- "user_role": "accused" if the user is the one facing a complaint or allegation, "complainant" if the user
  was wronged, "witness", or "unclear".
- "flags": object with true/false for: death, injury, serious_injury, property_damage, intoxication, vehicle,
  weapon, sexual, dowry, theft, cheating, threat, false_accusation, intent_to_kill. Mark something true only
  if the description states or clearly alleges it.
- "allegations_against_user": list of short strings (what the other side claims the user did).
- "allegations_by_user": list of short strings (what the user says the other side did).
- "missing_info": up to 4 short questions whose answers would change the legal analysis.
Do not mention any section numbers."""


def understand(text: str) -> dict:
    base = offline_facts(text)
    if not llm.available():
        return base
    try:
        data = llm.chat_json([{"role": "system", "content": UNDERSTAND_PROMPT},
                              {"role": "user", "content": text[:6000]}], max_tokens=1200)
    except llm.LLMError as e:
        base["llm_error"] = str(e)
        return base
    flags = {k: bool((data.get("flags") or {}).get(k, base["flags"][k])) for k in FLAGS}
    role = data.get("user_role") if data.get("user_role") in ("accused", "complainant", "witness", "unclear") \
        else base["user_role"]
    return {
        "summary": str(data.get("summary") or base["summary"])[:1500],
        "formal_facts": str(data.get("formal_facts") or "")[:3000],
        "user_role": role,
        "flags": flags,
        "allegations_against_user": [str(x)[:200] for x in (data.get("allegations_against_user") or [])][:6],
        "allegations_by_user": [str(x)[:200] for x in (data.get("allegations_by_user") or [])][:6],
        "missing_info": [str(x)[:200] for x in (data.get("missing_info") or [])][:4],
        "source": "groq",
    }


# --------------------------------------------------------------------------- layer 2: candidates
def candidates(text: str, facts: dict, k_model: int = 10, k_search: int = 6) -> list[dict]:
    corpus = get_corpus()
    pool: dict[str, dict] = {}

    def add(bns_id: str, **source):
        sec = corpus.by_id.get(bns_id)
        if not sec:
            return
        c = pool.setdefault(bns_id, {"id": bns_id, "act": sec["act"], "number": sec["number"],
                                     "heading": sec["heading"], "sources": {}, "ipc": []})
        for key, value in source.items():
            if key == "ipc":
                if value and value not in c["ipc"]:
                    c["ipc"].append(value)
            elif key == "model":
                c["sources"]["model"] = max(value, c["sources"].get("model", 0.0))
            else:
                c["sources"].setdefault(key, value)

    # The model reads both the user's words and the formal rewrite; the higher probability wins.
    model_inputs = [t for t in (text, facts.get("formal_facts")) if t]
    if predictor.status()["available"]:
        for t in model_inputs:
            for p in predictor.predict(t, k=k_model)["predictions"]:
                for b in p["bns"]:
                    add(b["id"], model=p["probability"], ipc=p["ipc"], model_above_threshold=p["above_threshold"])
    query = " ".join([facts.get("summary") or text] + allegations(facts))
    for rank, r in enumerate(search(query, method="hybrid", k=k_search, acts=["BNS"])["results"], 1):
        add(r["id"], search_rank=rank)
    flags = facts["flags"]
    for condition, sid, verdict, reason in FACT_SEEDS:
        if condition(flags):
            add(sid, fact_rule=True)
            c = pool.get(sid)
            if c is not None:
                c.setdefault("seed", {"verdict": verdict, "reason": reason})
    for c in pool.values():
        if not c["ipc"]:
            c["ipc"] = [f"{p['act']} {p['number']}" for p in reverse(c["act"], c["number"])][:3]
    return sorted(pool.values(), key=lambda c: (-c["sources"].get("model", 0), c["sources"].get("search_rank", 99)))


def allegations(facts: dict) -> list[str]:
    return list(facts.get("allegations_against_user") or []) + list(facts.get("allegations_by_user") or [])


# --------------------------------------------------------------------------- layer 3: check
def rule_check(c: dict, flags: dict) -> tuple[str, str] | None:
    ipc_numbers = {i.split()[-1] for i in c["ipc"] if i.startswith("IPC")}
    for need, sets in REQUIRES.items():
        if c["number"] in sets["BNS"] or ipc_numbers & sets["IPC"]:
            present = flags.get("intent_to_kill") or flags.get("weapon") if need == "intent_to_kill_or_weapon" \
                else flags.get(need)
            if not present:
                return "unlikely", RULE_REASON[need]
    return None


JUDGE_PROMPT = """You check which Indian criminal law sections may apply to an incident. You are given the
facts and a numbered list of CANDIDATE sections from the Bharatiya Nyaya Sanhita (BNS), each with its heading
and punishment. Judge EVERY candidate. Return a JSON object:
{"assessments": [{"id": "BNS-281", "verdict": "applies" | "unlikely" | "needs_info",
                  "against": "user" | "other_party" | "either", "reason": "one short sentence"}],
 "additional": [{"id": "BNS-115", "reason": "..."}],
 "outside_corpus": [{"law": "Motor Vehicles Act, 1988", "section": "185", "reason": "..."}]}
Rules: "applies" only if the stated facts or allegations fit the section's ingredients. Use "needs_info" when it
depends on facts not given. "against" says who would face the charge. "additional" may list at most 3 more BNS
sections that clearly apply and are missing; use the form "BNS-<number>". "outside_corpus" may list laws other
than BNS, BNSS and BSA (for example the Motor Vehicles Act). Do not invent facts."""


def judge(facts: dict, cands: list[dict]) -> dict:
    corpus = get_corpus()
    lines = []
    for i, c in enumerate(cands, 1):
        cls = corpus.classification_for(c["id"])
        pun = cls[0]["punishment"] if cls else ""
        lines.append(f"({i}) {c['id']}: {c['heading']}. Punishment: {pun}")
    flag_text = ", ".join(k for k, v in facts["flags"].items() if v) or "none"
    user = (f"User's role: {facts['user_role']}\nSummary: {facts['summary']}\n"
            f"Allegations against the user: {facts.get('allegations_against_user') or 'none'}\n"
            f"Allegations by the user: {facts.get('allegations_by_user') or 'none'}\n"
            f"Facts present: {flag_text}\n\nCANDIDATES:\n" + "\n".join(lines))
    return llm.chat_json([{"role": "system", "content": JUDGE_PROMPT}, {"role": "user", "content": user}],
                         max_tokens=2000)


def assess(facts: dict, cands: list[dict]) -> tuple[list[dict], list[dict], str, str | None]:
    """Returns (assessed candidates, outside-corpus laws, judge source, error)."""
    corpus = get_corpus()
    flags = facts["flags"]
    for c in cands:
        ruled = rule_check(c, flags)
        if ruled:
            c.update(verdict=ruled[0], reason=ruled[1], decided_by="rule", against="either")
    outside: list[dict] = []
    open_cands = [c for c in cands if "verdict" not in c]
    source, error = "rules", None
    if llm.available() and open_cands:
        try:
            out = judge(facts, open_cands)
            by_id = {c["id"]: c for c in open_cands}
            for a in out.get("assessments") or []:
                c = by_id.get(str(a.get("id", "")).strip())
                if c and a.get("verdict") in ("applies", "unlikely", "needs_info"):
                    c.update(verdict=a["verdict"], reason=str(a.get("reason", ""))[:300], decided_by="groq",
                             against=a.get("against") if a.get("against") in ("user", "other_party", "either")
                             else "either")
            for a in (out.get("additional") or [])[:3]:
                sid = str(a.get("id", "")).strip().upper().replace(" ", "-")
                sid = sid if sid.startswith("BNS-") else f"BNS-{sid.split('-')[-1]}"
                sec = corpus.by_id.get(sid)
                if sec and sid not in {c["id"] for c in cands}:  # only real sections from the corpus
                    cands.append({"id": sid, "act": "BNS", "number": sec["number"], "heading": sec["heading"],
                                  "sources": {"groq_added": True},
                                  "ipc": [f"{p['act']} {p['number']}" for p in reverse("BNS", sec["number"])][:3],
                                  "verdict": "applies", "reason": str(a.get("reason", ""))[:300],
                                  "decided_by": "groq", "against": "either"})
            outside = [{"law": str(o.get("law", ""))[:80], "section": str(o.get("section", ""))[:20],
                        "reason": str(o.get("reason", ""))[:200]}
                       for o in (out.get("outside_corpus") or [])[:4] if o.get("law")]
            source = "groq"
        except llm.LLMError as e:
            error = str(e)
    disputed = flags.get("false_accusation") and facts["user_role"] == "accused"
    for c in cands:  # anything still undecided: offline rules
        if "verdict" in c:
            continue
        seed = c.get("seed")
        votes = sum([bool(c["sources"].get("model_above_threshold")), "search_rank" in c["sources"] and
                     c["sources"]["search_rank"] <= 3, bool(seed)])
        if seed:
            verdict, reason = seed["verdict"], seed["reason"]
            if disputed and c["number"] in ("115", "74"):
                verdict, reason = "needs_info", DISPUTED_REASON
        elif votes >= 2 or c["sources"].get("model_above_threshold"):
            verdict, reason = "applies", "The trained model and the search engine both point to it."
        else:
            verdict, reason = "needs_info", "Possible; depends on facts that are not clear from the description."
            # Found only by keyword search: shown separately as a weaker possibility.
            c["weak"] = set(c["sources"]) <= {"search_rank"}
        c.update(verdict=verdict, reason=reason, decided_by="rule", against="either")
    if not outside and flags.get("vehicle") and flags.get("intoxication"):
        outside.append({"law": "Motor Vehicles Act, 1988", "section": "185",
                        "reason": "Driving or riding under the influence of alcohol."})
    return cands, outside, source, error


# --------------------------------------------------------------------------- layers 4-6
def attach_facts(cands: list[dict]) -> None:
    corpus = get_corpus()
    for c in cands:
        cls = corpus.classification_for(c["id"])
        c["classification"] = cls[0] if cls else None


def relief(facts: dict) -> list[dict]:
    corpus = get_corpus()
    role, flags = facts["user_role"], facts["flags"]
    keys = []
    if role in ("accused", "unclear"):
        keys += RELIEF["accused"]
    if flags.get("false_accusation") and role != "complainant":
        keys += RELIEF["false_accusation"]
    if role in ("complainant", "unclear", "witness"):
        keys += RELIEF["complainant"]
    out = []
    for sid, title, text in keys:
        sec = corpus.by_id.get(sid)
        if sec:
            out.append({"id": sid, "act": sec["act"], "number": sec["number"], "heading": sec["heading"],
                        "title": title, "explanation": text})
    return out


def next_steps(facts: dict) -> list[str]:
    steps = [GENERIC_STEPS[k] for k in ("vehicle", "property_damage", "injury", "false_accusation", "intoxication")
             if facts["flags"].get(k)]
    steps.append("Write down the date, time, place and names of everyone involved while you remember them.")
    steps.append("Speak to a lawyer before giving a written statement; free legal aid is available through the "
                 "District Legal Services Authority (call 15100).")
    return steps[:6]


def severity(applies: list[dict]) -> dict:
    cls = [c["classification"] for c in applies if c.get("classification")]
    return {
        "charges": len(applies),
        "any_non_bailable": any(x["bailable"].lower().startswith("non") for x in cls),
        "any_cognizable": any(x["cognizable"].lower().startswith("cognizable") for x in cls),
        "courts": sorted({x["triable_by"].rstrip(".") for x in cls}),
    }


ADVICE_PROMPT = """Write a short, calm explanation (120-180 words) for the person who described this incident.
Use only the sections listed below and cite each as [BNS 281] or [BNSS 482]. Explain: what they may be charged
with (or can complain about), how serious it is, and what protects them. Plain English, short paragraphs,
no headings. End with: "This is legal information, not legal advice." """


def advice(facts: dict, applies: list[dict], reliefs: list[dict]) -> str | None:
    if not llm.available():
        return None
    allowed = "\n".join(f"[{c['act']} {c['number']}] {c['heading']} (against: {c.get('against')}; "
                        f"{(c.get('classification') or {}).get('punishment', '')})" for c in applies)
    allowed += "\n" + "\n".join(f"[{r['act']} {r['number']}] {r['title']}: {r['explanation']}" for r in reliefs)
    try:
        return llm.chat([{"role": "system", "content": ADVICE_PROMPT},
                         {"role": "user", "content": f"Role: {facts['user_role']}\nSummary: {facts['summary']}\n\n"
                                                     f"Sections:\n{allowed}"}], max_tokens=700)
    except llm.LLMError:
        return None


def analyze(text: str, role: str | None = None) -> dict:
    from .rag import verify_citations

    t0 = time.perf_counter()
    timings = {}
    facts = understand(text)
    if role in ("accused", "complainant"):
        facts["user_role"] = role
    timings["understand_ms"] = round((time.perf_counter() - t0) * 1000)

    t1 = time.perf_counter()
    cands = candidates(text, facts)
    model_count = sum(1 for c in cands if "model" in c["sources"])
    timings["candidates_ms"] = round((time.perf_counter() - t1) * 1000)

    t2 = time.perf_counter()
    cands, outside, judge_source, judge_error = assess(facts, cands)
    attach_facts(cands)
    timings["check_ms"] = round((time.perf_counter() - t2) * 1000)

    applies = [c for c in cands if c["verdict"] == "applies"]
    reliefs = relief(facts)
    t3 = time.perf_counter()
    text_advice = advice(facts, applies, reliefs)
    timings["advice_ms"] = round((time.perf_counter() - t3) * 1000)
    allowed_ids = [c["id"] for c in applies] + [r["id"] for r in reliefs]
    order = {"applies": 0, "needs_info": 1, "unlikely": 2}
    cands.sort(key=lambda c: (order[c["verdict"]], -c["sources"].get("model", 0)))
    return {
        "facts": facts,
        "candidates": cands,
        "severity": severity(applies),
        "relief": reliefs,
        "next_steps": next_steps(facts),
        "outside_corpus": outside,
        "advice": text_advice,
        "advice_verification": verify_citations(text_advice, allowed_ids) if text_advice else None,
        "pipeline": {
            "understand": facts["source"],
            "model_available": predictor.status()["available"],
            "model_candidates": model_count,
            "search_candidates": sum(1 for c in cands if "search_rank" in c["sources"]),
            "ruled_out_by_rules": sum(1 for c in cands if c.get("decided_by") == "rule" and c["verdict"] == "unlikely"),
            "judge": judge_source,
            "judge_error": judge_error,
            "timings": timings,
        },
        "latency_ms": round((time.perf_counter() - t0) * 1000),
    }
