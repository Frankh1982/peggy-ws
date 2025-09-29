import os, string
from typing import Dict, List
from pathlib import Path
from collections import Counter

DICT_PATH = Path(__file__).resolve().parent / "dictionary.txt"
_DICT: List[str] = []
_MTIME = None

def load_dictionary(path: str | None = None) -> List[str]:
    """Reloads on file mtime change; keeps memory small."""
    global _DICT, _MTIME
    p = Path(path) if path else DICT_PATH
    mtime = p.stat().st_mtime if p.exists() else None
    if _MTIME != mtime or not _DICT:
        words = []
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                w = line.strip().lower()
                if len(w)==5 and w.isalpha():
                    words.append(w)
        _DICT = words
        _MTIME = mtime
    return list(_DICT)

def get_dict() -> List[str]:
    return load_dictionary()

def valid_word(word: str, dictionary: List[str] | None = None) -> bool:
    dictionary = dictionary or get_dict()
    w = (word or "").strip().lower()
    return len(w)==5 and w.isalpha() and (w in dictionary)

def respects_constraints(word: str, constraints: Dict) -> bool:
    w = word.lower()
    greens = constraints.get("greens", ["","","","",""])
    yellows_not_here = constraints.get("yellows_not_here", [[],[],[],[],[]])
    must_include = set([c.lower() for c in constraints.get("must_include", [])])
    must_exclude = set([c.lower() for c in constraints.get("must_exclude", [])])
    min_counts = {k.lower(): int(v) for k,v in constraints.get("min_counts", {}).items()}
    max_counts = {k.lower(): int(v) for k,v in constraints.get("max_counts", {}).items()}

    # fixed greens
    for i,g in enumerate(greens):
        if g and w[i] != g:
            return False
    # yellows cannot be at those positions
    for i,bads in enumerate(yellows_not_here):
        if w[i] in {b.lower() for b in bads}:
            return False
    # excludes
    for ch in w:
        if ch in must_exclude:
            return False
    # includes
    for ch in must_include:
        if ch not in w:
            return False
    # min/max counts (doubles)
    for ch, cnt in min_counts.items():
        if w.count(ch) < cnt:
            return False
    for ch, cnt in max_counts.items():
        if w.count(ch) > cnt:
            return False
    return True

def filter_candidates(constraints: Dict, dictionary: List[str] | None = None) -> List[str]:
    dictionary = dictionary or get_dict()
    return [w for w in dictionary if respects_constraints(w, constraints)]

def info_gain_score(word: str, candidates: List[str]) -> float:
    if not candidates: return 0.0
    pos_counts = [Counter([w[i] for w in candidates]) for i in range(5)]
    used = set(); score = 0.0
    for i,ch in enumerate(word):
        score += pos_counts[i].get(ch,0)/max(1,len(candidates))
        if ch not in used:
            total = sum(pc.get(ch,0) for pc in pos_counts)
            score += total/max(1,5*len(candidates))
            used.add(ch)
    return float(score)

def measure_state(sb: Dict) -> Dict[str,float]:
    """For foundation proof checks: size of the candidate set."""
    if sb.get("project",{}).get("id") != "wordle":
        return {}
    cons = sb.get("state",{}).get("constraints", {
        "greens":["","","","",""],
        "yellows_not_here":[[],[],[],[],[]],
        "must_include":[],
        "must_exclude":[],
        "min_counts":{},
        "max_counts":{}
    })
    cands = filter_candidates(cons, get_dict())
    return {"candidate_count": float(len(cands))}
