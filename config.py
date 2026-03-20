# -*- coding: utf-8 -*-
"""
إعدادات البوت المركزية — Muharram Bot v4.0
جميع الإعدادات في مكان واحد
"""
import os

# ══════════════════════════════════════════════════════════════
#  بيانات البوت — غيّرها بعد نسخ المشروع
# ══════════════════════════════════════════════════════════════
BOT_TOKEN      = "8207472950:AAHS9FqJzNARdhSj1iBu_y1WxzFOSe7VOZs"
API_ID         = 0          # من my.telegram.org
API_HASH       = "YOUR_API_HASH_HERE"
ADMIN_IDS      = [6056642165]  # قائمة IDs الأدمن
ENCRYPTION_KEY = "MuharramSecureKey2024v2!#@$"  # غيّر هذا!

# ══════════════════════════════════════════════════════════════
#  مسارات الملفات
# ══════════════════════════════════════════════════════════════
BASE_DIR      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR      = "/root/data/muharram"
DATABASE_PATH = os.path.join(DATA_DIR, "data.db")
LOG_FILE      = os.path.join(BASE_DIR, "logs", "bot.log")
EXPORTS_DIR   = os.path.join(BASE_DIR, "exports")
TEMP_DIR      = os.path.join(BASE_DIR, "temp")

for _d in [DATA_DIR, os.path.join(BASE_DIR, "logs"), EXPORTS_DIR, TEMP_DIR]:
    os.makedirs(_d, exist_ok=True)

# ══════════════════════════════════════════════════════════════
#  حدود النظام
# ══════════════════════════════════════════════════════════════
MAX_NUMBERS_PER_USER   = 10
MAX_ADS_PER_USER       = 10
MAX_FOLDERS_PER_NUMBER = 10
MAX_LINKS_PER_FOLDER   = 100

# ══════════════════════════════════════════════════════════════
#  حدود الأمان اليومية — لحماية الأرقام من الحظر
# ══════════════════════════════════════════════════════════════
DAILY_PUBLISH_LIMIT = 80   # رسائل/يوم/رقم
DAILY_JOIN_LIMIT    = 25   # انضمام/يوم/رقم

# ══════════════════════════════════════════════════════════════
#  إعدادات النشر الافتراضية
# ══════════════════════════════════════════════════════════════
DEFAULT_MIN_DELAY = 30
DEFAULT_MAX_DELAY = 60

# ══════════════════════════════════════════════════════════════
#  إعدادات المجلدات الافتراضية
# ══════════════════════════════════════════════════════════════
DEFAULT_JOIN_DELAY_MIN    = 60
DEFAULT_JOIN_DELAY_MAX    = 120
DEFAULT_BIG_BREAK_MINUTES = 10
DEFAULT_GROUPS_PER_BREAK  = 20

# ══════════════════════════════════════════════════════════════
#  إعدادات الإذاعة
# ══════════════════════════════════════════════════════════════
BROADCAST_SLEEP = 0.08

# ══════════════════════════════════════════════════════════════
#  إعدادات ديناميكية (تتغير من لوحة الأدمن)
# ══════════════════════════════════════════════════════════════
SETTINGS = {
    "subscription_price": "10$",
    "payment_number":     "123456789",
    "whatsapp_link":      "https://wa.me/123456789",
    "mirror_token":       "",
}
