# MAIN_EXP_MEM_V4 — memory + bandit + foundation + Wordle modules + autolearn
import os, json, uuid, re
from typing import Dict, List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .auth import require_bearer
from .llm_provider import stream_response
from .history import log_event
from .svec import build_svec, bucketize_svec
from .policy import choose, update, addon_for
from .memory import SessionMemory

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
app = FastAPI(title="peggy-ws")
app.mount("/app", StaticFiles(directory="client", html=True), name="app")

@app.get("/", response_class=HTMLResponse)
def home():
    return '<h3>peggy-ws online — <a href="/app/">open client</a></h3>'

# ---------------- Foundation bridge (safe fallbacks) ----------------
try:
    from .foundation.bridge import propose_and_apply_patch, load_statebook, save_statebook
    _FOUNDATION = True
except Exception:
    _FOUNDATION = False
    def load_statebook() -> Dict: return {}
    def save_statebook(sb: Dict) -> None: pass
    async def propose_and_apply_patch(**kwargs) -> Dict:
        return {"applied": False, "error": "no_foundation", "notes": [], "raw": None, "project_id": ""}

# ---------------- Autolearn (self-study) ----------------
try:
    from .foundation.autolearn import run_autolearn
    _AUTOLEARN = True
except Exception:
    _AUTOLEARN = False
    async def run_autolearn(project_id: str, sb: Dict) -> Dict:
        return {"project": project_id, "applied": False, "files": [], "error": "no_autolearn", "notes": []}

# ---------------- Wordle modules (prefer your module files; fallback to light in-file logic) ----------------
# checkers (dictionary + legality + info gain)
_WORDLE_CHECKERS_OK = False
try:
    # Preferred new path (you created server/foundation/modules/wordle/checker.py)
    from .foundation.modules.wordle.checker import get_dict, dict_len, filter_candidates, info_gain_score
    _WORDLE_CHECKERS_OK = True
except Exception:
    try:
        # Older path we used before
        from .foundation.checkers.wordle_checkers import get_dict, dict_len, filter_candidates, info_gain_score
        _WORDLE_CHECKERS_OK = True
    except Exception:
        # Minimal fallbacks so the server never crashes; dict will be 0 if you don't have a dictionary file.
        _WORDLE_CHECKERS_OK = False
        def get_dict() -> List[str]: return []
        def dict_len() -> int: return 0
        def filter_candidates(cons: Dict, dictionary=None) -> List[str]: return []
        def info_gain_score(w: str, cands: List[str]) -> float: return 0.0

# parser (plain-English → constraints)
_wordle_apply_from_nl = None
try:
    # If you have server/foundation/modules/wordle/parser.py with an apply(...) function
    from .foundation.modules.wordle.parser import apply as _wordle_apply_from_nl  # type: ignore
except Exception:
    try:
        # alternative name some folks prefer
        from .foundation.modules.wordle.parser import apply_feedback_from_nl as _wordle_apply_from_nl  # type: ignore
    except Exception:
        _wordle_apply_from_nl = None

# suggester (can blend heuristics learned by autolearn)
_wordle_suggest_func = None
try:
    # If you have server/foundation/modules/wordle/suggest.py with suggest(sb) → {guess,candidates,dict?,used?}
    from .foundation.modules.wordle.suggest import suggest as _wordle_suggest_func  # type: ignore
except Exception:
    _wordle_suggest_func = None

# ---------------- Wordle: minimal defaults kept in main as a safety net ----------------
_POS = {"first":0,"1st":0,"second":1,"2nd":1,"third":2,"3rd":2,"fourth":3,"4th":3,"fifth":4,"5th":4}
_DEFAULT = {
    "greens": ["","","","",""],
    "yellows_not_here": [[],[],[],[],[]],
    "must_include": [],
    "must_exclude": [],
    "min_counts": {},
    "max_counts": {}
}
def _ensure_bootstrap(sb: Dict) -> None:
    sb.setdefault("project",{}); sb.setdefault("state",{})
    if sb["project"].get("id")!="wordle": return
    sb["project"].setdefault("goal","Solve today's Wordle in ≤ 4 guesses.")
    sb["project"].setdefault("deliverable","Legal 5-letter guesses until solved.")
    sb["project"].setdefault("success_checks",["valid_word","respects_constraints","novel_guess"])
    sb["state"].setdefault("constraints",{k:(v.copy() if isinstance(v,list) else v) for k,v in _DEFAULT.items()})
    sb["state"].setdefault("history",[])
    sb["state"].setdefault("_last_guess","")

