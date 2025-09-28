# POLICY_V2 — warm-start + epsilon decay (fixed exploit line)
import json, random
from pathlib import Path
from typing import Dict

ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = ROOT / "policy.json"

PRINCIPLES = [
    {"id": "BASELINE", "system_addon": ""},
    {"id": "STRUCTURE_BULLETS",
     "system_addon": "When appropriate, structure the answer with short headings and bullet points, and include a brief numbered step list if the user asked how to do something."},
    {"id": "ASK_CLARIFYING",
     "system_addon": "If the user's request is ambiguous or missing a key parameter, ask exactly one concise clarifying question before answering."},
]

# compatible with old files that had "epsilon"; we now use "epsilon_base"
DEFAULT_STATE = {
    "epsilon_base": 0.25,   # starting exploration rate
    "warm_k": 3,            # try each arm once for brand-new buckets
    "buckets": {}
}

def _load_state() -> Dict:
    if POLICY_PATH.exists():
        try:
            st = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
            # migrate old key
            if "epsilon" in st and "epsilon_base" not in st:
                st["epsilon_base"] = float(st.get("epsilon", 0.25))
                st.pop("epsilon", None)
            st.setdefault("buckets", {})
            st.setdefault("warm_k", DEFAULT_STATE["warm_k"])
            st.setdefault("epsilon_base", DEFAULT_STATE["epsilon_base"])
            return st
        except Exception:
            pass
    return json.loads(json.dumps(DEFAULT_STATE))  # deep copy

def _save_state(state: Dict) -> None:
    POLICY_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

STATE = _load_state()

def _bucket_state(bucket: str):
    arms = {p["id"]: {"n": 0, "avg": 0.0} for p in PRINCIPLES}
    b = STATE["buckets"].setdefault(bucket, {"arms": arms, "rr": 0, "n_total": 0})
    # Ensure keys exist even if PRINCIPLES changed
    for p in PRINCIPLES:
        b["arms"].setdefault(p["id"], {"n": 0, "avg": 0.0})
    if "rr" not in b:
        b["rr"] = 0
    if "n_total" not in b:
        b["n_total"] = sum(v["n"] for v in b["arms"].values())
    return b

def _epsilon_for(n_total: int) -> float:
    """
    Decay epsilon after the first 10 feedback events in a bucket.
    Floor at 0.05. Decays 20% every additional 10 events.
    """
    base = float(STATE.get("epsilon_base", 0.25))
    if n_total <= 10:
        return base
    steps = max(0, (n_total - 10) // 10)
    eps = base * (0.8 ** steps)
    return max(0.05, round(eps, 3))

def choose(bucket: str) -> str:
    b = _bucket_state(bucket)
    n_total = b["n_total"]

    # Warm-start: try each arm once for brand-new buckets
    warm_k = int(STATE.get("warm_k", 3))
    if n_total < warm_k:
        idx = b["rr"] % len(PRINCIPLES)
        b["rr"] = (b["rr"] + 1) % len(PRINCIPLES)
        _save_state(STATE)
        return PRINCIPLES[idx]["id"]

    # Epsilon-greedy with decaying epsilon
    eps = _epsilon_for(n_total)
    arms = b["arms"]
    if random.random() < eps:
        return random.choice(list(arms.keys()))

    # Exploit best average reward so far (FIXED: use [0], not (0))
    if not arms:
        return "BASELINE"
    best = max(arms.items(), key=lambda kv: kv[1]["avg"])[0]
    return best

def update(bucket: str, principle_id: str, reward: float) -> None:
    b = _bucket_state(bucket)
    arm = b["arms"][principle_id]
    n, avg = arm["n"], arm["avg"]
    n2 = n + 1
    avg2 = avg + (reward - avg) / n2
    arm["n"], arm["avg"] = n2, float(avg2)
    b["n_total"] = sum(v["n"] for v in b["arms"].values())
    _save_state(STATE)

def addon_for(principle_id: str) -> str:
    for p in PRINCIPLES:
        if p["id"] == principle_id:
            return p["system_addon"]
    return ""
