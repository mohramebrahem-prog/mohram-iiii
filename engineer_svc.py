# -*- coding: utf-8 -*-
"""
خدمة المهندس الذكي v3 — Reverse Engineering System
الجديد: تحليل MessageEntities + Blueprint بدل Scraping
"""
import asyncio, logging, hashlib, json as _json, random
from telethon import TelegramClient
from telethon.sessions import StringSession

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════
#  Blueprint Engine — استخراج وتطبيق هيكل التنسيق
# ══════════════════════════════════════════════════════════════════

def build_blueprint(text: str, entities: list) -> dict:
    """
    يأخذ نص الرسالة + قائمة MessageEntity
    ويُنتج blueprint: قائمة segments قابلة لإعادة الاستخدام.

    أنواع segments:
      plain         — نص عادي يُحفظ كما هو
      user_text     — placeholder: {USER_TEXT}  ← أول block نصي كبير
      user_link     — placeholder: {USER_LINK}  ← أول text_link أو url
      user_number   — placeholder: {USER_NUMBER}← phone_number entity
      bold/italic/spoiler/code/pre  — نص مُنسَّق يُحفظ نصه
      url_entity    — رابط نصي عادي (ليس text_link)
    """
    if not entities:
        # لا تنسيق → الكل user_text
        return {"version": 3,
                "segments": [{"k": "user_text"}],
                "original_text": text}

    ents = sorted(entities, key=lambda e: e.offset)
    segs = []
    prev = 0
    link_done   = False
    number_done = False

    for e in ents:
        # نص عادي قبل هذا entity
        if e.offset > prev:
            chunk = text[prev:e.offset]
            segs.append({"k": "plain", "t": chunk})

        elen  = e.length
        chunk = text[e.offset: e.offset + elen]
        etype = e.type.value if hasattr(e.type, "value") else str(e.type)

        if etype == "text_link" and not link_done:
            segs.append({"k": "user_link",
                         "display": chunk,
                         "url_fallback": getattr(e, "url", "")})
            link_done = True
        elif etype == "url" and not link_done:
            segs.append({"k": "user_link",
                         "display": chunk,
                         "url_fallback": chunk})
            link_done = True
        elif etype == "phone_number" and not number_done:
            segs.append({"k": "user_number", "original": chunk})
            number_done = True
        elif etype == "bold":
            segs.append({"k": "bold", "t": chunk})
        elif etype == "italic":
            segs.append({"k": "italic", "t": chunk})
        elif etype == "spoiler":
            segs.append({"k": "spoiler", "t": chunk})
        elif etype == "code":
            segs.append({"k": "code", "t": chunk})
        elif etype == "pre":
            segs.append({"k": "pre", "t": chunk,
                         "lang": getattr(e, "language", "") or ""})
        else:
            # entity آخر → احتفظ بالنص
            segs.append({"k": "plain", "t": chunk})

        prev = e.offset + elen

    # ما تبقى
    if prev < len(text):
        segs.append({"k": "plain", "t": text[prev:]})

    # إذا لم يوجد user_text placeholder → أضفه في البداية
    has_ut = any(s["k"] == "user_text" for s in segs)
    if not has_ut:
        segs.insert(0, {"k": "user_text"})
        segs.insert(1, {"k": "plain", "t": "\n"})

    return {"version": 3, "segments": segs, "original_text": text}


