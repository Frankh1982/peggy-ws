# MAIN_EXP_MEM_V1 — bandit + per-session memory + foundation patch hook
import os, json, uuid
from typing import Dict
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .auth import require_bearer
from .llm_provider import stream_response
from .history import log_event
from .svec import build_svec, bucketize_svec
from .policy import choose, update, addon_for
from .memory import SessionMemory
from .foundation.bridge import propose_and_apply_patch  # ⬅️ NEW: proof-gated self-edit cycle

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

app = FastAPI(title="peggy-ws")
app.mount("/app", StaticFiles(directory="client", html=True), name="app")

@app.get("/", response_class=HTMLResponse)
def home():
    return '<h3>peggy-ws online (learning + session memory) — <a href="/app/">open client</a></h3>'

# experiment bookkeeping: exp_id -> {bucket, principle}
PENDING: Dict[str, Dict[str, str]] = {}

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    await require_bearer(ws)
    await ws.send_text("ready")

    try:
        while True:
            raw = await ws.receive_text()
            try:
                data = json.loads(raw)
                mtype = data.get("type", "message")
            except Exception:
                data = {"type": "message", "text": raw}
                mtype = "message"

            if mtype == "feedback":
                exp_id = str(data.get("exp_id", ""))
                val = float(data.get("value", 0))
                meta = PENDING.pop(exp_id, None)
                if meta:
                    update(meta["bucket"], meta["principle"], val)
                    log_event({"dir":"reward","exp_id":exp_id,"principle":meta["principle"],
                               "bucket":meta["bucket"],"reward":val})
                await ws.send_text(json.dumps({"type":"ack","exp_id":exp_id}))
                continue

            # user message
            user_text   = str(data.get("text", "")).strip()
            session_id  = str(data.get("session_id", "default")).strip() or "default"
            if not user_text:
                await ws.send_text(json.dumps({"type":"error","error":"empty message"}))
                continue

            # session memory
            mem = SessionMemory(session_id)
            mem.add_user(user_text)
            mem.save()

            # situation features + bandit choice
            svec    = build_svec(user_text, OPENAI_MODEL)
            bucket  = bucketize_svec(svec)
            principle = choose(bucket)
            exp_id  = uuid.uuid4().hex

            # tell client which principle we chose
            await ws.send_text(json.dumps({"type":"meta","exp_id":exp_id,"principle":principle,"session_id":session_id}))

            log_event({"dir":"in","text":user_text,"session_id":session_id,"svec":svec,
                       "bucket":bucket,"principle":principle,"exp_id":exp_id})

            # ---- system prompt with explicit memory policy ----
            sys_prompt = (
                "You are Peggy-Core. Be clear and concise. "
                "You may use information the user explicitly provided earlier in THIS session "
                "(e.g., their name, preferences, answers) when responding. "
                "If the user asks for such info (e.g., 'what is my name?'), answer from session context "
                "instead of saying you don't have access. "
                "Do not invent facts that were not stated this session."
            )
            addon = addon_for(principle)
            if addon:
                sys_prompt += " " + addon

            # build messages with session memory context
            messages = [{"role":"system","content":sys_prompt}]
            messages += mem.context_messages()
            messages.append({"role":"user","content":user_text})

            chunks = []
            try:
                async for chunk in stream_response(messages):
                    chunks.append(chunk)
                    await ws.send_text(chunk)
            except Exception as e:
                err = f"[error] {type(e).__name__}: {e}"
                await ws.send_text(err)
                log_event({"dir":"err","error":err,"exp_id":exp_id,"session_id":session_id})
            finally:
                reply = "".join(chunks).strip()
                mem.add_assistant(reply)
                await mem.maybe_summarize_async()
                mem.save()

                # === Foundation self-edit pass (non-stream; safe no-op if no API key) ===
                try:
                    fnd = await propose_and_apply_patch(user_text=user_text, assistant_reply=reply)
                    log_event({
                        "dir": "foundation",
                        "applied": fnd.get("applied"),
                        "error":   fnd.get("error"),
                        "notes":   fnd.get("notes"),
                        "project": fnd.get("project_id"),
                        "raw":     (fnd.get("raw") or "")[:400],
                        "exp_id":  exp_id,
                        "session_id": session_id
                    })
                except Exception as _e:
                    log_event({"dir":"foundation","error": f"[guard] {type(_e).__name__}: {_e}",
                               "exp_id":exp_id,"session_id":session_id})
                # === end foundation pass ===

                log_event({"dir":"out","text":reply,"exp_id":exp_id,"session_id":session_id})
                await ws.send_text("--- end ---")
                PENDING[exp_id] = {"bucket":bucket,"principle":principle}

    except WebSocketDisconnect:
        return
