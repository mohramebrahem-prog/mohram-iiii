# -*- coding: utf-8 -*-
"""
معالج مفاتيح تحكم الآدمن + نظام Auto-Resume
الإصلاح v3: edit_message_reply_markup فوري + MessageNotModified catch
"""
import asyncio, logging, json
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import BadRequest

logger = logging.getLogger(__name__)

def btn(text, cb): return InlineKeyboardButton(text, callback_data=cb)
def back(cb):      return InlineKeyboardMarkup([[btn("🔙 رجوع", cb)]])

FEATURE_KEYS = {
    "publish":    "🚀 محرك النشر",
    "folder":     "📁 نظام المجلدات",
    "fetch":      "🔍 جلب الروابط",
    "engineer":   "🛡️ نظام المهندس",
    "videos":     "📹 الفيديوهات",
    "auto_reply": "💬 الرد التلقائي",
}


class ControlHandler:
    def __init__(self, db, admin_ids):
        self.db        = db
        self.admin_ids = admin_ids
        self._ensure_tables()

    def _ensure_tables(self):
        self.db.execute("""CREATE TABLE IF NOT EXISTS feature_flags (
            key TEXT PRIMARY KEY,
            is_enabled INTEGER DEFAULT 1,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        for col, defn in [("is_enabled", "INTEGER DEFAULT 1"),
                          ("updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")]:
            try:
                self.db.execute(f"ALTER TABLE feature_flags ADD COLUMN {col} {defn}")
            except Exception:
                pass
        self.db.execute("""CREATE TABLE IF NOT EXISTS resume_state (
            id TEXT PRIMARY KEY,
            user_id INTEGER,
            operation TEXT,
            state_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        for col, defn in [("state_json", "TEXT"),
                          ("updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")]:
            try:
                self.db.execute(f"ALTER TABLE resume_state ADD COLUMN {col} {defn}")
            except Exception:
                pass
        for key in FEATURE_KEYS:
            self.db.execute(
                "INSERT OR IGNORE INTO feature_flags(key,is_enabled) VALUES(?,1)",
                (key,))

    async def safe_edit(self, q, text, kb=None, pm=ParseMode.MARKDOWN):
        try:
            kw = {"parse_mode": pm}
            if kb: kw["reply_markup"] = kb
            await q.edit_message_text(text, **kw)
        except Exception as e:
            if "not modified" not in str(e).lower():
                logger.debug(f"safe_edit: {e}")

    async def safe_ans(self, q, text="", alert=False):
        try: await q.answer(text, show_alert=alert)
        except Exception: pass

    def _is_admin(self, uid): return uid in self.admin_ids

    # ── قراءة حالة ميزة (fresh من DB) ────────────────────────────
    def is_feature_enabled(self, key: str) -> bool:
        try:
            r = self.db.fetch_one(
                "SELECT is_enabled FROM feature_flags WHERE key=?", (key,))
            return bool((r or {}).get("is_enabled", 1))
        except Exception:
            return True

    def toggle_feature(self, key: str) -> bool:
        """يبدّل الحالة ويُرجع الحالة الجديدة مباشرة من DB."""
        try:
            current = self.is_feature_enabled(key)
            new_val = 0 if current else 1
            self.db.execute(
                "INSERT OR REPLACE INTO feature_flags(key,is_enabled,updated_at)"
                " VALUES(?,?,CURRENT_TIMESTAMP)",
                (key, new_val))
            # Fresh read للتأكد من الحفظ
            fresh = self.db.fetch_one(
                "SELECT is_enabled FROM feature_flags WHERE key=?", (key,))
            return bool((fresh or {}).get("is_enabled", new_val))
        except Exception as e:
            logger.error(f"toggle_feature [{key}]: {e}")
            return True

    # ── بناء لوحة المفاتيح بحالات Fresh ──────────────────────────
    def _build_ctrl_keyboard(self) -> InlineKeyboardMarkup:
        btns = []
        for key, label in FEATURE_KEYS.items():
            enabled = self.is_feature_enabled(key)
            icon    = "🟢" if enabled else "🔴"
            action  = "إيقاف" if enabled else "تشغيل"
            btns.append([btn(f"{icon} {label} — اضغط للـ{action}",
                             f"ctrl_toggle_{key}")])
        btns.append([btn("🔄 Auto-Resume — عرض الحالة", "ctrl_resume_status")])
        btns.append([btn("🔙 رجوع", "admin_panel")])
        return InlineKeyboardMarkup(btns)

    # ── Auto-Resume ───────────────────────────────────────────────
    def save_resume_state(self, state_id: str, user_id: int,
                          operation: str, state_data: dict):
        self.db.execute(
            "INSERT OR REPLACE INTO resume_state"
            "(id,user_id,operation,state_json,updated_at) VALUES(?,?,?,?,CURRENT_TIMESTAMP)",
            (state_id, user_id, operation,
             json.dumps(state_data, ensure_ascii=False)))

    def load_resume_state(self, state_id: str) -> dict | None:
        r = self.db.fetch_one(
            "SELECT * FROM resume_state WHERE id=?", (state_id,))
        if not r: return None
        try:   r["state_data"] = json.loads(r["state_json"])
        except Exception: r["state_data"] = {}
        return r

    def delete_resume_state(self, state_id: str):
        self.db.execute("DELETE FROM resume_state WHERE id=?", (state_id,))

    def get_pending_resumes(self, user_id: int) -> list:
        rows = self.db.fetch_all(
            "SELECT * FROM resume_state WHERE user_id=? ORDER BY updated_at DESC",
            (user_id,))
        for r in rows:
            try: r["state_data"] = json.loads(r.get("state_json", "{}"))
            except Exception: r["state_data"] = {}
        return rows

    # ══ لوحة التحكم ═══════════════════════════════════════════════

    async def admin_control_panel(self, update, ctx):
        if not self._is_admin(update.effective_user.id):
            await self.safe_ans(update.callback_query, "❌"); return
        kb = self._build_ctrl_keyboard()
        await self.safe_edit(update.callback_query,
            "🎛️ **مفاتيح تحكم الأنظمة**\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "🟢 = مُشغَّل | 🔴 = موقوف\n"
            "اضغط على أي نظام لتغيير حالته فوراً:",
            kb)

    async def ctrl_toggle(self, update, ctx, key: str):
        """
        يبدّل الحالة ويُحدّث الكيبورد فوراً بـ edit_message_reply_markup.
        لا يحتاج إلى إعادة إرسال الرسالة كاملة.
        """
        if not self._is_admin(update.effective_user.id): return
        q = update.callback_query
        if key not in FEATURE_KEYS:
            await self.safe_ans(q, "❌ مفتاح غير معروف", True); return

        try:
            # 1) تبديل الحالة في DB
            new_state = self.toggle_feature(key)

            # 2) بناء كيبورد جديد بحالات Fresh
            new_kb = self._build_ctrl_keyboard()

            # 3) تحديث الكيبورد فوراً بدون إعادة إرسال النص
            try:
                await q.edit_message_reply_markup(reply_markup=new_kb)
            except BadRequest as e:
                if "message is not modified" not in str(e).lower():
                    # fallback: تحديث الرسالة كاملة
                    await self.admin_control_panel(update, ctx)

            # 4) إشعار بالحالة الجديدة
            label  = FEATURE_KEYS[key]
            status = "🟢 مُشغَّل" if new_state else "🔴 موقوف"
            await self.safe_ans(q, f"{label}: {status}")

        except Exception as e:
            logger.error(f"ctrl_toggle [{key}]: {e}")
            await self.safe_ans(q, "⚠️ حدث خطأ، حاول مجدداً", True)

    async def ctrl_resume_status(self, update, ctx):
        if not self._is_admin(update.effective_user.id): return
        rows = self.db.fetch_all(
            "SELECT user_id, operation, updated_at FROM resume_state"
            " ORDER BY updated_at DESC LIMIT 20")
        text = "🔄 **حالة Auto-Resume:**\n━━━━━━━━━━━━━━━━━━━━━━\n"
        if rows:
            for r in rows:
                text += f"👤 `{r['user_id']}` — {r['operation']} — {(r['updated_at'] or '')[:16]}\n"
        else:
            text += "✅ لا توجد عمليات معلقة."
        await self.safe_edit(update.callback_query, text, back("ctrl_panel"))
