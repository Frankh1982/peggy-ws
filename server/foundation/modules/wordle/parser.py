import re
from typing import Dict, List

_POS = {"first":0,"1st":0,"second":1,"2nd":1,"third":2,"3rd":2,"fourth":3,"4th":3,"fifth":4,"5th":4}
_DEFAULT = {
    "greens": ["","","","",""],
    "yellows_not_here": [[],[],[],[],[]],
    "must_include": [],
    "must_exclude": [],
    "min_counts": {},
    "max_counts": {}
}

def ensure_bootstrap(sb: Dict) -> None:
    sb.setdefault("project",{}); sb.setdefault("state",{})
    if sb["project"].get("id") != "wordle": return
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

def _uniq_inplace(lst: List[str]) -> None:
    s=set(); i=0
    for x in lst:
        if x not in s:
            lst[i]=x; i+=1; s.add(x)
    del lst[i:]

def _letters(blob: str) -> List[str]:
    return [c.lower() for c in re.findall(r"[a-z]", blob)]

def _guess_tokens(text: str) -> List[str]:
    return [w.lower() for w in re.findall(r"\b([A-Za-z]{5})\b", text)]

def constraints_block(sb: Dict) -> str:
    if sb.get("project",{}).get("id")!="wordle": return ""
    cons = sb.get("state",{}).get("constraints", _DEFAULT)
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

def compact_summary(sb: Dict) -> Dict:
    cons = sb.get("state",{}).get("constraints", _DEFAULT)
    greens = "".join([c if c else "_" for c in cons["greens"]])
    return {"greens":greens, "must_include":cons["must_include"], "must_exclude":cons["must_exclude"]}

def apply_from_nl(sb: Dict, user_text: str) -> bool:
    """Parse plain English feedback (yellow/green/gray, ordinals, doubles, reset)."""
    if sb.get("project",{}).get("id")!="wordle": return False
    t_raw = (user_text or "").strip()
    if not t_raw: return False
    txt = t_raw.lower()

    # reset
    if re.search(r"\b(new\s+game|restart|reset|start\s+over|new\s+puzzle)\b", txt):
        _reset(sb); return True

    ensure_bootstrap(sb)
    cons = sb["state"]["constraints"]; cons.setdefault("min_counts",{}); cons.setdefault("max_counts",{})
    before_last = sb["state"].get("_last_guess","")
    changed = False

    # active guess from any 5-letter token
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

    # 0/none correct
    if re.search(r"\b(?:none|no|0)\s+(?:letters?|chars?)\s+(?:are|is)\s+(?:correct|in\s+the\s+word)\b", txt):
        if last_guess:
            for ch in set(last_guess): changed |= add_out(ch)

    # excludes/includes
    for ch in re.findall(r"\bno\s+([a-z])\b", txt):  changed |= add_out(ch)
    for ch in re.findall(r"\bexclude\s+([a-z])\b", txt): changed |= add_out(ch)

    # doubles: "double e"/"two e's"/"only one c"
    for ch in re.findall(r"\b(?:double|two)\s+([a-z])'?s?\b", txt):
        c=ch.lower(); cons["min_counts"][c] = max(int(cons["min_counts"].get(c,0)), 2); changed = True
    for ch in re.findall(r"\b(?:only|just|single)\s+one\s+([a-z])\b", txt):
        c=ch.lower(); cons["max_counts"][c] = 1; changed = True

    # YELLOW
    for m in re.finditer(r"\b([a-z](?:\s*,\s*[a-z])*(?:\s+and\s+[a-z])?)\s+are\s+yellow\b", txt):
        for ch in _letters(m.group(1)):
            changed |= add_in(ch)
            if ref_guess:
                for idx,gch in enumerate(ref_guess):
                    if gch==ch: changed |= ban_pos(ch, idx)
    for m in re.finditer(r"\b([a-z])\s+is\s+yellow\b", txt):
        ch=m.group(1).lower(); changed |= add_in(ch)
        if ref_guess:
            for idx,gch in enumerate(ref_guess):
                if gch==ch: changed |= ban_pos(ch, idx)
    # comma form: "A, E, yellow"
    for m in re.finditer(r"\b([a-z](?:\s*,\s*[a-z])+)\s*,\s*yellow\b", txt):
        for ch in _letters(m.group(1)):
            changed |= add_in(ch)
            if ref_guess:
                for idx,gch in enumerate(ref_guess):
                    if gch==ch: changed |= ban_pos(ch, idx)

    # GREEN (including "in the right/correct place")
    if ref_guess:
        for m in re.finditer(r"\b([a-z](?:\s*,\s*[a-z])*(?:\s+and\s+[a-z])?)\s+are\s+(?:all\s+)?green\b", txt):
            for ch in _letters(m.group(1)):
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
            for ch in _letters(mg.group(1)):
                for idx,gch in enumerate(ref_guess):
                    if gch==ch and cons["greens"][idx]!=ch:
                        cons["greens"][idx]=ch; changed=True
                        if ch in cons["must_exclude"]: cons["must_exclude"].remove(ch); changed=True

    # GRAY
    for m in re.finditer(r"\b([a-z](?:\s*,\s*[a-z])*(?:\s+and\s+[a-z])?)\s+are\s+gray\b", txt):
        for ch in _letters(m.group(1)): changed |= add_out(ch)
    for m in re.finditer(r"\b([a-z])\s+is\s+gray\b", txt):
        changed |= add_out(m.group(1).lower())
    for m in re.finditer(r"\b([a-z](?:\s*,\s*[a-z])+)\s*,\s*gray\b", txt):
        for ch in _letters(m.group(1)): changed |= add_out(ch)

    # wrong-place variants
    m = re.search(r"\b([a-z](?:\s*,\s*[a-z])*(?:\s+and\s+[a-z])?)\s+(?:are|is)\s+in\s+the\s+word\s+but\s+(?:in\s+the\s+)?wrong\s+(?:place|position|spot)s?\b", txt)
    if m:
        letters=_letters(m.group(1))
        for ch in letters: changed |= add_in(ch)
        if ref_guess:
            for ch in letters:
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

    # ordinals with duplicates: "first/second C is green/gray/yellow"
    def _occ_positions(ch: str, guess: str)->List[int]: return [i for i,c in enumerate(guess) if c==ch]
    for ord_word, ch, color in re.findall(r"\b(first|second|third|fourth|fifth|last)\s+([a-z])\s+is\s+(green|gray|yellow)\b", txt):
        ch=ch.lower()
        if ref_guess:
            pos = _occ_positions(ch, ref_guess)
            if not pos: continue
            idx = (pos[-1] if ord_word=="last" else (_POS.get(ord_word, None)))
            if isinstance(idx,int) and idx < len(pos):
                idx = pos[idx]
            if isinstance(idx,int):
                if color=="green":
                    if cons["greens"][idx]!=ch: cons["greens"][idx]=ch; changed=True
                    if ch in cons["must_exclude"]: cons["must_exclude"].remove(ch); changed=True
                elif color=="yellow":
                    changed |= add_in(ch); changed |= ban_pos(ch, idx)
                elif color=="gray":
                    changed |= ban_pos(ch, idx)
                    if ch in cons["must_include"] or ch in cons["greens"]:
                        cons["max_counts"][ch] = min(int(cons["max_counts"].get(ch,99)), 1); changed=True

    # dedupe lists
    _uniq_inplace(cons["must_include"]); _uniq_inplace(cons["must_exclude"])
    for i in range(5): _uniq_inplace(cons["yellows_not_here"][i])

    return changed or (before_last != sb["state"].get("_last_guess",""))
