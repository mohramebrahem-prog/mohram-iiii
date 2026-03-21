# -*- coding: utf-8 -*-
# utils.py — أدوات مساعدة: logger + encryption + helpers + config
import os, re, random, time, io, zipfile, shutil, logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
import psutil
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64

# ── إعدادات البوت ─────────────────────────────────────────────────
BOT_TOKEN      = "8207472950:AAHS9FqJzNARdhSj1iBu_y1WxzFOSe7VOZs"
API_ID         = 30301641
API_HASH       = "9a4144e4215946eb14540c659f173852"
ADMIN_IDS      = [6056642165]
ENCRYPTION_KEY = "MuharramSecureKey2024v2!#@$"

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = BASE_DIR
DATABASE_PATH = os.path.join(BASE_DIR, "data.db")
import shutil as _shutil
_src = os.path.join(BASE_DIR, "data.db")
if os.path.exists(_src) and not os.path.exists(DATABASE_PATH):
    _shutil.copy2(_src, DATABASE_PATH)
LOG_FILE      = os.path.join(BASE_DIR, "logs", "bot.log")
EXPORTS_DIR   = os.path.join(BASE_DIR, "exports")
TEMP_DIR      = os.path.join(BASE_DIR, "temp")

for _d in [DATA_DIR, os.path.join(BASE_DIR,"logs"), EXPORTS_DIR, TEMP_DIR]:
    os.makedirs(_d, exist_ok=True)

MAX_NUMBERS_PER_USER   = 10
MAX_ADS_PER_USER       = 10
MAX_FOLDERS_PER_NUMBER = 10
MAX_LINKS_PER_FOLDER   = 100
DAILY_PUBLISH_LIMIT    = 80
DAILY_JOIN_LIMIT       = 25
DEFAULT_MIN_DELAY      = 30
DEFAULT_MAX_DELAY      = 60
DEFAULT_JOIN_DELAY_MIN    = 60
DEFAULT_JOIN_DELAY_MAX    = 120
DEFAULT_BIG_BREAK_MINUTES = 10
DEFAULT_GROUPS_PER_BREAK  = 20
BROADCAST_SLEEP        = 0.08

SETTINGS = {
    "subscription_price": "10$",
    "payment_number":     "123456789",
    "whatsapp_link":      "https://wa.me/123456789",
    "mirror_token":       "",
}

# ── Logger ────────────────────────────────────────────────────────
def setup_logger(name, log_file, level=logging.INFO):
    os.makedirs(os.path.dirname(log_file) if os.path.dirname(log_file) else ".", exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(level)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    fh = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    if not logger.handlers:
        logger.addHandler(fh)
        logger.addHandler(ch)
    return logger

# ── Encryption ────────────────────────────────────────────────────
class AESCipher:
    def __init__(self, key: str):
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32,
                         salt=b"mhrm_salt_v2", iterations=100000)
        self.fernet = Fernet(base64.urlsafe_b64encode(kdf.derive(key.encode())))
    def encrypt(self, data: str) -> str:
        return self.fernet.encrypt(data.encode()).decode() if data else ""
    def decrypt(self, enc: str) -> str:
        try: return self.fernet.decrypt(enc.encode()).decode() if enc else ""
        except Exception: return ""

# ── Helpers ───────────────────────────────────────────────────────
DEVICE_MODELS   = ["Samsung Galaxy S22","Xiaomi 12 Pro","iPhone 14","OnePlus 10 Pro",
                   "Huawei P50","Google Pixel 7","Realme GT2","Oppo Find X5"]
SYSTEM_VERSIONS = ["Android 12","Android 13","Android 11","iOS 16.0","iOS 15.4","Android 14"]
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
    score = 0
    avg_delay = (join_delay_min + join_delay_max) / 2
    if avg_delay >= 120:   score += 40
    elif avg_delay >= 80:  score += 25
    elif avg_delay >= 60:  score += 15
    else:                  score += 5
    if big_break_dur >= 15:  score += 30
    elif big_break_dur >= 10: score += 20
    elif big_break_dur >= 5:  score += 10
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
        except Exception: rem = 0
    return {"numbers": nums, "subscription": sub, "remaining_days": rem,
            "posts": u["total_posts"], "joins": u["total_joins"], "fetches": u["total_fetches"]}

