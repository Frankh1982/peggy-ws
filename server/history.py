# HISTORY_HELPER_V1
import os, json
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

HISTORY_FILE = Path(os.getenv("HISTORY_FILE", "history.jsonl"))
HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)

def log_event(event: dict) -> None:
    """Append a JSON line with a UTC timestamp."""
    item = {"ts": datetime.now(timezone.utc).isoformat(), **event}
    with HISTORY_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")
