from __future__ import annotations
import json, os

LEDGER = "server/foundation/ledger.json"

def load_json(path):
    # tolerate UTF-8 BOM on Windows
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def rule_ids(heur):
    ids = []
    for r in heur.get("rules", []):
        rid = r.get("id")
        if isinstance(rid, str):
            ids.append(rid.strip().lower())
    return set(ids)

def link_all(modules_dir="server/modules"):
    ledger = load_json(LEDGER)
    topics = {}
    for root, dirs, files in os.walk(modules_dir):
        if os.path.basename(root) != "studies" or "heuristics.json" not in files:
            continue
        parts = root.split(os.sep)
        # server / modules / <topic> / studies  -> topic is parts[-2]
        topic = parts[-2]
        if topic.startswith("_"):  # skip templates like _templates
            continue
        heur = load_json(os.path.join(root, "heuristics.json"))
        ids = rule_ids(heur)
        if not ids:
            continue
        topics[topic] = ids

    existing = {(x["a"], x["b"]) for x in ledger.get("xlinks", [])}
    added = 0
    names = sorted(topics.keys())
    for i in range(len(names)):
        for j in range(i+1, len(names)):
            a, b = names[i], names[j]
            shared = topics[a] & topics[b]
            if not shared or (a, b) in existing:
                continue
            why = f"shared heuristic(s): {', '.join(sorted(shared))}"
            ledger.setdefault("xlinks", []).append({"a": a, "b": b, "why": why})
            added += 1
    if added:
        save_json(LEDGER, ledger)
    return added

if __name__ == "__main__":
    print(json.dumps({"type": "xlinks", "added": link_all(), "examples": []}))
