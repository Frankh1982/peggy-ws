from __future__ import annotations
import json, sys, time

def grs(payload: dict) -> dict:
    keys = ["prereqs_ok","resources_ok","risk_inverse","context_freshness","ops_fit"]
    missing = [k for k in keys if k not in payload]
    if missing:
        return {"grs": 0.0, "pass": False, "reasons":[f"missing:{','.join(missing)}"]}
    vals = [max(0.0, min(1.0, float(payload[k]))) for k in keys]
    g = sum(vals)/len(vals)
    return {"grs": round(g, 3), "pass": g >= 0.80, "reasons":[]}

if __name__ == "__main__":
    payload = json.loads(sys.stdin.read() or "{}")
    out = grs(payload)
    out["timestamp"] = int(time.time())
    print(json.dumps(out, ensure_ascii=False))