def _reset(sb: Dict) -> None:
    sb.setdefault("state",{})
    sb["state"]["constraints"] = {k:(v.copy() if isinstance(v,list) else v) for k,v in _DEFAULT.items()}
    sb["state"]["history"] = []
    sb["state"]["_last_guess"] = ""

def _constraints_block(sb: Dict) -> str:
    if sb.get("project",{}).get("id")!="wordle": return ""
    cons = sb["state"]["constraints"]
    greens = "".join([c if c else "_" for c in cons["greens"]])
    must_inc = "".join(sorted(set(cons["must_include"]))) or "(none)"
    must_exc = "".join(sorted(set(cons["must_exclude"]))) or "(none)"
    ynh = cons["yellows_not_here"]
    ysum = ", ".join([f"{i+1}:{''.join(sorted(set(y)))}" for i,y in enumerate(ynh) if y]) or "(none)"
    return (
        "ACTIVE MODULE: WORDLE. Obey all constraints.\n"
        f"GREENS pattern: {greens}\n"
        f"MUST INCLUDE: {must_inc}\n"
        f"MUST EXCLUDE: {must_exc}\n"
        f"YELLOWS not allowed positions: {ysum}\n"
        "Never propose non-words. Never place letters in disallowed positions."
    )

def _guess_tokens(text: str) -> List[str]:
    return [w.lower() for w in re.findall(r"\b([A-Za-z]{5})\b", text or "")]

def _uniq_inplace(lst: List[str]) -> None:
    seen=set(); i=0
    for x in lst:
        if x not in seen: lst[i]=x; i+=1; seen.add(x)
    del lst[i:]