# ── Ad Protector ──────────────────────────────────────────────────
_BOLD_DIGITS = {
    '0': '𝟎', '1': '𝟏', '2': '𝟐', '3': '𝟑', '4': '𝟒',
    '5': '𝟓', '6': '𝟔', '7': '𝟕', '8': '𝟖', '9': '𝟗',
}
_HOMOGLYPHS = {
    'ع': ['ﻋ', 'ﻌ', 'ع'], 'ا': ['ا', 'ﺍ', 'ا'], 'و': ['و', 'ﻭ', 'و'],
    'ي': ['ي', 'ﻳ', 'ﻴ'], 'ن': ['ن', 'ﻥ', 'ﻦ'], 'م': ['م', 'ﻡ', 'ﻢ'],
    'ت': ['ت', 'ﺕ', 'ﺖ'], 'ه': ['ه', 'ﻫ', 'ﻬ'], 'ل': ['ل', 'ﻝ', 'ﻞ'],
    'ك': ['ك', 'ﻙ', 'ﻚ'], 'ر': ['ر', 'ﺭ', 'ر'], 'س': ['س', 'ﺱ', 'ﺲ'],
}
_INVISIBLES = ['\u200b', '\u200c', '\u200d', '\u2060', '\u00ad', '\ufeff', '\u034f', '\u180e']
_SENSITIVE  = ['واتساب','واتس','تواصل','اتصال','إعلان','إعلانات','عرض','عروض',
               'خصم','ارسل','أرسل','رسالة','اشتري','اطلب','طلب','مجاني','حصري']

class AdProtector:
    @staticmethod
    def ghost_numbers(text: str) -> str:
        result = []; i = 0
        while i < len(text):
            c = text[i]
            if c.isdigit():
                j = i
                while j < len(text) and text[j].isdigit(): j += 1
                num_str = text[i:j]
                if len(num_str) >= 3:
                    result.append(''.join(_BOLD_DIGITS.get(d, d) for d in num_str))
                else: result.append(num_str)
                i = j
            else: result.append(c); i += 1
        return ''.join(result)

    @staticmethod
    def fragment_words(text: str) -> str:
        for word in _SENSITIVE:
            if word in text:
                mid = len(word) // 2
                text = text.replace(word, word[:mid] + '\u200c' + word[mid:], 1)
        return text

    @staticmethod
    def apply_homoglyphs(text: str, intensity: float = 0.4) -> str:
        result = []
        for ch in text:
            if ch in _HOMOGLYPHS and random.random() < intensity:
                result.append(random.choice(_HOMOGLYPHS[ch]))
            else: result.append(ch)
        return ''.join(result)

    @staticmethod
    def inject_invisibles(text: str, rate: float = 0.08) -> str:
        result = []
        for ch in text:
            result.append(ch)
            if ch == ' ' and random.random() < rate:
                result.append(random.choice(_INVISIBLES[:4]))
        return ''.join(result)

    @classmethod
    def protect(cls, text: str, level: int = 2) -> str:
        # كل رسالة hash مختلف لتجنب اكتشافها
        invisible_count = random.randint(3, 12)
        text_end = text + ''.join(random.choices(_INVISIBLES, k=invisible_count))
        if level >= 1:
            text_end = cls.fragment_words(text_end)
        if level >= 2:
            text_end = cls.ghost_numbers(text_end)
        if level >= 3:
            text_end = cls.apply_homoglyphs(text_end, intensity=random.uniform(0.2, 0.6))
            text_end = cls.inject_invisibles(text_end)
        return text_end

    @classmethod
    def generate_variants(cls, text: str, count: int = 5, level: int = 2) -> list:
        return [cls.protect(text, level) for _ in range(count)]
