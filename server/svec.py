# SVEC_V1
import re
from datetime import datetime

def build_svec(user_text: str, model: str) -> dict:
    t = user_text or ""
    has_url = 1 if re.search(r"https?://", t) else 0
    has_code = 1 if ("```" in t or re.search(r"[;{}<>]", t)) else 0
    length = len(t)
    hour = datetime.now().hour
    return {"len": length, "has_url": has_url, "has_code": has_code, "hour": hour, "model": model}

def bucketize_svec(s: dict) -> str:
    def bin_len(n):
        if n <= 20: return "s"
        if n <= 120: return "m"
        return "l"
    def bin_hour(h):
        if 0 <= h < 6: return "n"     # night
        if 6 <= h < 12: return "m"    # morning
        if 12 <= h < 18: return "a"   # afternoon
        return "e"                    # evening
    return f"L{bin_len(s['len'])}_U{s['has_url']}_C{s['has_code']}_H{bin_hour(s['hour'])}_M{s.get('model','')}"
