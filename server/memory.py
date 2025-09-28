# MEMORY_V1B — per-session memory with fact extraction (name) + recent + summary
import os, json, re
from pathlib import Path
from typing import List, Dict
from datetime import datetime, timezone
from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

ROOT     = Path(__file__).resolve().parent.parent
SESS_DIR = ROOT / "sessions"
SESS_DIR.mkdir(exist_ok=True)

MAX_RECENT_CHARS = 2000
KEEP_TURNS        = 4

# capture: "my name is Frank", "I'm Frank", "I am Frank", "call me Frank"
NAME_PAT = re.compile(
    r"\b(?:my\s+name\s+is|i\s*am|i'm|call\s+me)\s+([A-Za-z][A-Za-z\-'.]{1,40})\b",
    flags=re.IGNORECASE
)

def _norm_name(s: str) -> str:
    s = s.strip().strip(".,;:!?)(")
    parts = re.split(r"([\-'])", s)
    return "".join(p.capitalize() if p.isalpha() else p for p in parts)

class SessionMemory:
    def __init__(self, session_id: str):
        self.session_id = session_id or "default"
        self.path = SESS_DIR / f"{self.session_id}.json"
        self.data: Dict = {"session_id": self.session_id, "facts": [], "summary": "", "recent": []}
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                pass

    def save(self):
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _ingest_facts_from_user(self, text: str):
        m = NAME_PAT.search(text or "")
        if m:
            name = _norm_name(m.group(1))
            fact = f"name={name}"
            facts = set(self.data.get("facts", []))
            if fact not in facts:
                facts.add(fact)
                self.data["facts"] = sorted(facts)

    def add_user(self, text: str):
        self._ingest_facts_from_user(text)
        self.data["recent"].append({"role": "user", "text": text, "ts": self._now()})

    def add_assistant(self, text: str):
        self.data["recent"].append({"role": "assistant", "text": text, "ts": self._now()})

    def _recent_chars(self) -> int:
        return sum(len(r.get("text", "")) for r in self.data.get("recent", []))

    def context_messages(self) -> List[Dict[str, str]]:
        parts = []
        if self.data.get("facts"):
            parts.append("Known user facts: " + "; ".join(self.data["facts"]))
        if self.data.get("summary"):
            parts.append("Session summary: " + self.data["summary"])
        if not parts:
            return []
        return [{"role": "system", "content": "(Session memory) " + " | ".join(parts)}]

    def recent_messages(self, max_turns: int = 6, max_chars: int = 1000) -> List[Dict[str, str]]:
        """Return tail of raw conversation as chat messages for immediate recall."""
        msgs: List[Dict[str, str]] = []
        chars = 0
        for r in reversed(self.data.get("recent", [])):
            txt = r.get("text", "")
            if not txt:
                continue
            if chars + len(txt) > max_chars:
                break
            msgs.append({
                "role": ("assistant" if r["role"] == "assistant" else "user"),
                "content": txt
            })
            chars += len(txt)
            if len(msgs) >= max_turns:
                break
        msgs.reverse()
        return msgs

    async def maybe_summarize_async(self):
        if self._recent_chars() <= MAX_RECENT_CHARS:
            return
        if not OPENAI_API_KEY:
            while self._recent_chars() > MAX_RECENT_CHARS and self.data["recent"]:
                self.data["recent"].pop(0)
            self.save()
            return

        pre = []
        if self.data.get("facts"):
            pre.append("Prior facts: " + "; ".join(self.data["facts"]))
        if self.data.get("summary"):
            pre.append("Prior summary: " + self.data["summary"])
        lines = [f"{r['role']}: {r['text']}" for r in self.data.get("recent", [])]
        content = (
            (("\n".join(pre) + "\n") if pre else "") +
            "Conversation to compress:\n" + "\n".join(lines) +
            "\n\nReturn STRICT JSON with keys: facts (list of durable user facts, if any), "
            "summary (<=150 words). No extra text."
        )

        client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        try:
            resp = await client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "You condense chat into durable memory."},
                    {"role": "user", "content": content},
                ],
            )
            out = resp.choices[0].message.content.strip()
            obj = json.loads(out)
            if isinstance(obj.get("facts"), list):
                exist = set(self.data.get("facts", []))
                for f in obj["facts"]:
                    if isinstance(f, str) and f.strip():
                        exist.add(f.strip())
                self.data["facts"] = sorted(exist)
            if isinstance(obj.get("summary"), str):
                self.data["summary"] = obj["summary"].strip()
            self.data["recent"] = self.data["recent"][-KEEP_TURNS:]
        except Exception:
            while self._recent_chars() > MAX_RECENT_CHARS and self.data["recent"]:
                self.data["recent"].pop(0)
        self.save()

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()
