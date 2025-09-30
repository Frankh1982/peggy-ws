import json, pathlib
from jsonschema import validate

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCH  = ROOT / "server" / "foundation" / "schemas"

def load(p):
    with open(p, "r", encoding="utf-8-sig") as f:
        return json.load(f)

ledger    = load(ROOT/"server/foundation/ledger.json")
statebook = load(ROOT/"server/foundation/statebook.json")
sch_ledg  = load(SCH/"ledger.schema.json")
sch_stat  = load(SCH/"statebook.schema.json")
sch_heur  = load(SCH/"heuristics.schema.json")

validate(ledger, sch_ledg)
validate(statebook, sch_stat)

for p in ROOT.glob("server/modules/*/studies/heuristics.json"):
    topic_dir = p.parent.parent.name  # modules/<topic>/studies
    if topic_dir.startswith("_"):     # skip templates
        continue
    validate(load(p), sch_heur)

print("OK: JSON schema validation passed.")
