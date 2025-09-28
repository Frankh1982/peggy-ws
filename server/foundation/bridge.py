import os, json, re
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
from datetime import datetime, timezone

from .patch_guard import apply_with_evidence, PatchError
from .prompt_patch import assemble_patch_prompt
from .checkers.wordle_checkers import measure_wordle
from .signatures import build_ssig, build_esig

# Use OpenAI directly for the foundation (non-stream)
try:
    from openai import AsyncOpenAI
except Exception:
    AsyncOpenAI = None

ROOT = Path(__file__).resolve().parents[1]  # .../server
SB_PATH = ROOT / "foundation" / "statebook.json"

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_write_under_foundation(rel_path: str, text: str) -> bool:
    """
    Only allow creating/updating small text files under server/foundation/*.
    Limits:
      - path must resolve inside ROOT / "foundation"
      - size <= 64 KB
    """
    try:
        root = ROOT / "foundation"
        target = (root / rel_path).resolve()
        if root not in target.parents and target != root:
            return False
        if len(text.encode("utf-8")) > 64*1024:
            return False
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return True
    except Exception:
        return False


def load_statebook() -> Dict:
    if SB_PATH.exists():
        try:
            return json.loads(SB_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    # default minimal structure
    return {"kernel": {"policy": {"allowed_paths": ["/state/*"], "thresholds": {"grs": 0.8}}},
            "project": {"id": "", "goal":"", "deliverable":"", "success_checks":[]},
            "state": {"svec": {}, "grs": {"score": 0.0}, "next_action": "", "open_questions": [], "unknowns": []},
            "principles": {"invariants": []},
            "connections": {"motifs": []}}

def save_statebook(sb: Dict) -> None:
    SB_PATH.parent.mkdir(parents=True, exist_ok=True)
    sb.setdefault("meta", {})["updated"] = _now()
    SB_PATH.write_text(json.dumps(sb, ensure_ascii=False, indent=2), encoding="utf-8")

def detect_project(user_text: str, assistant_reply: str, sb: Dict) -> str:
    t = f"{user_text}\n{assistant_reply}".lower()
    if "wordle" in t:
        sb["project"]["id"] = "wordle"
        sb["project"]["goal"] = "Solve today's Wordle in ≤ 4 guesses."
        sb["project"]["deliverable"] = "Legal 5-letter guesses until solved."
        sb["project"]["success_checks"] = ["valid_word","respects_constraints","novel_guess"]
        sb["state"].setdefault("constraints", {
            "greens":["","","","",""],
            "yellows_not_here":[[],[],[],[],[]],
            "must_include":[],
            "must_exclude":[],
            "min_counts":{}
        })
        return "wordle"
    return sb.get("project",{}).get("id","")

def measure(sb: Dict) -> Dict[str, float]:
    pid = sb.get("project",{}).get("id","")
    if pid == "wordle":
        return measure_wordle(sb)
    # default readiness passthrough
    return {"grs": float(sb.get("state",{}).get("grs",{}).get("score",0.0))}

async def propose_and_apply_patch(user_text: str, assistant_reply: str) -> Dict[str, Any]:
    """
    Called once per WS turn (after streaming). Non-blocking for the main stream.
    - loads statebook
    - detects project
    - asks LLM for a JSON patch (if OPENAI_API_KEY set), else skips
    - verifies via patch_guard
    - saves statebook
    Returns a small dict with diagnostic info.
    """
    sb = load_statebook()
    project_id = detect_project(user_text, assistant_reply, sb)

    sys, messages = assemble_patch_prompt(sb, project_id, last_user=user_text, last_assistant=assistant_reply)

    applied = False; error = None; notes = []; raw = None

    # If no API key present or library missing, skip proposing patches (foundation stays passive)
    api_key = os.getenv("OPENAI_API_KEY","").strip()
    if not api_key or AsyncOpenAI is None:
        save_statebook(sb)
        return {"applied": applied, "error": "no_api_or_lib", "notes": notes, "raw": raw}

    try:
        client = AsyncOpenAI(api_key=api_key)
        resp = await client.chat.completions.create(model=os.getenv("OPENAI_MODEL","gpt-4o-mini"),
                                                    messages=messages, temperature=0.1, max_tokens=300)
        raw = (resp.choices[0].message.content or "").strip()
        obj = json.loads(raw)
        patch = obj.get("patch", [])
        evidence = obj.get("evidence", {})
        # guard
        policy = sb.get("kernel",{}).get("policy",{})
        sb_new, notes = apply_with_evidence(sb, {"patch": patch, "evidence": evidence}, policy, measure)
        applied = True
        sb = sb_new
    except Exception as e:
        error = f"{type(e).__name__}: {e}"

    # optional file writes (esoteric modules, notes); allowed only under server/foundation/*
    try:
        if isinstance(obj, dict) and isinstance(obj.get("files"), list):
            for ft in obj["files"]:
                p = (ft.get("path") or "").strip()
                t = (ft.get("text") or "")
                if p and _safe_write_under_foundation(p, t):
                    notes.append(f"file_written:{p}")
                else:
                    notes.append(f"file_write_rejected:{p}")
    except Exception as _fw:
        error = (error or "") + f" | file_write:{type(_fw).__name__}:{_fw}"
    save_statebook(sb)
    return {"applied": applied, "error": error, "notes": notes, "raw": raw, "project_id": project_id}