def apply_blueprint(blueprint: dict,
                    user_text: str,
                    user_link: str = "",
                    user_number: str = "") -> tuple:
    """
    يدمج بيانات المستخدم في blueprint.
    يُرجع (final_text: str, entities: list[MessageEntity] | None)
    entities تكون None إذا لم يكن هناك تنسيق.

    مهم: لا نستخدم parse_mode — نُرسل entities مباشرة لـ Bot API
    لتجنب ParseError كلياً.
    """
    from telegram import MessageEntity

    segs = blueprint.get("segments", [])
    if not segs:
        return user_text, None

    parts    = []   # أجزاء النص
    ents_out = []   # MessageEntity للإرسال

    ENTITY_TYPE_MAP = {
        "bold":    MessageEntity.BOLD,
        "italic":  MessageEntity.ITALIC,
        "spoiler": MessageEntity.SPOILER,
        "code":    MessageEntity.CODE,
        "pre":     MessageEntity.PRE,
    }

    for seg in segs:
        k = seg["k"]
        start = sum(len(p) for p in parts)

        if k == "user_text":
            parts.append(user_text)

        elif k == "user_link":
            display = user_link or seg.get("display", "")
            url     = user_link if user_link.startswith("http") else seg.get("url_fallback", user_link)
            if not url:
                url = display
            parts.append(display)
            if url:
                try:
                    ents_out.append(MessageEntity(
                        type=MessageEntity.TEXT_LINK,
                        offset=start,
                        length=len(display),
                        url=url))
                except Exception:
                    pass

        elif k == "user_number":
            num = user_number or seg.get("original", "")
            parts.append(num)

        elif k in ENTITY_TYPE_MAP:
            txt = seg.get("t", "")
            parts.append(txt)
            try:
                kw = {"type": ENTITY_TYPE_MAP[k],
                      "offset": start,
                      "length": len(txt)}
                if k == "pre":
                    kw["language"] = seg.get("lang", "")
                ents_out.append(MessageEntity(**kw))
            except Exception:
                pass

        elif k == "plain":
            parts.append(seg.get("t", ""))

    final = "".join(parts)
    return final, (ents_out if ents_out else None)


