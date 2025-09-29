# server/modules/wordle/suggest.py
import json
from pathlib import Path
from typing import Dict
from .checkers import get_dict, filter_candidates, info_gain_score

def _load_heuristics() -> Dict:
    p = Path(__file__).resolve().parent / "studies" / "heuristics.json"
    if p.exists():
        try: return json.loads(p.read_text(encoding="utf-8"))
        except Exception: return {}
    return {}

def _letter_freq(cands):
    from collections import Counter
    cnt = Counter("".join(cands)) if cands else Counter()
    total = sum(cnt.values()) or 1
    return {ch: cnt[ch]/total for ch in cnt}

def _heur_score(word: str, cands, heur: Dict, turn_idx: int) -> float:
    rules = heur.get("rules", [])
    freq = _letter_freq(cands)
    vowels = set("aeiou")
    uniq = len(set(word)) == len(word)
    score = 0.0
    for r in rules:
        rid = r.get("id",""); w = float(r.get("weight", 0))
        if rid == "avoid_duplicates_early":
            if turn_idx <= 2 and uniq: score += w
        elif rid == "prefer_common_letters":
            score += sum(freq.get(ch,0) for ch in set(word)) * w
        elif rid == "prefer_two_vowels_early":
            if turn_idx <= 2 and sum(1 for ch in set(word) if ch in vowels) >= 2:
                score += w
        # (extend with new ids safely)
    return score

def suggest(sb: Dict) -> Dict:
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
    turns = len(sb.get("state",{}).get("history", [])) + 1
    dictionary = get_dict()
    cands = filter_candidates(cons, dictionary)
    if not cands:
        return {"guess": None, "candidates": 0, "dict": len(dictionary)}

    heur = _load_heuristics()
    weights = heur.get("weights", {"info_gain":0.8,"heuristics":0.2})
    ig = {w: info_gain_score(w, cands) for w in cands}

    # combine info gain with learned heuristics (bounded, safe)
    scores = []
    for w in cands:
        h = _heur_score(w, cands, heur, turns)
        s = float(weights.get("info_gain",0.8))*ig[w] + float(weights.get("heuristics",0.2))*h
        scores.append((s, w))

    scores.sort(reverse=True)
    best = scores[0][1]
    return {"guess": best, "candidates": len(cands), "dict": len(dictionary), "used":{"weights":weights}}
4