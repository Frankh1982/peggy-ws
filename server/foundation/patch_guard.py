import copy
from typing import Dict, List, Any, Tuple

class PatchError(Exception):
    pass

def _path_allowed(path: str, allowed_patterns: List[str]) -> bool:
    # minimal matcher: "/state/*" style and exact
    for pat in allowed_patterns:
        if pat.endswith("/*"):
            if path.startswith(pat[:-1]):
                return True
        elif path == pat:
            return True
    return False

def _get(d: Dict, path: str):
    node = d
    if path == "/" or path == "":
        return node
    parts = [p for p in path.split("/") if p]
    for p in parts:
        if isinstance(node, list) and p.isdigit():
            node = node[int(p)]
        else:
            node = node.get(p)
    return node

def _set(d: Dict, path: str, value: Any):
    parts = [p for p in path.split("/") if p]
    node = d
    for i,p in enumerate(parts):
        last = i==len(parts)-1
        if isinstance(node, list) and p.isdigit():
            idx = int(p)
            if last:
                node[idx] = value
            else:
                node = node[idx]
        else:
            if last:
                node[p] = value
            else:
                if p not in node or not isinstance(node[p], (dict, list)):
                    node[p] = {}
                node = node[p]

def _add_to_list(d: Dict, path: str, value: Any):
    parts = [p for p in path.split("/") if p]
    *pre, last = parts
    node = d
    for p in pre:
        if isinstance(node, list) and p.isdigit():
            node = node[int(p)]
        else:
            node = node.setdefault(p, {})
    if isinstance(node, list):
        if last == "-":
            node.append(value)
        else:
            node.insert(int(last), value)
    else:
        # expect list at final path; create if absent
        if last not in node or not isinstance(node[last], list):
            node[last] = []
        node[last].append(value)

def apply_with_evidence(statebook: Dict, proposal: Dict, policy: Dict, measure_fn) -> Tuple[Dict, List[str]]:
    """
    proposal = {"patch":[...], "evidence": {...}}
    - allowed paths: policy['allowed_paths']
    - risky paths: policy['proof_required'] (requires evidence checker deltas)
    - measure_fn(sb) -> Dict[str,float] recomputes metrics
    Returns: (new_statebook, notes)
    """
    notes: List[str] = []
    allowed = policy.get("allowed_paths", [])
    proof_required = policy.get("proof_required", [])

    patch = proposal.get("patch", [])
    evidence = proposal.get("evidence", {})

    sb_new = copy.deepcopy(statebook)

    risky_targets = [r.get("path","") for r in proof_required]

    def requires_proof(path: str) -> bool:
        for rt in risky_targets:
            if rt.endswith("/*"):
                if path.startswith(rt[:-1]):
                    return True
            elif rt.endswith("/-"):
                if path.startswith(rt[:-2]):
                    return True
            elif path == rt:
                return True
        return False

    before = measure_fn(copy.deepcopy(sb_new))

    for op in patch:
        act = op.get("op"); path = op.get("path"); value = op.get("value")
        if not _path_allowed(path, allowed):
            raise PatchError(f"Path not allowed: {path}")
        if requires_proof(path) and not evidence:
            raise PatchError(f"Evidence required for risky edit at {path}")
        if act == "replace":
            _set(sb_new, path, value)
        elif act == "add":
            if path.endswith("/-") or path.split("/")[-1].isdigit():
                _add_to_list(sb_new, path, value)
            else:
                _set(sb_new, path, value)
        else:
            raise PatchError(f"Unsupported op: {act}")

    after = measure_fn(copy.deepcopy(sb_new))

    claimed = evidence.get("checker_deltas") if isinstance(evidence, dict) else None
    if claimed:
        for k, v in claimed.items():
            if k not in before or k not in after:
                raise PatchError(f"Unknown metric in evidence: {k}")
            delta = after[k] - before[k]
            # directions must agree
            if (delta > 0 and v < 0) or (delta < 0 and v > 0):
                raise PatchError(f"Evidence mismatch for {k}: claimed {v}, observed {delta}")
        notes.append("Evidence verified")
    return sb_new, notes
