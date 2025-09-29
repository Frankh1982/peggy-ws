# server/foundation/checkers/wordle_checkers.py
from pathlib import Path
from typing import Dict, List
from collections import Counter
import os

# ---- dictionary discovery (first hit wins) ----
def _candidate_paths() -> List[Path]:
    env = os.getenv("WORDLE_DICT_FILE", "").strip()
    return [
        Path(env).expanduser() if env else None,  # explicit override
        # your current layout (see screenshot):
        Path(__file__).resolve().parents[1] / "modules" / "wordle" / "dictionary.txt",  # server/foundation/modules/wordle/...
        # alternative layout if you later move modules out of foundation:
        Path(__file__).resolve().parents[2] / "modules" / "wordle" / "dictionary.txt",  # server/modules/wordle/...
        # legacy fallback (same folder as this file):
        Path(__file__).resolve().parent / "dictionary.txt",
    ]

_DICT: List[str] = []
_MTIME = None
_PATH: Path | None = None

def _resolve_path() -> Path | None:
    for p in _candidate_paths():
        if p and p.exists() and p.is_file():
            return p
    return None

def load_dictionary(path: str | None = None) -> List[str]:
    """Load lowercased 5-letter words, hot‑reloading on file mtime changes."""
    global _DICT, _MTIME, _PATH
    p = Path(path) if path else _resolve_path()
    if not p:
        _DICT, _MTIME, _PATH = [], None, None
        return []
    mtime = p.stat().st_mtime
    if _MTIME != mtime or not _DICT:
        words = []
        for ln in p.read_text(encoding="utf-8").splitlines():
            w = ln.strip().lower()
            if len(w) == 5 and w.isalpha():
                words.append(w)
        _DICT, _MTIME, _PATH = words, mtime, p
    return list(_DICT)

def get_dict() -> List[str]:
    return load_dictionary()

def dict_len() -> int:
    return len(load_dictionary())

# ---- constraint checking (supports doubles) ----
def respects_constraints(word: str, constraints: Dict) -> bool:
    w = word.lower()
    greens = constraints.get("greens", ["","","","",""])
    ynh = constraints.get("yellows_not_here", [[],[],[],[],[]])
    must_include = set(map(str.lower, constraints.get("must_include", [])))
    must_exclude = set(map(str.lower, constraints.get("must_exclude", [])))
    min_counts = {k.lower(): int(v) for k,v in constraints.get("min_counts", {}).items()}
    max_counts = {k.lower(): int(v) for k,v in constraints.get("max_counts", {}).items()}

    for i,g in enumerate(greens):
        if g and w[i] != g: return False
    for i, bads in enumerate(ynh):
        if w[i] in {b.lower() for b in bads}: return False
    if any(ch in must_exclude for ch in w): return False
    if any(ch not in w for ch in must_include): return False
    for ch, cnt in min_counts.items():
        if w.count(ch) < cnt: return False
    for ch, cnt in max_counts.items():
        if w.count(ch) > cnt: return False
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
