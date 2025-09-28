import os, string
from typing import Dict, List
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # .../server/
DICT_PATH = ROOT / "foundation" / "modules" / "wordle" / "dictionary.txt"

def load_dictionary(path: str | None = None) -> List[str]:
    path = path or str(DICT_PATH)
    with open(path, "r", encoding="utf-8") as f:
        return [w.strip().lower() for w in f if w.strip() and len(w.strip())==5]

def valid_word(word: str, dictionary: List[str] | None = None) -> bool:
    dictionary = dictionary or load_dictionary()
    w = (word or "").strip().lower()
    if len(w) != 5: return False
    if any(ch not in string.ascii_letters for ch in w): return False
    return w in dictionary

def respects_constraints(word: str, constraints: Dict) -> bool:
    w = (word or "").lower()
    greens = constraints.get("greens", ["","","","",""])
    yellows_not_here = constraints.get("yellows_not_here", [[],[],[],[],[]])
    must_include = set([c.lower() for c in constraints.get("must_include", [])])
    must_exclude = set([c.lower() for c in constraints.get("must_exclude", [])])
    min_counts = constraints.get("min_counts", {})

    for i,g in enumerate(greens):
        if g and w[i] != g.lower():
            return False
    for i, bads in enumerate(yellows_not_here):
        if w[i] in [b.lower() for b in bads]:
            return False
    for ch in w:
        if ch in must_exclude:
            return False
    for ch in must_include:
        if ch not in w:
            return False
    for ch, cnt in min_counts.items():
        if w.count(ch.lower()) < int(cnt):
            return False
    return True

def filter_candidates(constraints: Dict, dictionary: List[str] | None = None) -> List[str]:
    dictionary = dictionary or load_dictionary()
    return [w for w in dictionary if respects_constraints(w, constraints)]

def info_gain_score(word: str, candidates: List[str]) -> float:
    if not candidates: return 0.0
    pos_counts = [Counter([w[i] for w in candidates]) for i in range(5)]
    used = set(); score = 0.0
    for i,ch in enumerate(word):
        score += pos_counts[i].get(ch, 0) / max(1, len(candidates))
        if ch not in used:
            total = sum(pc.get(ch,0) for pc in pos_counts)
            score += total / max(1, 5*len(candidates))
            used.add(ch)
    return float(score)

def measure_wordle(statebook: Dict) -> Dict[str, float]:
    cons = statebook.get("state", {}).get("constraints", {
        "greens":["","","","",""],
        "yellows_not_here":[[],[],[],[],[]],
        "must_include":[],
        "must_exclude":[],
        "min_counts":{}
    })
    cands = filter_candidates(cons)
    return {"candidate_count": float(len(cands)), "violations": 0.0, "validity": 1.0}
