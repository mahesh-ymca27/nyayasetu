"""Knowledge graph views of the codes: acts -> chapters -> sections, with old -> new succession edges."""
from __future__ import annotations

from .corpus import NEW_TO_OLD, get_corpus, roman_to_int


def overview() -> dict:
    """Acts and their chapters, with weighted succession edges between old and new acts."""
    corpus = get_corpus()
    nodes, edges = [], []
    for a in corpus.acts:
        nodes.append({"id": a["code"], "label": a["code"], "title": a["name"], "type": "act", "era": a["era"],
                      "size": a["sections"]})
    for new, old in NEW_TO_OLD.items():
        n = sum(1 for m in corpus.mappings if m["new_act"] == new and m["old"])
        edges.append({"source": old, "target": new, "type": "replaced_by", "weight": n, "label": f"{n} mapped"})
    chapters: dict[str, dict] = {}
    for s in corpus.sections:
        if s["act"] not in ("BNS", "BNSS", "BSA") or not s["chapter"]:
            continue
        cid = f"{s['act']}:{s['chapter']}"
        ch = chapters.setdefault(cid, {"id": cid, "label": s["chapter"].replace("CHAPTER ", "Ch "),
                                       "title": s["chapter_name"], "type": "chapter", "act": s["act"], "size": 0})
        ch["size"] += 1
    for ch in sorted(chapters.values(), key=lambda c: (c["act"], roman_to_int(c["label"].replace("Ch ", "")))):
        nodes.append(ch)
        edges.append({"source": ch["act"], "target": ch["id"], "type": "contains", "weight": ch["size"]})
    return {"nodes": nodes, "edges": edges}


def chapter_graph(act: str, chapter: str) -> dict:
    """One chapter of a 2023 code: its sections and the old-code sections they replaced."""
    corpus = get_corpus()
    secs = [s for s in corpus.sections if s["act"] == act and s["chapter"] == chapter]
    if not secs:
        return {"nodes": [], "edges": []}
    cid = f"{act}:{chapter}"
    nodes = [{"id": cid, "label": chapter.replace("CHAPTER ", "Ch "), "title": secs[0]["chapter_name"],
              "type": "chapter", "act": act, "size": len(secs)}]
    edges, seen = [], {cid}
    for s in secs:
        nodes.append({"id": s["id"], "label": f"{act} {s['number']}", "title": s["heading"], "type": "section",
                      "act": act, "era": "new", "size": 1})
        seen.add(s["id"])
        edges.append({"source": cid, "target": s["id"], "type": "contains"})
        m = corpus.old_from_new.get((act, s["number"]))
        if m and not m["old"]:
            nodes[-1]["is_new"] = True
        for o in (m or {}).get("old", []):
            oid = f"{m['old_act']}-{o}"
            if oid not in seen:
                old = corpus.by_id.get(oid)
                nodes.append({"id": oid, "label": f"{m['old_act']} {o}", "title": old["heading"] if old else "",
                              "type": "section", "act": m["old_act"], "era": "old", "size": 1})
                seen.add(oid)
            edges.append({"source": oid, "target": s["id"], "type": "replaced_by",
                          "confidence": m["confidence"], "mapping": m["source"]})
    return {"nodes": nodes, "edges": edges}


def section_graph(section_id: str) -> dict:
    """Ego graph around one section: predecessors, successors and siblings in the same chapter."""
    corpus = get_corpus()
    sec = corpus.by_id.get(section_id)
    if not sec:
        return {"nodes": [], "edges": []}
    nodes = {sec["id"]: {"id": sec["id"], "label": f"{sec['act']} {sec['number']}", "title": sec["heading"],
                         "type": "section", "act": sec["act"], "focus": True, "size": 3}}
    edges = []

    def add(s: dict, rel: str, src: str, dst: str) -> None:
        nodes.setdefault(s["id"], {"id": s["id"], "label": f"{s['act']} {s['number']}", "title": s["heading"],
                                   "type": "section", "act": s["act"], "size": 1})
        edges.append({"source": src, "target": dst, "type": rel})

    m = corpus.old_from_new.get((sec["act"], sec["number"]))
    for o in (m or {}).get("old", []):
        old = corpus.by_id.get(f"{m['old_act']}-{o}")
        if old:
            add(old, "replaced_by", old["id"], sec["id"])
    for m2 in corpus.new_from_old.get((sec["act"], sec["number"]), []):
        new = corpus.by_id.get(f"{m2['new_act']}-{m2['new']}")
        if new:
            add(new, "replaced_by", sec["id"], new["id"])
    siblings = [s for s in corpus.sections if s["act"] == sec["act"] and s["chapter"] == sec["chapter"]]
    i = next((k for k, s in enumerate(siblings) if s["id"] == sec["id"]), 0)
    for s in siblings[max(0, i - 3): i + 4]:
        if s["id"] != sec["id"]:
            add(s, "same_chapter", sec["id"], s["id"])
    return {"nodes": list(nodes.values()), "edges": edges}
