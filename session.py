# -*- coding: utf-8 -*-
"""
مدير الجلسات والأكواد المتطور
- تسجيل خروج المشترك مع توليد كود دخول للحساب الآخر
- حذف كود مشترك مع Logout قسري
"""
import asyncio, logging, random, string
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

logger = logging.getLogger(__name__)

def btn(text, cb): return InlineKeyboardButton(text, callback_data=cb)
def back(cb):      return InlineKeyboardMarkup([[btn("🔙 رجوع", cb)]])


class SessionManager:
    def __init__(self, db, admin_ids):
        self.db        = db
        self.admin_ids = admin_ids
        self._ensure_table()

    def _ensure_table(self):
        self.db.execute("""CREATE TABLE IF NOT EXISTS transfer_codes (
            code TEXT PRIMARY KEY,
            user_id INTEGER,
            remaining_days REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,
            used INTEGER DEFAULT 0
        )""")

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

    def _gen_transfer_code(self) -> str:
        return "TR-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))

    # ── تسجيل خروج المشترك (مع كود نقل) ────────────────────────

    async def user_logout_prompt(self, update, ctx):
        """عرض تأكيد الخروج"""
        uid = update.effective_user.id
        u   = self.db.fetch_one("SELECT subscription_end FROM users WHERE user_id=?", (uid,))
        if not u or not u.get("subscription_end"):
            await self.safe_edit(update.callback_query,
                "⚠️ لا يوجد اشتراك نشط.",
                back("main_menu")); return
        try:
            rem = max(0, (datetime.strptime(u["subscription_end"], "%Y-%m-%d")
                         - datetime.now()).days)
        except Exception:
            rem = 0
        kb = InlineKeyboardMarkup([
            [btn("✅ تأكيد الخروج وتوليد كود النقل", "sm_confirm_logout")],
            [btn("❌ إلغاء", "main_menu")]
        ])
        await self.safe_edit(update.callback_query,
            f"🚪 **تسجيل الخروج**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⏳ المتبقي من اشتراكك: **{rem} يوم**\n\n"
            f"سيتم توليد **كود نقل** يتيح لك الدخول من حساب/جهاز آخر.\n"
            f"⚠️ سيُحذف وصولك الحالي فوراً.", kb)

    async def user_confirm_logout(self, update, ctx):
        """تنفيذ الخروج وتوليد كود النقل"""
        uid = update.effective_user.id
        u   = self.db.fetch_one("SELECT subscription_end FROM users WHERE user_id=?", (uid,))
        try:
            rem = max(0, (datetime.strptime(u["subscription_end"], "%Y-%m-%d")
                         - datetime.now()).days) if u and u.get("subscription_end") else 0
        except Exception:
            rem = 0
        code    = self._gen_transfer_code()
        expires = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        self.db.execute(
            "INSERT INTO transfer_codes(code,user_id,remaining_days,expires_at) VALUES(?,?,?,?)",
            (code, uid, rem, expires))
        # إيقاف الاشتراك الحالي
        self.db.execute(
            "UPDATE users SET subscription_end=date('now','-1 day') WHERE user_id=?", (uid,))
        await self.safe_edit(update.callback_query,
            f"✅ **تم تسجيل الخروج**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎫 **كود النقل:**\n`{code}`\n\n"
            f"⏳ المدة المحفوظة: **{rem} يوم**\n"
            f"📅 صالح حتى: `{expires[:10]}`\n\n"
            f"💡 استخدم هذا الكود على أي حساب للدخول بنفس المدة.",
            InlineKeyboardMarkup([]))

    async def user_use_transfer_code(self, update, ctx, code: str):
        """استخدام كود النقل على حساب آخر"""
        uid = update.effective_user.id
        r   = self.db.fetch_one(
            "SELECT * FROM transfer_codes WHERE code=? AND used=0", (code,))
        if not r:
            await update.message.reply_text("❌ الكود غير صالح أو مستخدم."); return
        try:
            exp = datetime.strptime(r["expires_at"], "%Y-%m-%d %H:%M:%S")
            if datetime.now() > exp:
                await update.message.reply_text("❌ انتهت صلاحية الكود."); return
        except Exception:
            pass
        days = r.get("remaining_days", 0)
        u    = self.db.fetch_one("SELECT subscription_end FROM users WHERE user_id=?", (uid,))
        try:
            base = datetime.strptime(u["subscription_end"], "%Y-%m-%d") \
                   if (u and u.get("subscription_end")) else datetime.now()
        except Exception:
            base = datetime.now()
        new_end = base + timedelta(days=float(days))
        self.db.execute("UPDATE users SET subscription_end=? WHERE user_id=?",
                        (new_end.strftime("%Y-%m-%d"), uid))
        self.db.execute("UPDATE transfer_codes SET used=1 WHERE code=?", (code,))
        await update.message.reply_text(
            f"✅ **تم تفعيل كود النقل!**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⏳ تم إضافة **{days:.0f} يوم** لاشتراكك\n"
            f"📅 ينتهي: `{new_end.strftime('%Y-%m-%d')}`",
            parse_mode=ParseMode.MARKDOWN)

    # ── حذف كود مشترك (آدمن) ─────────────────────────────────────

    async def admin_revoke_code_menu(self, update, ctx):
        """قائمة الأكواد النشطة مع تفاصيل كل كود"""
        if not self._is_admin(update.effective_user.id): return
        rows = self.db.fetch_all("""
            SELECT sc.code, sc.days, sc.used_at, sc.used_by,
                   u.first_name, u.username, u.subscription_end
            FROM subscription_codes sc
            JOIN users u ON sc.used_by = u.user_id
            WHERE sc.used_by IS NOT NULL
              AND u.subscription_end >= date('now')
            ORDER BY u.subscription_end DESC
            LIMIT 30
        """)
        if not rows:
            await self.safe_edit(update.callback_query,
                "📭 لا توجد أكواد نشطة حالياً.",
                back("admin_manage_codes")); return
        text = ("🔑 **الأكواد النشطة حالياً:**\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n")
        btns = []
        now  = datetime.now()
        for r in rows:
            try:
                rem = max(0, (datetime.strptime(r["subscription_end"], "%Y-%m-%d") - now).days)
            except Exception:
                rem = 0
            name = r.get("first_name") or f"user_{r['used_by']}"
            uname = f"@{r['username']}" if r.get("username") else ""
            lbl   = f"{int(r['days']*24)}ساعة" if (r["days"] or 0) < 1 else f"{int(r['days'] or 0)}يوم"
            text += (f"👤 {name} {uname}\n"
                     f"   🎫 `{r['code']}` — {lbl} — متبقي: {rem} يوم\n\n")
            btns.append([btn(
                f"🚫 حذف: {r['code']} — {name}",
                f"sm_revoke_confirm_{r['used_by']}_{r['code']}")])
        btns.append([btn("🔙 رجوع", "admin_manage_codes")])
        # تقليص النص إذا طال
        if len(text) > 3800:
            text = text[:3700] + "\n..."
        await self.safe_edit(update.callback_query, text, InlineKeyboardMarkup(btns))

    async def admin_revoke_confirm(self, update, ctx, uid: int, code: str):
        """تأكيد حذف الكود"""
        if not self._is_admin(update.effective_user.id): return
        u = self.db.fetch_one("SELECT first_name, subscription_end FROM users WHERE user_id=?", (uid,))
        name = (u or {}).get("first_name", str(uid))
        sub  = (u or {}).get("subscription_end", "—")
        kb = InlineKeyboardMarkup([
            [btn("✅ نعم — حذف الكود و Logout فوري",
                 f"sm_revoke_execute_{uid}_{code}")],
            [btn("❌ إلغاء", "sm_revoke_menu")]
        ])
        await self.safe_edit(update.callback_query,
            f"⚠️ **تأكيد الحذف**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 المستخدم: `{uid}` — {name}\n"
            f"🎫 الكود: `{code}`\n"
            f"📅 الاشتراك ينتهي: `{sub}`\n\n"
            f"هل تريد حذف الكود وتسجيل خروج المستخدم نهائياً؟", kb)

    async def admin_revoke_execute(self, update, ctx, uid: int, code: str):
        """تنفيذ الحذف الفوري + Logout قسري"""
        if not self._is_admin(update.effective_user.id): return
        # إبطال الكود
        self.db.execute(
            "UPDATE subscription_codes SET used_by=NULL WHERE code=?", (code,))
        # إيقاف الاشتراك فوراً
        self.db.execute(
            "UPDATE users SET subscription_end=date('now','-1 day') WHERE user_id=?", (uid,))
        # إشعار المستخدم إذا أمكن
        try:
            from telegram.constants import ParseMode as PM
            bot = update.callback_query.message.get_bot() \
                  if hasattr(update.callback_query.message, 'get_bot') \
                  else ctx.bot
            await bot.send_message(
                uid,
                "🔴 **تم إلغاء اشتراكك**\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "تم إلغاء اشتراكك من قِبل الإدارة.\n"
                "للاستفسار تواصل مع الدعم.",
                parse_mode=PM.MARKDOWN)
        except Exception as e:
            logger.debug(f"revoke notify: {e}")
        await self.safe_ans(update.callback_query, "✅ تم الإلغاء والـ Logout", True)
        await update.callback_query.message.reply_text(
            f"✅ **تمت المهمة**\n"
            f"🚫 الكود `{code}` ألغى\n"
            f"👤 المستخدم `{uid}` تم تسجيل خروجه فوراً.",
            parse_mode=ParseMode.MARKDOWN)
        await self.admin_revoke_code_menu(update, ctx)
