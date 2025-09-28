from typing import Dict

def build_ssig(statebook: Dict, project_id: str) -> Dict:
    if project_id == "wordle":
        return {"problem_type":"constraint_search",
                "search_space":{"kind":"discrete","size_log10":3.5,"branching":26},
                "feedback":{"mode":"symbolic","arity":3,"deterministic":True},
                "objective":{"form":"prune_to_singleton"},
                "constraints":{"hard":True,"dynamic":True},
                "verifiers":["valid_word","respects_constraints","novel_guess"]}
    return {"problem_type":"unknown"}

def build_esig(before: Dict[str,float], after: Dict[str,float]) -> Dict:
    esig = {}
    for k in set(before) | set(after):
        esig[k] = after.get(k,0.0) - before.get(k,0.0)
    return {"checker_deltas": esig}