def _apply_from_nl_fallback(sb: Dict, user_text: str) -> bool:
    """Fallback NL parser if modules.wordle.parser is not available."""
    if sb.get("project",{}).get("id")!="wordle": return False
    t_raw = (user_text or "").strip()
    if not t_raw: return False
    txt = t_raw.lower()

    # reset
    if re.search(r"\b(new\s+game|restart|reset|start\s+over|new\s+puzzle)\b", txt):
        _reset(sb); return True

    _ensure_bootstrap(sb)
    cons = sb["state"]["constraints"]; cons.setdefault("min_counts",{}); cons.setdefault("max_counts",{})
    before_last = sb["state"].get("_last_guess","")
    changed = False

    # record last 5‑letter token as active guess
    toks = _guess_tokens(t_raw)
    if toks:
        g = toks[-1]
        if g != sb["state"].get("_last_guess"):
            sb["state"]["_last_guess"] = g
            sb["state"]["history"].append({"guess": g})
            changed = True
    last_guess = sb["state"].get("_last_guess","")
    ref_guess  = toks[-1] if toks else last_guess

    def ban_pos(ch: str, idx: int) -> bool:
        y = cons["yellows_not_here"][idx]
        if ch not in y: y.append(ch); return True
        return False
    def add_in(ch:str)->bool:
        if ch not in cons["must_include"]: cons["must_include"].append(ch); return True
        return False
    def add_out(ch:str)->bool:
        if ch not in cons["greens"] and ch not in cons["must_include"] and ch not in cons["must_exclude"]:
            cons["must_exclude"].append(ch); return True
        return False
    def letters(blob: str) -> List[str]:
        return [c.lower() for c in re.findall(r"[a-z]", blob)]

    # 0/none correct
    if re.search(r"\b(?:none|no|0)\s+(?:letters?|chars?)\s+(?:are|is)\s+(?:correct|in\s+the\s+word)\b", txt):
        if last_guess:
            for ch in set(last_guess): changed |= add_out(ch)

    # excludes/includes
    for ch in re.findall(r"\bno\s+([a-z])\b", txt):  changed |= add_out(ch)
    for ch in re.findall(r"\bexclude\s+([a-z])\b", txt): changed |= add_out(ch)

    # doubles
    for ch in re.findall(r"\b(?:double|two)\s+([a-z])'?s?\b", txt):
        c=ch.lower(); cons["min_counts"][c] = max(int(cons["min_counts"].get(c,0)), 2); changed = True
    for ch in re.findall(r"\b(?:only|just|single)\s+one\s+([a-z])\b", txt):
        c=ch.lower(); cons["max_counts"][c] = 1; changed = True

    # YELLOW
    for m in re.finditer(r"\b([a-z](?:\s*,\s*[a-z])*(?:\s+and\s+[a-z])?)\s+are\s+yellow\b", txt):
        for ch in letters(m.group(1)):
            changed |= add_in(ch)
            if ref_guess:
                for idx,gch in enumerate(ref_guess):
                    if gch==ch: changed |= ban_pos(ch, idx)
    for m in re.finditer(r"\b([a-z])\s+is\s+yellow\b", txt):
        ch=m.group(1).lower(); changed |= add_in(ch)
        if ref_guess:
            for idx,gch in enumerate(ref_guess):
                if gch==ch: changed |= ban_pos(ch, idx)
    for m in re.finditer(r"\b([a-z](?:\s*,\s*[a-z])+)\s*,\s*yellow\b", txt):
        for ch in letters(m.group(1)):
            changed |= add_in(ch)
            if ref_guess:
                for idx,gch in enumerate(ref_guess):
                    if gch==ch: changed |= ban_pos(ch, idx)

    # GREEN / right place
    if ref_guess:
        for m in re.finditer(r"\b([a-z](?:\s*,\s*[a-z])*(?:\s+and\s+[a-z])?)\s+are\s+(?:all\s+)?green\b", txt):
            for ch in letters(m.group(1)):
                for idx,gch in enumerate(ref_guess):
                    if gch==ch and cons["greens"][idx]!=ch:
                        cons["greens"][idx]=ch; changed=True
                        if ch in cons["must_exclude"]: cons["must_exclude"].remove(ch); changed=True
        for m in re.finditer(r"\b([a-z])\s+is\s+green\b", txt):
            ch=m.group(1).lower()
            for idx,gch in enumerate(ref_guess):
                if gch==ch and cons["greens"][idx]!=ch:
                    cons["greens"][idx]=ch; changed=True
                    if ch in cons["must_exclude"]: cons["must_exclude"].remove(ch); changed=True
        mg = re.search(r"\b([a-z](?:\s*,\s*[a-z])*(?:\s+and\s+[a-z])?)\s+(?:are|is)\s+in\s+the\s+(?:right|correct)\s+(?:place|position)s?\b", txt)
        if mg:
            for ch in letters(mg.group(1)):
                for idx,gch in enumerate(ref_guess):
                    if gch==ch and cons["greens"][idx]!=ch:
                        cons["greens"][idx]=ch; changed=True
                        if ch in cons["must_exclude"]: cons["must_exclude"].remove(ch); changed=True

    # GRAY
    for m in re.finditer(r"\b([a-z](?:\s*,\s*[a-z])*(?:\s+and\s+[a-z])?)\s+are\s+gray\b", txt):
        for ch in letters(m.group(1)): changed |= add_out(ch)
    for m in re.finditer(r"\b([a-z])\s+is\s+gray\b", txt):
        changed |= add_out(m.group(1).lower())
    for m in re.finditer(r"\b([a-z](?:\s*,\s*[a-z])+)\s*,\s*gray\b", txt):
        for ch in letters(m.group(1)): changed |= add_out(ch)

    # wrong-place variants
    m = re.search(r"\b([a-z](?:\s*,\s*[a-z])*(?:\s+and\s+[a-z])?)\s+(?:are|is)\s+in\s+the\s+word\s+but\s+(?:in\s+the\s+)?wrong\s+(?:place|position|spot)s?\b", txt)
    if m:
        letters_set = letters(m.group(1))
        for ch in letters_set: changed |= add_in(ch)
        if ref_guess:
            for ch in letters_set:
                for idx,gch in enumerate(ref_guess):
                    if gch==ch: changed |= ban_pos(ch, idx)
    m2 = re.search(r"\bthe\s+([a-z])\s+in\s+([a-z]{5})\s+is\s+in\s+the\s+word\s+but\s+not\s+in\s+that\s+(?:spot|place|position)\b", txt)
    if m2:
        ch=m2.group(1).lower(); g=m2.group(2).lower()
        changed |= add_in(ch)
        for idx,gch in enumerate(g):
            if gch==ch: changed |= ban_pos(ch, idx)
    m3 = re.search(r"\b([a-z])\s+is\s+in\s+the\s+word\s+but\s+not\s+in\s+the\s+([a-z0-9]+)\s+(?:spot|place|position)\b", txt)
    if m3:
        ch=m3.group(1).lower(); idx=_POS.get(m3.group(2).lower())
        changed |= add_in(ch)
        if idx is not None: changed |= ban_pos(ch, idx)

    # dedupe
    _uniq_inplace(cons["must_include"]); _uniq_inplace(cons["must_exclude"])
    for i in range(5): _uniq_inplace(cons["yellows_not_here"][i])

    return changed or (before_last != sb["state"].get("_last_guess",""))

