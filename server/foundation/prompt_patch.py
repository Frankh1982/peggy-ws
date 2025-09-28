import json
from typing import Dict

INSTR = (
  "You are Peggy-Foundation. Reply ONLY with compact JSON: "
  '{"reply":"<short note to user>", "patch":[...], "evidence":{"checker_deltas":{...}}}. '
  "Patch must use RFC-6902 ops (add/replace). "
  "Only edit allowed paths (policy.allowed_paths). "
  "If you lack evidence for risky edits (policy.proof_required), do not propose them. "
  "If you don't know, set reply to \"I don't know yet\" and propose a probe in reply."
)

def assemble_patch_prompt(statebook: Dict, project_id: str, last_user: str = "", last_assistant: str = "") -> tuple[str, list]:
    kernel = statebook.get("kernel", {})
    body = {
        "policy": kernel.get("policy", {}),
        "project": statebook.get("project", {}),
        "state": {
            "svec": statebook.get("state",{}).get("svec",{}),
            "grs": statebook.get("state",{}).get("grs",{}),
            "next_action": statebook.get("state",{}).get("next_action",""),
            "open_questions": statebook.get("state",{}).get("open_questions",[])[:2],
            "unknowns": statebook.get("state",{}).get("unknowns",[])[:2]
        },
        "principles": statebook.get("principles",{}).get("invariants",[])[:4],
        "motifs": statebook.get("connections",{}).get("motifs",[])[:2],
        "module": project_id or ""
    }
    sys = (
      "Follow safety: assertion_policy=require_evidence_or_state_unknown; "
      "do not invent facts; stay within bounded scope. "
      f"Mission: {kernel.get('mission','')}"
    )
    messages = [
        {"role":"system","content": sys},
        {"role":"system","content": "Last user: " + (last_user or "")},
        {"role":"system","content": "Last assistant: " + (last_assistant or "")},
        {"role":"user","content": json.dumps(body, ensure_ascii=False)},
        {"role":"system","content": INSTR}
    ]
    return sys, messages
