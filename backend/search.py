"""Retrieval engines over the legal corpus.

Three methods are implemented so they can be compared on the Evaluation page:
  * keyword  - TF-IDF cosine similarity (baseline)
  * bm25     - Okapi BM25 (k1=1.5, b=0.75), heading tokens weighted x3
  * hybrid   - BM25 + Hindi/Hinglish legal vocabulary expansion + explicit section-reference
               resolution + old-code -> new-code mapping boost (NyayaSetu's method)
"""
from __future__ import annotations

import math
import re
import time
from collections import Counter, defaultdict
from functools import lru_cache

from .corpus import OLD_TO_NEW, get_corpus
from .detector import detect_references

TOKEN = re.compile(r"[a-z0-9]+")
STOP = set(
    "the of and or to in a an by for on with as at be is any which that this from such other under who whose "
    "shall may where when his her it its not person persons etc what how does do can if are was were will i me my "
    "someone somebody there their them they he she you your about into than then also been being has have had "
    "section sections act law punishment punished".split()
)

# Hindi (Devanagari) and Hinglish words mapped to English legal vocabulary.
VOCAB = {
    # Devanagari
    "चोरी": "theft", "हत्या": "murder", "कत्ल": "murder", "धोखाधड़ी": "cheating", "धोखा": "cheating",
    "ठगी": "cheating", "दहेज": "dowry", "जमानत": "bail", "गिरफ्तारी": "arrest", "बलात्कार": "rape",
    "अपहरण": "kidnapping", "मानहानि": "defamation", "मारपीट": "hurt", "चोट": "hurt", "धमकी": "intimidation",
    "पत्नी": "wife", "पति": "husband", "क्रूरता": "cruelty", "शिकायत": "complaint", "पुलिस": "police",
    "सबूत": "evidence", "गवाह": "witness", "आत्महत्या": "suicide", "डकैती": "dacoity", "लूट": "robbery",
    "जालसाजी": "forgery", "रिश्वत": "bribe gratification", "छेड़छाड़": "modesty woman assault",
    "पीछा": "stalking", "बच्चा": "child", "महिला": "woman", "संपत्ति": "property", "न्यायालय": "court",
    "अदालत": "court", "इलेक्ट्रॉनिक": "electronic", "रिकॉर्ड": "record", "आतंकवाद": "terrorist",
    "संगठित": "organised", "अपराध": "offence crime", "भीड़": "group", "झपटमारी": "snatching",
    "विवाह": "marriage", "शादी": "marriage", "नकली": "counterfeit", "गुमशुदा": "missing",
    "एफआईआर": "information cognizable", "प्राथमिकी": "information cognizable", "हिरासत": "custody",
    "तलाशी": "search", "समन": "summons", "वारंट": "warrant", "दुर्घटना": "negligence death",
    # Hinglish (romanised)
    "chori": "theft", "hatya": "murder", "qatl": "murder", "katl": "murder", "dhokha": "cheating",
    "dhokhadhadi": "cheating", "thagi": "cheating", "dahej": "dowry", "zamanat": "bail", "jamanat": "bail",
    "giraftari": "arrest", "balatkar": "rape", "apharan": "kidnapping", "maanhani": "defamation",
    "manhani": "defamation", "maarpeet": "hurt", "marpeet": "hurt", "dhamki": "intimidation",
    "patni": "wife", "pati": "husband", "shikayat": "complaint", "saboot": "evidence", "gawah": "witness",
    "aatmahatya": "suicide", "dakaiti": "dacoity", "loot": "robbery", "jaalsaazi": "forgery",
    "rishwat": "bribe gratification", "chhedchhad": "modesty woman assault", "chedchad": "modesty woman assault",
    "jhapatmari": "snatching", "fir": "information cognizable", "hirasat": "custody", "talashi": "search",
    "shaadi": "marriage", "vivah": "marriage", "kroorta": "cruelty", "krurta": "cruelty",
    "pehle": "apprehending", "bike": "movable property",
    # English everyday words -> statutory wording
    "kill": "murder death", "killed": "murder death", "killing": "murder death", "steal": "theft",
    "steals": "theft", "stealing": "theft", "stole": "theft", "stolen": "theft",
    "dying": "statement person who is dead cause of death", "following": "stalking", "follows": "stalking",
    "anticipatory bail": "bail person apprehending arrest direction", "fraud": "cheating dishonestly", "scam": "cheating dishonestly",
    "beat": "hurt", "beating": "hurt", "threat": "intimidation", "threaten": "intimidation",
    "threatening": "intimidation", "kidnap": "kidnapping", "abduct": "abduction", "harass": "cruelty",
    "harassment": "cruelty", "lynching": "group five more persons race caste community",
    "mob": "group five more persons", "bribe": "gratification", "accident": "rash negligent",
    "drunk": "intoxication", "hacking": "electronic", "cctv": "electronic record", "whatsapp": "electronic record",
    "video": "electronic record", "email": "electronic record", "anticipatory": "anticipatory arrest bail",
    "chargesheet": "report police officer completion investigation", "remand": "custody detention",
    "confession": "confession", "stalk": "stalking", "stalking": "stalking", "acid": "acid",
    "snatch": "snatching", "snatching": "snatching", "terror": "terrorist", "terrorism": "terrorist",
    "gang": "organised crime", "extortion": "extortion", "blackmail": "extortion", "rioting": "rioting",
    "riot": "rioting", "trespass": "trespass", "defame": "defamation", "rape": "rape",
}


def tokenize(text: str) -> list[str]:
    return [t for t in TOKEN.findall(text.lower()) if t not in STOP and len(t) > 1]


def stem(tok: str) -> str:
    for suf in ("ings", "ing", "ies", "ied", "es", "ed", "ly", "s"):
        if tok.endswith(suf) and len(tok) - len(suf) >= 4:
            return tok[: -len(suf)]
    return tok