def _apply_from_nl(sb: Dict, user_text: str) -> bool:
    """Prefer external parser module; otherwise fallback."""
    if _wordle_apply_from_nl:
        try:
            return bool(_wordle_apply_from_nl(sb, user_text))  # type: ignore
        except Exception as e:
            log_event({"dir":"module","note":"parser_error","error":str(e)})
    return _apply_from_nl_fallback(sb, user_text)

def _validated_suggestion(sb: Dict) -> Dict:
    """Prefer external suggester; otherwise use checkers+info gain."""
    # try your modules/wordle/suggest.py first
    if _wordle_suggest_func:
        try:
            out = _wordle_suggest_func(sb)  # type: ignore
            if isinstance(out, dict):
                # normalize keys we care about
                return {
                    "guess": out.get("guess"),
                    "candidates": int(out.get("candidates", 0)),
                    "dict": int(out.get("dict", dict_len() if _WORDLE_CHECKERS_OK else 0)),
                    "used": out.get("used")
                }
        except Exception as e:
            log_event({"dir":"module","note":"suggest_error","error":str(e)})

    # fallback: checkers + info gain
    if not _WORDLE_CHECKERS_OK:  # no dictionary
        return {"guess": None, "candidates": 0, "dict": 0}

    cons = sb["state"]["constraints"]
    dictionary = get_dict()
    cands = filter_candidates(cons, dictionary)
    if not cands:
        return {"guess": None, "candidates": 0, "dict": len(dictionary)}
    best = max(cands, key=lambda w: info_gain_score(w, cands))
    return {"guess": best, "candidates": len(cands), "dict": len(dictionary)}

