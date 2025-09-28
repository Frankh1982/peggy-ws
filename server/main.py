# peggy-ws / server/main.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .auth import require_bearer
from .llm_provider import stream_response
from .history import log_event

app = FastAPI(title="peggy-ws")

# Serve the web client from /app so it works on Wi-Fi AND cellular via the tunnel
app.mount("/app", StaticFiles(directory="client", html=True), name="app")

@app.get("/", response_class=HTMLResponse)
def home():
    return '<h3>peggy-ws online (OpenAI streaming + history) — <a href="/app/">open client</a></h3>'

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    # Accept the socket, then require the token (?token=...)
    await ws.accept()
    await require_bearer(ws)

    # Light handshake so the client knows we’re ready
    await ws.send_text("ready")

    try:
        while True:
            # Get a single user message
            user_text = await ws.receive_text()
            print(">> USER:", user_text)
            log_event({"dir": "in", "text": user_text})

            # Minimal prompt to the model
            messages = [
                {"role": "system", "content": "You are Peggy-Core. Be clear and concise."},
                {"role": "user", "content": user_text},
            ]

            # Stream back chunks; always flush an end marker
            chunks = []
            try:
                async for chunk in stream_response(messages):
                    chunks.append(chunk)
                    await ws.send_text(chunk)
            except Exception as e:
                err = f"[error] {type(e).__name__}: {e}"
                print(err)
                log_event({"dir": "err", "error": err})
                await ws.send_text(err)
            finally:
                reply = "".join(chunks).strip()
                log_event({"dir": "out", "text": reply})
                await ws.send_text("--- end ---")

    except WebSocketDisconnect:
        print("client disconnected")
        return