def analyze(text: str) -> list[str]:
    return [stem(t) for t in tokenize(text)]


def expand_query(query: str) -> tuple[str, list[str]]:
    """Adds English legal terms for Hindi/Hinglish/colloquial words. Returns (expanded, added_terms)."""
    added: list[str] = []
    lowered = query.lower()
    for word, legal in VOCAB.items():
        if re.search(r"[a-z]", word):
            hit = re.search(rf"\b{re.escape(word)}\b", lowered)
        else:
            hit = word in query
        if hit:
            added.append(legal)
    return (query + " " + " ".join(added)).strip(), added


class Index:
    def __init__(self, docs: list[dict], heading_weight: int = 3) -> None:
        self.docs = docs
        self.doc_tokens: list[Counter] = []
        for d in docs:
            toks = analyze(d.get("heading", "")) * heading_weight + analyze(d.get("chapter_name", "")) + analyze(d["text"])
            self.doc_tokens.append(Counter(toks))
        self.lengths = [sum(c.values()) for c in self.doc_tokens]
        self.avgdl = sum(self.lengths) / max(1, len(self.lengths))
        self.df: Counter = Counter()
        self.postings: dict[str, list[int]] = defaultdict(list)
        for i, c in enumerate(self.doc_tokens):
            for t in c:
                self.df[t] += 1
                self.postings[t].append(i)
        self.n = len(docs)
        self._norms: list[float] | None = None

    def idf(self, t: str) -> float:
        df = self.df.get(t, 0)
        return math.log(1 + (self.n - df + 0.5) / (df + 0.5))

    def bm25(self, query: str, k1: float = 1.5, b: float = 0.75) -> dict[int, float]:
        scores: dict[int, float] = defaultdict(float)
        for t in set(analyze(query)):
            idf = self.idf(t)
            for i in self.postings.get(t, ()):
                tf = self.doc_tokens[i][t]
                denom = tf + k1 * (1 - b + b * self.lengths[i] / self.avgdl)
                scores[i] += idf * tf * (k1 + 1) / denom
        return scores

    def tfidf(self, query: str) -> dict[int, float]:
        if self._norms is None:
            self._norms = [
                math.sqrt(sum(((1 + math.log(c)) * self.idf(t)) ** 2 for t, c in toks.items())) or 1.0
                for toks in self.doc_tokens
            ]
        q = Counter(analyze(query))
        scores: dict[int, float] = defaultdict(float)
        for t, qc in q.items():
            idf = self.idf(t)
            for i in self.postings.get(t, ()):
                scores[i] += (1 + math.log(self.doc_tokens[i][t])) * idf * (1 + math.log(qc)) * idf
        return {i: s / self._norms[i] for i, s in scores.items()}


@lru_cache(maxsize=1)
def corpus_index() -> Index:
    return Index(get_corpus().sections)


def search(query: str, method: str = "hybrid", k: int = 8, acts: list[str] | None = None,
           prefer_new: bool = True) -> dict:
    """Returns {'results': [...], 'expanded_query', 'added_terms', 'references', 'latency_ms'}."""
    t0 = time.perf_counter()
    corpus = get_corpus()
    idx = corpus_index()
    added: list[str] = []
    refs: list[dict] = []
    q = query

    if method == "keyword":
        scores = idx.tfidf(q)
    elif method == "bm25":
        scores = idx.bm25(q)
    else:
        q, added = expand_query(query)
        scores = idx.bm25(q)
        top = max(scores.values(), default=1.0) or 1.0
        # Explicit references such as "IPC 420" / "section 154 CrPC" / "धारा 302"
        refs = detect_references(query)
        pos = {d["id"]: i for i, d in enumerate(idx.docs)}
        for r in refs:
            if r["section_id"] in pos:
                scores[pos[r["section_id"]]] = scores.get(pos[r["section_id"]], 0) + top * 2.0
            for target in r.get("converted", []):
                if target["id"] in pos:
                    scores[pos[target["id"]]] = scores.get(pos[target["id"]], 0) + top * 2.5
        # Mapping boost: when an old-code section scores well, lift its 2023 successor.
        if prefer_new:
            for i, s in list(sorted(scores.items(), key=lambda x: -x[1])[:15]):
                d = idx.docs[i]
                if d["act"] in OLD_TO_NEW:
                    for m in corpus.new_from_old.get((d["act"], d["number"]), []):
                        j = pos.get(f"{m['new_act']}-{m['new']}")
                        if j is not None:
                            scores[j] = max(scores.get(j, 0), s * 1.05)
                    scores[i] = s * 0.8

    ranked = sorted(scores.items(), key=lambda x: -x[1])
    results = []
    for i, s in ranked:
        d = idx.docs[i]
        if acts and d["act"] not in acts:
            continue
        item = corpus.summary(d)
        item["score"] = round(s, 3)
        results.append(item)
        if len(results) >= k:
            break
    return {
        "query": query,
        "method": method,
        "expanded_query": q,
        "added_terms": added,
        "references": refs,
        "results": results,
        "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
    }


class ChunkIndex:
    """Small BM25 index over chunks of an uploaded document (for 'Ask this document')."""

    def __init__(self, chunks: list[dict]) -> None:
        self.index = Index([{"heading": "", "chapter_name": "", "text": c["text"]} for c in chunks], 1)
        self.chunks = chunks

    def search(self, query: str, k: int = 4) -> list[dict]:
        q, _ = expand_query(query)
        scores = self.index.bm25(q)
        ranked = sorted(scores.items(), key=lambda x: -x[1])[:k]
        return [{**self.chunks[i], "score": round(s, 3)} for i, s in ranked]
