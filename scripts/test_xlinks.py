import json, pathlib, sys
p = pathlib.Path("server/foundation/ledger.json")
led = json.loads(open(p, "r", encoding="utf-8-sig").read())
ok = any(x.get("a") and x.get("b") for x in led.get("xlinks", []))
print("xlinks present:", ok)
sys.exit(0 if ok else 1)
