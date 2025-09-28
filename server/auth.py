# AUTH_DEBUG_V3 — read .env by path; fallback parser for odd encodings
import os
from pathlib import Path
from urllib.parse import unquote
from fastapi import WebSocket, WebSocketDisconnect, status
from dotenv import load_dotenv, dotenv_values

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"

def _mask(s: str) -> str:
    if not s: return ""
    s = s.strip()
    return s if len(s) < 4 else (s[:2] + "…" + s[-2:])

def _expected_token() -> str:
    """
    Try multiple ways so weird encodings don’t break auth:
    1) dotenv_values (reads file directly)
    2) load_dotenv + os.getenv
    3) manual parse as last resort (utf-8 -> utf-16)
    """
    # 1) direct map
    try:
        m = dotenv_values(dotenv_path=ENV_PATH)
        val = (m.get("ACCESS_TOKEN") or "").strip()
        if val:
            return val
    except Exception:
        pass

    # 2) env overlay
    try:
        load_dotenv(dotenv_path=ENV_PATH, override=True)
        val = (os.getenv("ACCESS_TOKEN") or "").strip()
        if val:
            return val
    except Exception:
        pass

    # 3) manual parse, tolerant encodings
    for enc in ("utf-8", "utf-16", "utf-8-sig"):
        try:
            txt = ENV_PATH.read_text(encoding=enc, errors="ignore")
            for line in txt.splitlines():
                if line.startswith("ACCESS_TOKEN="):
                    return line.split("=", 1)[1].strip()
        except Exception:
            continue
    return ""

async def require_bearer(ws: WebSocket) -> None:
    token = unquote(ws.query_params.get("token", "")).strip()
    expected = _expected_token()

    print(f"[auth] .env={ENV_PATH} exists={ENV_PATH.exists()} | expected len={len(expected)} {_mask(expected)} | got len={len(token)} {_mask(token)}")

    if not expected or token != expected:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason="bad token")
        raise WebSocketDisconnect()
