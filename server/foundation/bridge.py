# Minimal foundation bridge: no esoteric imports; optional measure_fn for proof-gated edits
import os, json
from pathlib import Path
from typing import Dict, Any, Optional, Callable
from datetime import datetime, timezone

from .patch_guard import apply_with_evidence, PatchError
from .prompt_patch import assemble_patch_prompt

try:
    from openai import AsyncOpenAI
except Exception:
    AsyncOpenAI = None

ROOT   = Path(__file__).resolve().parents[1]  # .../server
SB_PATH = ROOT / "foundation" / "statebook.json"

def _now() -> str: return datetime.now(timezone.utc).isoformat()

def load_statebook() -> Dict:
    if SB_PATH.exists():
        try: return json.loads(SB_PATH.read_text(encoding="utf-8"))
        except Exception: pass
    return {
        "kernel":{"policy":{"allowed_paths":["/state/*","/temp/*","/connections/*","/gaps/*","/logs/decisions/*"],
                            "thresholds":{"grs":0.80}, "kernel_locked":True}},
        "project":{"id":"","goal":"", "deliverable":"", "success_checks":[]},
        "state":{"svec":{}, "grs":{"score":0.0}, "next_action":"", "open_questions":[], "unknowns":[]},
        "connections":{"motifs":[]}
    }

def save_statebook(sb: Dict) -> None:
    SB_PATH.parent.mkdir(parents=True, exist_ok=True)
    sb.setdefault("meta", {})["updated"] = _now()
    SB_PATH.write_text(json.dumps(sb, ensure_ascii=False, indent=2), encoding="utf-8")

async def propose_and_apply_patch(user_text: str, assistant_reply: str,
                                  measure_fn: Optional[Callable[[Dict], Dict[str,float]]] = None) -> Dict[str, Any]:
    sb = load_statebook()
    project_id = sb.get("project",{}).get("id","")

    # tiny, token-lean prompt
    _, messages = assemble_patch_prompt(sb, project_id, last_user=user_text, last_assistant=assistant_reply)

    applied=False; error=None; notes=[]; raw=None
    api_key = os.getenv("OPENAI_API_KEY","").strip()

    if not api_key or AsyncOpenAI is None:
        save_statebook(sb)
        return {"applied": applied, "error":"no_api_or_lib", "notes":notes, "raw":raw, "project_id":project_id}

    try:
        client = AsyncOpenAI(api_key=api_key)
        resp = await client.chat.completions.create(model=os.getenv("OPENAI_MODEL","gpt-4o-mini"),
                                                    messages=messages, temperature=0.1, max_tokens=300)
        raw = (resp.choices[0].message.content or "").strip()
        obj = json.loads(raw)
        patch = obj.get("patch", [])
        evidence = obj.get("evidence", {})

        policy = sb.get("kernel",{}).get("policy",{})
        meas = (lambda s: measure_fn(s) if measure_fn else {})
        sb_new, notes = apply_with_evidence(sb, {"patch":patch,"evidence":evidence}, policy, meas)
        sb = sb_new; applied=True
    except Exception as e:
        error = f"{type(e).__name__}: {e}"

    save_statebook(sb)
    return {"applied": applied, "error": error, "notes": notes, "raw": raw, "project_id": project_id}