# ---------------- WebSocket ----------------
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

            # thumbs feedback → bandit reward
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
            user_text  = str(data.get("text","")).strip()
            session_id = str(data.get("session_id","default")).strip() or "default"
            if not user_text:
                await ws.send_text(json.dumps({"type":"error","error":"empty message"}))
                continue

            # per-session memory
            mem = SessionMemory(session_id)
            mem.add_user(user_text); mem.save()

            # --- PRE-STREAM: activate Wordle if mentioned; parse NL → constraints; emit status ---
            sb = load_statebook() or {"project": {}, "state": {}}
            if "wordle" in user_text.lower():
                sb.setdefault("project", {})["id"] = "wordle"
                _ensure_bootstrap(sb)
                save_statebook(sb)

            sb = load_statebook() or {}
            if sb.get("project", {}).get("id") == "wordle":
                _ensure_bootstrap(sb)

                # autolearn trigger (chat: "learn: wordle" or "learn wordle")
                if _AUTOLEARN and re.search(r"\blearn\b.*\bwordle\b", user_text.lower()):
                    res = await run_autolearn("wordle", sb)
                    await ws.send_text(json.dumps({"type":"learn", **res}))

                # parse NL → constraints
                if _apply_from_nl(sb, user_text):
                    save_statebook(sb)
                    cons = sb["state"]["constraints"]
                    greens = "".join([c if c else "_" for c in cons["greens"]])
                    await ws.send_text(json.dumps({
                        "type":"constraints",
                        "greens": greens,
                        "must_include": cons["must_include"],
                        "must_exclude": cons["must_exclude"]
                    }))

                # always emit a module status line (activation + dict size)
                dlen = int(dict_len()) if _WORDLE_CHECKERS_OK else 0
                await ws.send_text(json.dumps({
                    "type":"module",
                    "id":"wordle",
                    "active": True,
                    "dict": dlen
                }))

                # pre-stream suggestion (server-validated)
                pre = _validated_suggestion(sb)
                if pre:
                    pre["stage"] = "pre"
                    await ws.send_text(json.dumps({"type":"suggestion", **pre}))

            # bandit choice
            svec = build_svec(user_text, OPENAI_MODEL)
            bucket = bucketize_svec(svec)
            principle = choose(bucket)
            exp_id = uuid.uuid4().hex

            await ws.send_text(json.dumps({"type":"meta","exp_id":exp_id,"principle":principle,"session_id":session_id}))
            log_event({"dir":"in","text":user_text,"session_id":session_id,"svec":svec,
                       "bucket":bucket,"principle":principle,"exp_id":exp_id})

            # system prompt (tiny, with explicit Wordle permission)
            sys_prompt = (
                "You are Peggy-Core. Be clear and concise. "
                "You MAY use facts explicitly provided earlier in THIS session. "
                "If asked for such a fact, answer from session context; if missing, say you don't know and ask. "
                "Do not invent facts. If the project is Wordle, do not refuse—propose legal guesses within constraints and request marks."
            )
            addon = addon_for(principle)
            if addon: sys_prompt += " " + addon

            # build messages (durable + recent + compact module context)
            messages = [{"role":"system","content":sys_prompt}]
            messages += mem.context_messages()
            messages += mem.recent_messages(max_turns=12, max_chars=5000)
            if sb.get("project", {}).get("id") == "wordle":
                block = _constraints_block(sb)
                if block:
                    messages.append({"role":"system","content": block})
            messages.append({"role":"user","content": user_text})

            # stream reply
            chunks = []
            try:
                async for chunk in stream_response(messages):
                    chunks.append(chunk); await ws.send_text(chunk)
            except Exception as e:
                err = f"[error] {type(e).__name__}: {e}"
                await ws.send_text(err); log_event({"dir":"err","error":err,"exp_id":exp_id,"session_id":session_id})
            finally:
                reply = "".join(chunks).strip()
                mem.add_assistant(reply); await mem.maybe_summarize_async(); mem.save()

                # foundation pass (generic)
                try:
                    fnd = await propose_and_apply_patch(user_text=user_text, assistant_reply=reply)
                    log_event({"dir":"foundation","applied":fnd.get("applied"),"error":fnd.get("error"),
                               "notes":fnd.get("notes"),"project":fnd.get("project_id"),
                               "raw":(fnd.get("raw") or "")[:400],"exp_id":exp_id,"session_id":session_id})
                    await ws.send_text(json.dumps({"type":"foundation","applied":fnd.get("applied"),
                                                   "error":fnd.get("error"),"project":fnd.get("project_id")}))
                except Exception as _e:
                    log_event({"dir":"foundation","error":f"[guard] {type(_e).__name__}: {_e}",
                               "exp_id":exp_id,"session_id":session_id})

                # post-stream suggestion (server-validated)
                if sb.get("project", {}).get("id") == "wordle":
                    sug = _validated_suggestion(sb)
                    if sug:
                        sug["stage"] = "post"
                        await ws.send_text(json.dumps({"type":"suggestion", **sug}))

                log_event({"dir":"out","text":reply,"exp_id":exp_id,"session_id":session_id})
                await ws.send_text("--- end ---")
                PENDING[exp_id] = {"bucket":bucket,"principle":principle}

    except WebSocketDisconnect:
        return
