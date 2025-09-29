# server/foundation/autolearn.py
import os, json, re
from pathlib import Path
from typing import Dict, Any
from datetime import datetime, timezone

try:
    from openai import AsyncOpenAI
except Exception:
    AsyncOpenAI = None

ROOT = Path(__file__).resolve().parents[1]
def _now(): return datetime.now(timezone.utc).isoformat()

def _ensure_dir(path: Path): path.mkdir(parents=True, exist_ok=True)

def _unwrap_json(s: str) -> Dict:
    s = (s or "").strip()
    # tolerate ```json ... ``` or ``` ... ```
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", s, flags=re.S)
    if m:
        s = m.group(1)
    return json.loads(s)

async def run_autolearn(project_id: str, sb: Dict) -> Dict[str, Any]:
    out = {"project": project_id, "applied": False, "files": [], "error": None, "notes": []}

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key or AsyncOpenAI is None:
        out["error"] = "no_api_or_lib"; return out

    client = AsyncOpenAI(api_key=api_key)

    system = (
        "You are Peggy-Learn. Output a compact JSON object of heuristics ONLY.\n"
        'Schema:\n{"weights":{"info_gain":0.8,"heuristics":0.2},'
        '"rules":[{"id":"avoid_duplicates_early","weight":1.0},'
        '{"id":"prefer_common_letters","weight":1.0},'
        '{"id":"prefer_two_vowels_early","weight":0.6}]}\n'
        "No prose, no explanations—JSON only."
    )
    user = f"Project={project_id}. Provide heuristics JSON now."

    try:
        resp = await client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL","gpt-4o-mini"),
            messages=[{"role":"system","content":system},{"role":"user","content":user}],
            temperature=0.1,
            max_tokens=400,
            response_format={"type":"json_object"}  # <-- force JSON
        )
        raw = (resp.choices[0].message.content or "").strip()
        data = _unwrap_json(raw)  # tolerate code fences if any
    except Exception as e:
        out["error"] = f"gen_fail: {type(e).__name__}: {e}"
        return out

    # store under modules/<project>/studies to keep it data-only (no code)
    mod_dir = ROOT / "modules" / project_id / "studies"
    _ensure_dir(mod_dir)
    heuristics_path = mod_dir / "heuristics.json"
    data["meta"] = {"generated": _now(), "model": os.getenv("OPENAI_MODEL","gpt-4o-mini")}
    heuristics_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    out["applied"] = True
    out["files"].append(str(heuristics_path.relative_to(ROOT)))
    out["notes"].append("heuristics.json written; suggester will blend info_gain + heuristics")
    return out