# ══════════════════════════════════════════════════════════════════
#  EngineerService
# ══════════════════════════════════════════════════════════════════
class EngineerService:
    def __init__(self, db, api_id, api_hash):
        self.db         = db
        self.api_id     = api_id
        self.api_hash   = api_hash
        self._spy_tasks = {}
        self._monitors  = {}
        self.bot        = None

    # ── إعدادات ────────────────────────────────────────────────────
    def get_snipe_timeout(self) -> int:
        r = self.db.fetch_one(
            "SELECT value FROM engineer_settings WHERE key='snipe_timeout'")
        return int(r["value"]) if r else 15

    def get_active_target_bots(self):
        return self.db.fetch_all("SELECT * FROM monitored_bots WHERE is_active=1")

    def get_approved_templates(self):
        return self.db.fetch_all(
            "SELECT * FROM captured_templates WHERE status='approved'"
            " ORDER BY created_at DESC")

    def get_best_template(self):
        return self.db.fetch_one(
            "SELECT * FROM captured_templates WHERE status='approved'"
            " ORDER BY created_at DESC LIMIT 1")

    def get_zws_chars(self) -> list:
        r = self.db.fetch_one(
            "SELECT value FROM engineer_settings WHERE key='zws_chars'")
        if r and r["value"]:
            return r["value"].split(",")
        return ['\u200b', '\u200c', '\u200d', '\u2060']

    # ── تأكد من وجود عمود blueprint ──────────────────────────────
    def _ensure_blueprint_col(self):
        try:
            self.db.execute(
                "ALTER TABLE captured_templates ADD COLUMN blueprint TEXT DEFAULT ''")
        except Exception:
            pass

    # ── منع التكرار ────────────────────────────────────────────────
    def _hash(self, text: str) -> str:
        import hashlib
        return hashlib.md5(text.strip().encode()).hexdigest()

    def is_duplicate_template(self, content: str) -> bool:
        h = self._hash(content)
        return bool(self.db.fetch_one(
            "SELECT id FROM captured_templates WHERE content_hash=?", (h,)))

    # ── إضافة قالب ────────────────────────────────────────────────
    def add_template(self, name: str, content: str,
                     target_bot: str = "", source_group: str = "",
                     notify_admin: bool = True,
                     blueprint_json: str = "") -> dict:
        """إضافة قالب جديد. blueprint_json اختياري."""
        if self.is_duplicate_template(content):
            return {"status": "duplicate"}
        self._ensure_blueprint_col()
        h = self._hash(content)
        self.db.execute(
            "INSERT INTO captured_templates"
            "(template_name,content,target_bot,source_group,status,content_hash,blueprint)"
            " VALUES(?,?,?,?,'pending',?,?)",
            (name, content, target_bot, source_group, h, blueprint_json))
        row = self.db.fetch_one(
            "SELECT id FROM captured_templates ORDER BY id DESC LIMIT 1")
        return {"status": "added",
                "id": (row["id"] if row else None),
                "notify": notify_admin}

    # ── تحديث blueprint لقالب موجود ──────────────────────────────
    def save_blueprint(self, tpl_id: int, blueprint: dict):
        self._ensure_blueprint_col()
        self.db.execute(
            "UPDATE captured_templates SET blueprint=? WHERE id=?",
            (_json.dumps(blueprint, ensure_ascii=False), tpl_id))

    # ── دمج نص مع قالب ────────────────────────────────────────────
    def merge_with_template(self, user_text: str, template_content: str) -> str:
        """Fallback نصي بدون entities."""
        zws = self.get_zws_chars()
        out = []
        for i, ch in enumerate(user_text):
            out.append(ch)
            if ch == ' ' and i % 4 == 0 and zws:
                out.append(zws[i % len(zws)])
        protected = "".join(out)
        if "{{AD_TEXT}}" in template_content:
            return template_content.replace("{{AD_TEXT}}", protected)
        return f"{protected}\n\n{template_content}"

    def apply_manual_encryption(self, text: str) -> str:
        """تشفير ZWS بسيط."""
        try:
            from utils import AdProtector
            text = AdProtector.protect(text, level=2)
        except Exception:
            pass
        zws = self.get_zws_chars()
        if zws:
            text += "".join(random.choices(zws, k=6))
        return text

    # ── render قالب ذكي مع بيانات المستخدم ──────────────────────
    def render_smart_template(self, tpl_row: dict,
                               user_text: str,
                               user_link: str = "",
                               user_number: str = "") -> tuple:
        """
        يُرجع (final_text, entities_or_None).
        يستخدم blueprint إن وُجد، وإلا fallback نصي.
        """
        bp_json = tpl_row.get("blueprint") or ""
        if bp_json:
            try:
                bp = _json.loads(bp_json)
                if bp.get("version") == 3:
                    return apply_blueprint(bp, user_text, user_link, user_number)
            except Exception as e:
                logger.debug(f"render_smart_template bp error: {e}")
        # fallback
        return self.merge_with_template(user_text,
                                        tpl_row.get("content", "")), None

    # ── Telethon helpers (لـ estimate فقط) ──────────────────────
    async def find_group_with_bot(self, user_id: int, bot_username: str):
        numbers = self.db.get_user_numbers(user_id)
        bot_username = bot_username.lstrip("@").lower()
        for num in numbers:
            if not num.get("is_active") or not num.get("session_string"):
                continue
            try:
                c = TelegramClient(StringSession(num["session_string"]),
                                   self.api_id, self.api_hash)
                await c.connect()
                if not await c.is_user_authorized():
                    await c.disconnect(); continue
                for d in await c.get_dialogs(limit=200):
                    if not (hasattr(d.entity, "megagroup") or
                            hasattr(d.entity, "gigagroup")):
                        continue
                    try:
                        for m in await c.get_participants(d.entity, limit=50):
                            if m.username and m.username.lower() == bot_username:
                                await c.disconnect()
                                return {"found": True,
                                        "group_title": getattr(d.entity, "title", ""),
                                        "group_id": d.entity.id,
                                        "number_id": num["id"],
                                        "session_string": num["session_string"]}
                    except Exception:
                        pass
                await c.disconnect()
            except Exception as e:
                logger.debug(f"find_group_with_bot: {e}")
        return None

    async def estimate_bot_presence(self, bot_username: str) -> int:
        users = self.db.fetch_all(
            "SELECT DISTINCT user_id FROM numbers WHERE is_active=1")
        count = 0
        for u in users[:20]:
            try:
                if await self.find_group_with_bot(u["user_id"], bot_username):
                    count += 1
            except Exception:
                pass
        return count

    # ── إشعار الآدمن ──────────────────────────────────────────────
    async def notify_admin_new_template(self, tpl_id: int, admin_ids: list):
        if not self.bot: return
        tpl = self.db.fetch_one(
            "SELECT * FROM captured_templates WHERE id=?", (tpl_id,))
        if not tpl: return
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        preview = (tpl.get("content") or "")[:200]
        text = (f"🔔 **قالب جديد!**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📛 الاسم: `{tpl.get('template_name','—')}`\n"
                f"🤖 البوت: `{tpl.get('target_bot','—')}`\n\n"
                f"📝 معاينة:\n`{preview}`")
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ اعتماد",
                                 callback_data=f"eng_approve_tpl_{tpl_id}"),
            InlineKeyboardButton("🗑️ حذف",
                                 callback_data=f"eng_del_tpl_{tpl_id}")
        ]])
        for aid in admin_ids:
            try:
                await self.bot.send_message(
                    aid, text, parse_mode="Markdown", reply_markup=kb)
            except Exception as e:
                logger.debug(f"notify_admin: {e}")
