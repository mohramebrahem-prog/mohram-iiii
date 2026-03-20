# -*- coding: utf-8 -*-
import re, random, time, os, io, zipfile, shutil
from datetime import datetime
import psutil

DEVICE_MODELS   = ["Samsung Galaxy S22","Xiaomi 12 Pro","iPhone 14","OnePlus 10 Pro",
                   "Huawei P50","Google Pixel 7","Realme GT2","Oppo Find X5"]
SYSTEM_VERSIONS = ["Android 12","Android 13","Android 11","iOS 16.0","iOS 15.4",
                   "Android 14","iOS 17.0"]
APP_VERSIONS    = ["9.3.3","9.4.0","9.2.1","9.5.0","9.1.0"]

def random_device():
    return random.choice(DEVICE_MODELS), random.choice(SYSTEM_VERSIONS), random.choice(APP_VERSIONS)

TG_RE = re.compile(
    r"https?://t\.me/(?:[a-zA-Z0-9_]{3,}|joinchat/[a-zA-Z0-9_\-]+|\+[a-zA-Z0-9_\-]+|addlist/[a-zA-Z0-9_\-]+)"
)
WA_RE = re.compile(r"https?://chat\.whatsapp\.com/[\w\d\-_]{10,}")

def extract_telegram_links(text): return list(set(TG_RE.findall(text or "")))
def extract_whatsapp_links(text):  return list(set(WA_RE.findall(text or "")))
def clean_phone_code(code: str):   return code.replace(" ", "").replace("-", "")

def progress_bar(current, total, length=12):
    if total == 0: return "▱" * length
    filled = min(int(current / total * length), length)
    return "▰" * filled + "▱" * (length - filled)

def pct(current, total):
    return f"{int(current/total*100)}%" if total else "0%"

def health_icon(h):
    if h >= 80: return "🟢"
    if h >= 50: return "🟡"
    return "🔴"

def status_dot(active, busy=False):
    if busy:   return "🔵"
    if active: return "🟢"
    return "🔴"

def calc_eta(done, total, start_ts):
    if done == 0: return "—"
    elapsed   = time.time() - start_ts
    remaining = (elapsed / done) * (total - done)
    if remaining < 60:   return f"{int(remaining)}ث"
    if remaining < 3600: return f"{int(remaining//60)}د"
    return f"{int(remaining//3600)}س"

def get_server_stats():
    cpu  = psutil.cpu_percent(interval=0.5)
    mem  = psutil.virtual_memory()
    disk = shutil.disk_usage("/")
    return {"cpu": cpu, "mem_pct": mem.percent,
            "mem_used": mem.used, "mem_total": mem.total,
            "disk_used": disk.used, "disk_total": disk.total,
            "disk_pct": disk.used / disk.total * 100}

def fmt_size(b):
    for u in ["B","KB","MB","GB"]:
        if b < 1024: return f"{b:.1f}{u}"
        b /= 1024
    return f"{b:.1f}TB"

def create_db_backup(db_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(db_path, "data.db")
    buf.seek(0)
    return buf.read()

def parse_proxy(s):
    if not s: return None
    try:
        if s.startswith("socks5://"):
            rest = s[9:]
            user = pwd = None
            if "@" in rest:
                auth, rest = rest.split("@", 1)
                user, pwd  = auth.split(":", 1)
            host, port = rest.rsplit(":", 1)
            return {"proxy_type":"socks5","addr":host,"port":int(port),
                    "username":user,"password":pwd,"rdns":True}
    except Exception:
        pass
    return None

def safety_score(join_delay_min, join_delay_max, big_break_dur, groups_per_break):
    """حساب نسبة الأمان بناءً على الإعدادات"""
    score = 0
    # تقييم الفاصل الزمني
    avg_delay = (join_delay_min + join_delay_max) / 2
    if avg_delay >= 120:   score += 40
    elif avg_delay >= 80:  score += 25
    elif avg_delay >= 60:  score += 15
    else:                  score += 5
    # تقييم مدة الاستراحة
    if big_break_dur >= 15:  score += 30
    elif big_break_dur >= 10: score += 20
    elif big_break_dur >= 5:  score += 10
    # تقييم عدد المجموعات قبل الاستراحة
    if groups_per_break <= 10:  score += 30
    elif groups_per_break <= 20: score += 20
    elif groups_per_break <= 30: score += 10
    return min(100, score)

def safety_icon(score):
    if score >= 70: return "🟢"
    if score >= 40: return "🟡"
    return "🔴"


def dashboard_stats(user_id, db):
    u = db.fetch_one(
        "SELECT subscription_end, total_posts, total_joins, total_fetches FROM users WHERE user_id=?",
        (user_id,))
    if not u: return None
    nums = (db.fetch_one("SELECT COUNT(*) as c FROM numbers WHERE user_id=?", (user_id,)) or {}).get("c", 0)
    sub  = u["subscription_end"] or "غير مشترك"
    rem  = 0
    if u["subscription_end"]:
        try:
            rem = max(0, (datetime.strptime(u["subscription_end"], "%Y-%m-%d") - datetime.now()).days)
        except Exception:
            rem = 0
    return {"numbers": nums, "subscription": sub, "remaining_days": rem,
            "posts": u["total_posts"], "joins": u["total_joins"], "fetches": u["total_fetches"]}
