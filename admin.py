# -*- coding: utf-8 -*-
import asyncio, io, logging, os, sys, random, string
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
import utils as helpers

logger = logging.getLogger(__name__)

def btn(text, cb): return InlineKeyboardButton(text, callback_data=cb)
def back(cb):      return InlineKeyboardMarkup([[btn("🔙 رجوع", cb)]])

class AdminHandlers:
    def __init__(self, db, admin_ids, pub_svc=None, folder_svc=None, bot=None):
        self.db        = db
        self.admin_ids = admin_ids
        self.pub       = pub_svc
        self.folder    = folder_svc
        self.bot       = bot

    async def safe_edit(self, q, text, kb=None, pm=ParseMode.MARKDOWN):
        try:
            kw = {"parse_mode": pm}
            if kb: kw["reply_markup"] = kb
            await q.edit_message_text(text, **kw)
        except Exception as e:
            if "not modified" not in str(e).lower(): logger.debug(f"safe_edit: {e}")

    async def safe_ans(self, q, text="", alert=False):
        try: await q.answer(text, show_alert=alert)
        except Exception: pass

    def _is_admin(self, uid): return uid in self.admin_ids

    # ══════════════════════════════════════════════════════════════
    #   ⚙️ لوحة التحكم الرئيسية
    # ══════════════════════════════════════════════════════════════
    async def admin_panel(self, update, ctx):
        uid = update.effective_user.id
        if not self._is_admin(uid):
            await self.safe_ans(update.callback_query, "❌ غير مصرح."); return
        total   = (self.db.fetch_one("SELECT COUNT(*) as c FROM users") or {}).get("c", 0)
        active  = (self.db.fetch_one("SELECT COUNT(*) as c FROM users WHERE subscription_end >= date('now')") or {}).get("c", 0)
        banned  = (self.db.fetch_one("SELECT COUNT(*) as c FROM users WHERE status='banned'") or {}).get("c", 0)
        numbers = (self.db.fetch_one("SELECT COUNT(*) as c FROM numbers WHERE is_active=1") or {}).get("c", 0)
        folders = (self.db.fetch_one("SELECT COUNT(*) as c FROM folders") or {}).get("c", 0)
        stats   = helpers.get_server_stats()
        pub_w   = len(self.pub._campaigns) if self.pub else 0

        # نسبة أمان البوت
        cpu_s   = max(0, 100 - stats['cpu'])
        ram_s   = max(0, 100 - stats['mem_pct'])
        bot_safety = int((cpu_s + ram_s) / 2)
        si = helpers.health_icon(bot_safety)

        text = (
            f"⚙️ **لوحة التحكم**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👥 المستخدمين: `{total}`\n"
            f"⭐ المشتركين: `{active}`\n"
            f"🚫 المحظورين: `{banned}`\n"
            f"📱 الأرقام النشطة: `{numbers}`\n"
            f"📁 المجلدات: `{folders}`\n"
            f"🚀 النشر النشط: `{pub_w}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{si} نسبة الأمان: `{bot_safety}%`\n"
            f"🖥 CPU: `{stats['cpu']}%`\n"
            f"🧠 RAM: `{stats['mem_pct']}%`\n"
            f"💾 DISK: `{stats['disk_pct']:.1f}%`"
        )
        kb = InlineKeyboardMarkup([
            [btn("👥 إدارة المستخدمين",  "admin_manage_users"),   btn("📊 مراقبة النشاط",   "admin_activity")],
            [btn("🎫 إدارة الأكواد",      "admin_manage_codes"),   btn("📢 نظام الإذاعة",    "admin_broadcast_menu")],
            [btn("📱 إدارة الأرقام",      "admin_numbers_menu"),   btn("🤖 إدارة البوت",     "admin_bot_control")],
            [btn("🛡 نظام الأمان",         "admin_security"),       btn("📡 مراقبة السيرفر", "admin_server_status")],
            [btn("📂 قاعدة البيانات",     "admin_database_menu"),  btn("⚙️ الإعدادات",       "admin_bot_settings")],
            [btn("📝 النصوص والتعليمات", "admin_edit_texts"),      btn("🔑 توكين احتياطي",  "admin_backup_token")],
            [btn("🛠️ إعدادات نظام المهندس",  "eng_admin_menu")],
            [btn("🎛️ مفاتيح تحكم الأنظمة",      "ctrl_panel"),
             btn("📹 إدارة الفيديوهات",           "vid_admin_menu")],
            [btn("🔑 حذف كود مشترك (Logout)",     "sm_revoke_menu")],
            [btn("🔙 رجوع", "main_menu")]
        ])
        await self.safe_edit(update.callback_query, text, kb)

    # ══════════════════════════════════════════════════════════════
    #   👥 إدارة المستخدمين
    # ══════════════════════════════════════════════════════════════
    async def admin_manage_users(self, update, ctx):
        if not self._is_admin(update.effective_user.id):
            await self.safe_ans(update.callback_query, "❌"); return
        total   = (self.db.fetch_one("SELECT COUNT(*) as c FROM users") or {}).get("c", 0)
        active  = (self.db.fetch_one("SELECT COUNT(*) as c FROM users WHERE subscription_end >= date('now')") or {}).get("c", 0)
        banned  = (self.db.fetch_one("SELECT COUNT(*) as c FROM users WHERE status='banned'") or {}).get("c", 0)
        text = (f"👥 **إدارة المستخدمين**\n━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📊 الإجمالي: `{total}` | ✅ نشطون: `{active}` | 🚫 محظورون: `{banned}`")
        kb = InlineKeyboardMarkup([
            [btn("🔎 البحث عن مستخدم",     "admin_search_user")],
            [btn("📋 قائمة المستخدمين",     "admin_list_users")],
            [btn("⭐ المشتركون",             "admin_list_subscribed")],
            [btn("🚫 المحظورون",             "admin_list_banned")],
            [btn("📊 نشاط المستخدمين",     "admin_users_activity")],
            [btn("🔙 رجوع", "admin_panel")]
        ])
        await self.safe_edit(update.callback_query, text, kb)

    async def admin_list_users(self, update, ctx):
        page   = ctx.user_data.get("user_page", 0)
        limit  = 10
        offset = page * limit
        users  = self.db.fetch_all(
            "SELECT user_id,first_name,username,subscription_end,status FROM users ORDER BY user_id DESC LIMIT ? OFFSET ?",
            (limit, offset))
        total  = (self.db.fetch_one("SELECT COUNT(*) as c FROM users") or {}).get("c", 0)
        pages  = max(1, (total - 1) // limit + 1)
        text   = f"📋 **المستخدمون (ص {page+1}/{pages})**\n━━━━━━━━━━━━━━━━━━━━━━\n"
        rows   = []
        for u in users:
            try:
                ok = "✅" if u["subscription_end"] and datetime.strptime(u["subscription_end"], "%Y-%m-%d") >= datetime.now() else "❌"
            except Exception:
                ok = "❌"
            ban = "🚫" if u.get("status") == "banned" else ""
            text += f"{ok}{ban} {u['first_name'] or '—'} (`{u['user_id']}`)\n"
            rows.append([btn(f"👤 {u['first_name'] or u['user_id']}", f"show_user_{u['user_id']}")])
        nav = []
        if page > 0:             nav.append(btn("⬅️ السابق", "user_page_prev"))
        if offset + limit < total: nav.append(btn("التالي ➡️", "user_page_next"))
        if nav: rows.append(nav)
        rows.append([btn("🔙 رجوع", "admin_manage_users")])
        await self.safe_edit(update.callback_query, text, InlineKeyboardMarkup(rows))

    async def admin_list_subscribed(self, update, ctx):
        users = self.db.fetch_all(
            "SELECT user_id,first_name,username,subscription_end FROM users WHERE subscription_end >= date('now') ORDER BY subscription_end DESC LIMIT 30")
        text = "⭐ **المشتركون النشطون:**\n━━━━━━━━━━━━━━━━━━━━━━\n"
        rows = []
        for u in users:
            text += f"✅ {u['first_name'] or '—'} — ينتهي: `{(u['subscription_end'] or '')[:10]}`\n"
            rows.append([btn(f"👤 {u['first_name'] or u['user_id']}", f"show_user_{u['user_id']}")])
        if not users: text += "لا يوجد مشتركون."
        rows.append([btn("🔙 رجوع", "admin_manage_users")])
        await self.safe_edit(update.callback_query, text, InlineKeyboardMarkup(rows))

    async def admin_list_banned(self, update, ctx):
        users = self.db.fetch_all(
            "SELECT user_id,first_name,username FROM users WHERE status='banned' ORDER BY user_id DESC")
        text = "🚫 **المحظورون:**\n━━━━━━━━━━━━━━━━━━━━━━\n"
        rows = []
        for u in users:
            text += f"🚫 {u['first_name'] or '—'} (`{u['user_id']}`)\n"
            rows.append([btn(f"👤 {u['first_name'] or u['user_id']}", f"show_user_{u['user_id']}")])
        if not users: text += "لا يوجد محظورون."
        rows.append([btn("🔙 رجوع", "admin_manage_users")])
        await self.safe_edit(update.callback_query, text, InlineKeyboardMarkup(rows))

    async def admin_users_activity(self, update, ctx):
        top = self.db.fetch_all(
            "SELECT user_id,first_name,total_posts,total_joins,total_fetches FROM users ORDER BY total_posts+total_joins+total_fetches DESC LIMIT 10")
        text = "📊 **أكثر المستخدمين نشاطاً:**\n━━━━━━━━━━━━━━━━━━━━━━\n"
        for i, u in enumerate(top, 1):
            total = (u["total_posts"] or 0) + (u["total_joins"] or 0) + (u["total_fetches"] or 0)
            text += f"{i}. {u['first_name'] or '—'}: 📤{u['total_posts']} 🔍{u['total_fetches']} | إجمالي: {total}\n"
        if not top: text += "لا بيانات."
        await self.safe_edit(update.callback_query, text, back("admin_manage_users"))

    async def user_page_nav(self, update, ctx, direction):
        ctx.user_data["user_page"] = max(0, ctx.user_data.get("user_page", 0) + (1 if direction == "next" else -1))
        await self.admin_list_users(update, ctx)

    async def show_user_details(self, update, ctx, uid):
        u = self.db.get_user_stats(uid)
        if not u:
            await self.safe_ans(update.callback_query, "❌ مستخدم غير موجود.", True); return
        sub  = u.get("subscription_end", "—") or "غير مشترك"
        rem  = 0
        if u.get("subscription_end"):
            try:
                rem = max(0, (datetime.strptime(u["subscription_end"], "%Y-%m-%d") - datetime.now()).days)
            except Exception: rem = 0
        code_r = self.db.fetch_one("SELECT code,days FROM subscription_codes WHERE used_by=? ORDER BY used_at DESC LIMIT 1", (uid,))
        code_info = f"`{code_r['code']}` ({int(code_r['days'])} يوم)" if code_r else "—"
        banned = "🚫 محظور" if u.get("status") == "banned" else "✅ نشط"
        text = (
            f"👤 **تفاصيل المستخدم**\n━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 `{uid}`\n"
            f"📛 {u.get('first_name', '—')}\n"
            f"👤 @{u.get('username') or '—'}\n"
            f"📅 تاريخ التسجيل: `{(u.get('created_at') or '')[:10]}`\n"
            f"📱 الأرقام: `{u.get('numbers_count', 0)}`\n"
            f"📝 الإعلانات: `{u.get('ads_count', 0)}`\n"
            f"🎫 الكود المستخدم: {code_info}\n"
            f"⭐ حالة الاشتراك: `{sub}`\n"
            f"⏳ المتبقي: `{rem} يوم`\n"
            f"📤 النشر: `{u.get('total_posts', 0)}` | 🔍 الجلب: `{u.get('total_fetches', 0)}`\n"
            f"🔰 الحالة: {banned}"
        )
        is_banned = u.get("status") == "banned"
        kb = InlineKeyboardMarkup([
            [btn("🚫 حظر" if not is_banned else "✅ فك الحظر",
                 f"admin_ban_user_{uid}" if not is_banned else f"admin_unban_user_{uid}")],
            [btn("⭐ تمديد الاشتراك", f"admin_extend_user_{uid}"),
             btn("🗑 حذف المستخدم",   f"admin_delete_user_{uid}")],
            [btn("📱 أرقام المستخدم",  f"admin_user_numbers_{uid}"),
             btn("📊 عرض النشاط",     f"admin_user_activity_{uid}")],
            [btn("🚫 إيقاف الكود فوراً", f"eng_disable_code_{uid}")],
            [btn("🔙 رجوع", "admin_list_users")]
        ])
        await self.safe_edit(update.callback_query, text, kb)

    async def admin_ban_user(self, update, ctx, uid):
        self.db.execute("UPDATE users SET status='banned' WHERE user_id=?", (uid,))
        await self.safe_ans(update.callback_query, "🚫 تم الحظر", True)
        await update.callback_query.message.reply_text("✅ تمت المهمة — تم حظر المستخدم.")
        await self.show_user_details(update, ctx, uid)

    async def admin_unban_user(self, update, ctx, uid):
        self.db.execute("UPDATE users SET status='active' WHERE user_id=?", (uid,))
        await self.safe_ans(update.callback_query, "✅ تم فك الحظر", True)
        await update.callback_query.message.reply_text("✅ تمت المهمة — تم فك الحظر.")
        await self.show_user_details(update, ctx, uid)

    async def admin_delete_user(self, update, ctx, uid):
        ctx.user_data["confirm_delete_user"] = uid
        await self.safe_edit(update.callback_query,
            f"⚠️ **تأكيد الحذف**\nسيتم حذف المستخدم `{uid}` بشكل نهائي!",
            InlineKeyboardMarkup([
                [btn("🗑 تأكيد الحذف",  f"admin_confirm_delete_user_{uid}"),
                 btn("❌ إلغاء",         f"show_user_{uid}")]
            ]))

    async def admin_confirm_delete_user(self, update, ctx, uid):
        self.db.execute("DELETE FROM numbers WHERE user_id=?", (uid,))
        self.db.execute("DELETE FROM ads WHERE user_id=?", (uid,))
        self.db.execute("DELETE FROM settings WHERE user_id=?", (uid,))
        self.db.execute("DELETE FROM users WHERE user_id=?", (uid,))
        await self.safe_ans(update.callback_query, "✅ تم الحذف", True)
        await update.callback_query.message.reply_text(f"✅ تمت المهمة — تم حذف المستخدم `{uid}`.")
        await self.admin_list_users(update, ctx)

    async def admin_extend_user_prompt(self, update, ctx, uid):
        ctx.user_data["extend_user_id"] = uid
        ctx.user_data["state"] = "ADMIN_EXTEND_USER"
        await self.safe_edit(update.callback_query,
            f"⭐ **تمديد اشتراك** `{uid}`\nأرسل عدد الأيام (مثال: 30):",
            back(f"show_user_{uid}"))

    async def handle_extend_user(self, update, ctx):
        if ctx.user_data.get("state") != "ADMIN_EXTEND_USER": return
        uid = ctx.user_data.pop("extend_user_id", None)
        ctx.user_data.pop("state", None)
        txt = (update.message.text or "").strip()
        if not txt.replace(".", "").isdigit() or not uid:
            await update.message.reply_text("❌ أرسل عدد أيام صحيح."); return
        days = float(txt)
        u    = self.db.fetch_one("SELECT subscription_end FROM users WHERE user_id=?", (uid,))
        try:
            base = datetime.strptime(u["subscription_end"], "%Y-%m-%d") if (u and u["subscription_end"]) else datetime.now()
        except Exception:
            base = datetime.now()
        new_end = base + timedelta(days=days)
        self.db.execute("UPDATE users SET subscription_end=? WHERE user_id=?", (new_end.strftime("%Y-%m-%d"), uid))
        await update.message.reply_text(
            f"✅ تمت المهمة — تم تمديد اشتراك `{uid}` بـ {days} يوم.\nتنتهي: `{new_end.strftime('%Y-%m-%d')}`")

    async def admin_user_numbers(self, update, ctx, uid):
        nums = self.db.fetch_all("SELECT id,phone,is_active,health,added_at FROM numbers WHERE user_id=?", (uid,))
        text = f"📱 **أرقام المستخدم** `{uid}`\n━━━━━━━━━━━━━━━━━━━━━━\n"
        for n in nums:
            st = "✅" if n["is_active"] else "❌"
            text += f"{st} {n['phone']} — صحة: {n['health']}%\n"
        if not nums: text += "لا أرقام مسجلة."
        await self.safe_edit(update.callback_query, text, back(f"show_user_{uid}"))

    async def admin_user_activity(self, update, ctx, uid):
        u = self.db.get_user_stats(uid)
        if not u:
            await self.safe_ans(update.callback_query, "❌", True); return
        logs = self.db.fetch_all(
            "SELECT action,details,created_at FROM activity_logs WHERE user_id=? ORDER BY created_at DESC LIMIT 10", (uid,))
        text = (f"📊 **نشاط المستخدم** `{uid}`\n━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📤 نشر: {u.get('total_posts',0)} | 🔍 جلب: {u.get('total_fetches',0)}\n\n"
                f"📋 **آخر النشاطات:**\n")
        for l in logs:
            text += f"• {(l['created_at'] or '')[:16]} — {l['action']}\n"
        if not logs: text += "لا نشاطات مسجلة."
        await self.safe_edit(update.callback_query, text, back(f"show_user_{uid}"))

    async def admin_search_user(self, update, ctx):
        ctx.user_data["state"] = "ADMIN_SEARCH"
        await self.safe_edit(update.callback_query,
            "🔎 **البحث عن مستخدم**\n━━━━━━━━━━━━━━━━━━━━━━\n"
            "أرسل:\n1️⃣ ID المستخدم (رقم)\n2️⃣ @username\n3️⃣ رقم الهاتف",
            back("admin_manage_users"))

    async def handle_search_user(self, update, ctx):
        if ctx.user_data.get("state") != "ADMIN_SEARCH": return
        txt = (update.message.text or "").strip()
        ctx.user_data.pop("state", None)
        u = None
        if txt.lstrip("-").isdigit():
            u = self.db.get_user_stats(int(txt))
        elif txt.startswith("@"):
            uname = txt[1:]
            ur = self.db.fetch_one("SELECT user_id FROM users WHERE username=?", (uname,))
            if ur: u = self.db.get_user_stats(ur["user_id"])
        else:
            nr = self.db.fetch_one("SELECT user_id FROM numbers WHERE phone=?", (txt,))
            if nr: u = self.db.get_user_stats(nr["user_id"])
        if not u:
            await update.message.reply_text("❌ لم يُعثر على مستخدم."); return
        uid  = u.get("user_id") or u.get("user_id")
        sub  = u.get("subscription_end", "—") or "غير مشترك"
        code_r = self.db.fetch_one("SELECT code FROM subscription_codes WHERE used_by=? ORDER BY used_at DESC LIMIT 1",
                                   (u["user_id"],))
        banned = "🚫 محظور" if u.get("status") == "banned" else "✅ نشط"
        await update.message.reply_text(
            f"👤 **{u.get('first_name','—')}**\n"
            f"🆔 `{u['user_id']}`\n"
            f"👤 @{u.get('username') or '—'}\n"
            f"📅 التسجيل: `{(u.get('created_at') or '')[:10]}`\n"
            f"📱 أرقام: {u.get('numbers_count',0)}\n"
            f"📝 إعلانات: {u.get('ads_count',0)}\n"
            f"🎫 الكود: `{code_r['code'] if code_r else '—'}`\n"
            f"⭐ اشتراك: `{sub}`\n"
            f"📤 نشر: {u.get('total_posts',0)} | 🔍 جلب: {u.get('total_fetches',0)}\n"
            f"🔰 الحالة: {banned}",
            parse_mode=ParseMode.MARKDOWN)

    # ══════════════════════════════════════════════════════════════
    #   📊 مراقبة النشاط
    # ══════════════════════════════════════════════════════════════
    async def admin_activity(self, update, ctx):
        if not self._is_admin(update.effective_user.id):
            await self.safe_ans(update.callback_query, "❌"); return
        kb = InlineKeyboardMarkup([
            [btn("📊 النشاط المباشر",     "admin_activity_live")],
            [btn("📈 نشاط اليوم",          "admin_activity_today")],
            [btn("📉 نشاط الأسبوع",        "admin_activity_week")],
            [btn("🔥 أكثر المستخدمين نشاطاً", "admin_users_activity")],
            [btn("👁 المستخدمون النشطون الآن", "admin_active_now")],
            [btn("🔙 رجوع", "admin_panel")]
        ])
        await self.safe_edit(update.callback_query, "📊 **مراقبة النشاط**", kb)

    async def admin_activity_live(self, update, ctx):
        pub_w  = len(self.pub._campaigns) if self.pub else 0
        fldr_w = len(self.folder._tasks)  if self.folder else 0
        stats  = helpers.get_server_stats()
        text = (f"📊 **النشاط المباشر**\n━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🚀 عمليات النشر النشطة: `{pub_w}`\n"
                f"📁 مهام المجلدات النشطة: `{fldr_w}`\n"
                f"🖥 CPU: `{stats['cpu']}%`\n"
                f"🧠 RAM: `{stats['mem_pct']}%`\n"
                f"💾 DISK: `{stats['disk_pct']:.1f}%`")
        await self.safe_edit(update.callback_query, text, back("admin_activity"))

    async def admin_activity_today(self, update, ctx):
        logs = self.db.fetch_all(
            "SELECT action, COUNT(*) as c FROM activity_logs WHERE date(created_at)=date('now') GROUP BY action")
        text = "📈 **نشاط اليوم:**\n━━━━━━━━━━━━━━━━━━━━━━\n"
        for l in logs:
            text += f"• {l['action']}: `{l['c']}`\n"
        if not logs: text += "لا نشاطات اليوم."
        await self.safe_edit(update.callback_query, text, back("admin_activity"))

    async def admin_activity_week(self, update, ctx):
        logs = self.db.fetch_all(
            "SELECT action, COUNT(*) as c FROM activity_logs WHERE created_at >= date('now','-7 days') GROUP BY action")
        text = "📉 **نشاط الأسبوع:**\n━━━━━━━━━━━━━━━━━━━━━━\n"
        for l in logs:
            text += f"• {l['action']}: `{l['c']}`\n"
        if not logs: text += "لا نشاطات هذا الأسبوع."
        await self.safe_edit(update.callback_query, text, back("admin_activity"))

    async def admin_active_now(self, update, ctx):
        pub_w = len(self.pub._campaigns) if self.pub else 0
        active_uids = list(self.pub._campaigns.keys()) if self.pub else []
        text = (f"👁 **المستخدمون النشطون الآن:**\n━━━━━━━━━━━━━━━━━━━━━━\n"
                f"إجمالي النشاط: `{pub_w}` عملية نشر\n\n")
        for uid in active_uids[:10]:
            u = self.db.fetch_one("SELECT first_name FROM users WHERE user_id=?", (uid,))
            name = (u or {}).get("first_name", str(uid))
            text += f"• `{uid}` — {name}\n"
        if not active_uids: text += "لا مستخدمون نشطون حالياً."
        await self.safe_edit(update.callback_query, text, back("admin_activity"))

    # ══════════════════════════════════════════════════════════════
    #   🎫 إدارة الأكواد
    # ══════════════════════════════════════════════════════════════
    async def admin_manage_codes(self, update, ctx):
        if not self._is_admin(update.effective_user.id):
            await self.safe_ans(update.callback_query, "❌"); return
        total     = (self.db.fetch_one("SELECT COUNT(*) as c FROM subscription_codes") or {}).get("c", 0)
        unused    = (self.db.fetch_one("SELECT COUNT(*) as c FROM subscription_codes WHERE used_by IS NULL") or {}).get("c", 0)
        used      = (self.db.fetch_one("SELECT COUNT(*) as c FROM subscription_codes WHERE used_by IS NOT NULL") or {}).get("c", 0)
        active    = (self.db.fetch_one("""SELECT COUNT(*) as c FROM subscription_codes sc
                                         JOIN users u ON sc.used_by=u.user_id
                                         WHERE u.subscription_end >= date('now')""") or {}).get("c", 0)
        text = (f"🎫 **إدارة الأكواد**\n━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📊 الإجمالي: `{total}` | غير مستخدم: `{unused}`\n"
                f"✅ مستخدم: `{used}` | 🟢 نشط: `{active}`")
        kb = InlineKeyboardMarkup([
            [btn("➕ إنشاء كود",          "admin_add_code"),
             btn("🎁 كود تجريبي",          "admin_trial_code")],
            [btn("📋 عرض الأكواد",         "admin_list_codes_full"),
             btn("📊 تقرير الأكواد",        "admin_codes_report")],
            [btn("📤 تصدير تقرير الأكواد", "admin_export_codes"),
             btn("🗑 حذف كود",             "admin_delete_code")],
            [btn("➕ إضافة يدوي",           "admin_add_code_manual"),
             btn("💰 سجل المبيعات",         "admin_sales_report")],
            [btn("🚫 حذف كود من مستخدم",    "sm_revoke_menu")],
            [btn("🔙 رجوع", "admin_panel")]
        ])
        await self.safe_edit(update.callback_query, text, kb)

    async def admin_add_code_prompt(self, update, ctx):
        await self.safe_edit(update.callback_query,
            "📝 **إنشاء كود جديد**\n━━━━━━━━━━━━━━━━━━━━━━\n"
            "أرسل: `الاسم الأيام`\nمثال: `أحمد 30`",
            back("admin_manage_codes"))
        ctx.user_data["state"] = "ADD_CODE"

    async def handle_add_code(self, update, ctx):
        if ctx.user_data.get("state") != "ADD_CODE": return
        try:
            parts = update.message.text.strip().split()
            if len(parts) < 2: raise ValueError()
            name, days = parts[0], float(parts[1])
            code = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
            self.db.add_code(code, days, name, created_by=update.effective_user.id)
            await update.message.reply_text(
                f"✅ **تم إنشاء الكود**\n━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🎫 الكود: `{code}`\n"
                f"👤 الاسم: {name}\n"
                f"⏳ مدة الاشتراك: {days} يوم",
                parse_mode=ParseMode.MARKDOWN)
        except Exception:
            await update.message.reply_text("❌ صيغة خاطئة. مثال: `أحمد 30`")
        ctx.user_data.pop("state", None)

    async def admin_trial_code(self, update, ctx):
        await self.safe_edit(update.callback_query, "🎁 **مدة الكود التجريبي:**",
            InlineKeyboardMarkup([
                [btn("⏱️ 3 ساعات", "trial_3h"),  btn("⏱️ 12 ساعة", "trial_12h")],
                [btn("📅 يوم",      "trial_1d"),   btn("📅 يومان",    "trial_2d")],
                [btn("🔙 رجوع",    "admin_manage_codes")]
            ]))

    async def handle_trial_selection(self, update, ctx, hours):
        days = hours / 24.0
        code = f"TRIAL-{hours}H-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
        self.db.add_code(code, days, f"تجريبي {hours}ساعة", created_by=update.effective_user.id)
        lbl = f"{hours} ساعة" if hours < 24 else f"{int(days)} يوم"
        await self.safe_edit(update.callback_query,
            f"✅ **تم إنشاء الكود**\n━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎫 الكود: `{code}`\n⏳ المدة: {lbl}",
            back("admin_manage_codes"))

    async def admin_list_codes_full(self, update, ctx):
        """عرض جميع الأكواد مصنفة"""
        all_codes = self.db.fetch_all("""
            SELECT sc.*, u.first_name as user_name, u.subscription_end
            FROM subscription_codes sc
            LEFT JOIN users u ON sc.used_by = u.user_id
            ORDER BY sc.created_at DESC
        """)
        if not all_codes:
            await self.safe_edit(update.callback_query, "📭 لا توجد أكواد.", back("admin_manage_codes")); return

        now = datetime.now()
        text = "🎫 **جميع الأكواد:**\n━━━━━━━━━━━━━━━━━━━━━━\n"
        count = 0
        for c in all_codes[:25]:
            lbl = f"{int(c['days']*24)}ساعة" if (c["days"] or 0) < 1 else f"{int(c['days'] or 0)}يوم"
            if c["used_by"] is None:
                # التحقق من انتهاء الصلاحية قبل الاستخدام (7 أيام من الإنشاء كافتراضي)
                created = c.get("created_at", "")
                try:
                    created_dt = datetime.strptime(created[:19], "%Y-%m-%d %H:%M:%S")
                    if (now - created_dt).days > 7:
                        status = "⏰ منتهي قبل التفعيل"
                    else:
                        status = "🔵 غير مستخدم"
                except Exception:
                    status = "🔵 غير مستخدم"
            else:
                try:
                    sub_end = c.get("subscription_end", "")
                    if sub_end and datetime.strptime(sub_end, "%Y-%m-%d") >= now:
                        status = "🟢 نشط"
                    else:
                        status = "🔴 منتهي"
                except Exception:
                    status = "🟡 مستخدم"
            text += f"{status} `{c['code']}` — {lbl} — {c.get('owner_name','—')}\n"
            count += 1
        if count >= 25: text += f"\n_...وأكثر — استخدم تصدير التقرير للكل_"
        await self.safe_edit(update.callback_query, text, back("admin_manage_codes"))

    # المتوافق مع الكود القديم
    async def admin_list_codes(self, update, ctx):
        await self.admin_list_codes_full(update, ctx)

    async def admin_codes_report(self, update, ctx):
        """تقرير شامل للأكواد"""
        now = datetime.now()
        unused    = self.db.fetch_all("SELECT * FROM subscription_codes WHERE used_by IS NULL ORDER BY created_at DESC")
        used_all  = self.db.fetch_all("""
            SELECT sc.*, u.first_name, u.username, u.subscription_end
            FROM subscription_codes sc JOIN users u ON sc.used_by=u.user_id
            ORDER BY sc.used_at DESC""")

        active  = [r for r in used_all if r.get("subscription_end") and
                   self._safe_date(r["subscription_end"]) >= now.date()]
        expired = [r for r in used_all if not r.get("subscription_end") or
                   self._safe_date(r["subscription_end"]) < now.date()]

        total_unused = len(unused)
        total_active  = len(active)
        total_expired = len(expired)
        total_all     = total_unused + len(used_all)

        text = (f"📊 **تقرير الأكواد**\n━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📊 الإجمالي: `{total_all}`\n"
                f"🔵 غير مستخدمة: `{total_unused}`\n"
                f"🟢 نشطة: `{total_active}`\n"
                f"🔴 منتهية: `{total_expired}`\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📤 لتصدير التقرير الكامل: استخدم زر التصدير")
        await self.safe_edit(update.callback_query, text, back("admin_manage_codes"))

    def _safe_date(self, s):
        try: return datetime.strptime(s, "%Y-%m-%d").date()
        except Exception: return datetime.min.date()

    async def admin_export_codes(self, update, ctx):
        """تصدير تقرير الأكواد كملف txt"""
        now = datetime.now()
        all_codes = self.db.fetch_all("""
            SELECT sc.*, u.first_name, u.username, u.subscription_end
            FROM subscription_codes sc
            LEFT JOIN users u ON sc.used_by = u.user_id
            ORDER BY sc.created_at DESC
        """)

        lines = [
            "════════════════════════════════════════",
            "📊 تقرير الأكواد",
            "════════════════════════════════════════",
            f"📅 التاريخ: {now.strftime('%Y-%m-%d %H:%M')}",
            "",
        ]

        used_rows   = [c for c in all_codes if c["used_by"]]
        unused_rows = [c for c in all_codes if not c["used_by"]]
        active_rows = [c for c in used_rows if c.get("subscription_end") and
                       self._safe_date(c["subscription_end"]) >= now.date()]
        expired_rows = [c for c in used_rows if not c.get("subscription_end") or
                        self._safe_date(c["subscription_end"]) < now.date()]

        lines += ["━━━━━ الأكواد المستخدمة ━━━━━"]
        for c in used_rows:
            days_lbl = f"{int(c['days']*24)}ساعة" if (c["days"] or 0) < 1 else f"{int(c['days'] or 0)}يوم"
            lines.append(f"🔹 الكود: {c['code']}")
            lines.append(f"   المالك: {c.get('owner_name','—')}")
            lines.append(f"   المستخدم: {c.get('first_name','—')} (ID: {c['used_by']})")
            lines.append(f"   تاريخ التفعيل: {(c.get('used_at') or '')[:16]}")
            lines.append(f"   مدة الاشتراك: {days_lbl}")
            lines.append(f"   تاريخ الانتهاء: {c.get('subscription_end','—')}")
            sub_end = c.get("subscription_end", "")
            status = "🟢 نشط" if sub_end and self._safe_date(sub_end) >= now.date() else "🔴 منتهي"
            lines.append(f"   الحالة: {status}")
            lines.append("")

        lines += ["━━━━━ الأكواد النشطة ━━━━━"]
        for c in active_rows:
            try:
                rem = (datetime.strptime(c["subscription_end"], "%Y-%m-%d") - now).days
            except Exception:
                rem = 0
            lines.append(f"🟢 {c['code']} — {c.get('first_name','—')} — متبقي: {rem} يوم")

        lines += ["", "━━━━━ الأكواد المنتهية ━━━━━"]
        for c in expired_rows:
            lines.append(f"🔴 {c['code']} — انتهت: {c.get('subscription_end','—')}")

        lines += ["", "━━━━━ الأكواد غير المستخدمة ━━━━━"]
        for c in unused_rows:
            days_lbl = f"{int(c['days']*24)}ساعة" if (c["days"] or 0) < 1 else f"{int(c['days'] or 0)}يوم"
            lines.append(f"🔵 {c['code']} — إنشاء: {(c.get('created_at') or '')[:10]} — مدة: {days_lbl}")

        lines += [
            "",
            "━━━━━ إحصائيات ━━━━━",
            f"📊 عدد الأكواد الكلي: {len(all_codes)}",
            f"🟡 عدد الأكواد المستخدمة: {len(used_rows)}",
            f"🟢 عدد الأكواد النشطة: {len(active_rows)}",
            f"🔴 عدد الأكواد المنتهية: {len(expired_rows)}",
            f"🔵 عدد الأكواد غير المستخدمة: {len(unused_rows)}",
            "════════════════════════════════════════",
        ]

        content  = "\n".join(lines)
        buf      = io.BytesIO(content.encode("utf-8"))
        buf.name = f"codes_report_{now.strftime('%Y%m%d_%H%M%S')}.txt"
        await update.callback_query.message.reply_document(
            document=buf, filename=buf.name, caption="✅ تقرير الأكواد")
        await self.safe_ans(update.callback_query, "✅ تم التصدير")

    async def admin_add_code_manual(self, update, ctx):
        await self.safe_edit(update.callback_query,
            "📝 أرسل: `الكود المدة الاسم`\nمثال: `AHMED123 30 أحمد`", back("admin_manage_codes"))
        ctx.user_data["state"] = "ADMIN_ADD_CODE_MANUAL"

    async def handle_add_code_manual(self, update, ctx):
        if ctx.user_data.get("state") != "ADMIN_ADD_CODE_MANUAL": return
        try:
            parts = update.message.text.strip().split(maxsplit=2)
            if len(parts) < 3: raise ValueError()
            code, days, name = parts[0], float(parts[1]), parts[2]
            if self.db.fetch_one("SELECT code FROM subscription_codes WHERE code=?", (code,)):
                await update.message.reply_text("❌ الكود موجود مسبقاً."); return
            self.db.add_code(code, days, name, created_by=update.effective_user.id)
            await update.message.reply_text(f"✅ تمت المهمة — تمت الإضافة: `{code}` — {days}يوم — {name}",
                                            parse_mode=ParseMode.MARKDOWN)
        except Exception:
            await update.message.reply_text("❌ صيغة خاطئة. مثال: `AHMED123 30 أحمد`")
        ctx.user_data.pop("state", None)

    async def admin_delete_code_prompt(self, update, ctx):
        codes = self.db.fetch_all("SELECT code,days,owner_name FROM subscription_codes WHERE used_by IS NULL ORDER BY created_at DESC")
        if not codes:
            await self.safe_edit(update.callback_query, "📭 لا توجد أكواد للحذف.", back("admin_manage_codes")); return
        rows = []
        for c in codes[:20]:
            lbl = f"{int(c['days']*24)}ساعة" if (c["days"] or 0) < 1 else f"{int(c['days'] or 0)}يوم"
            rows.append([btn(f"🗑️ {c['code']} ({lbl}) — {c['owner_name']}", f"delete_code_{c['code']}")])
        rows.append([btn("🔙 رجوع", "admin_manage_codes")])
        await self.safe_edit(update.callback_query, "🗑 اختر الكود للحذف:", InlineKeyboardMarkup(rows))

    async def handle_delete_code(self, update, ctx, code):
        if not self._is_admin(update.effective_user.id): return
        code_info = self.db.fetch_one(
            "SELECT used_by FROM subscription_codes WHERE code=?", (code,))
        used_by   = (code_info or {}).get("used_by")
        logout_note = "🔵 الكود لم يكن مستخدماً"
        if used_by:
            u = self.db.fetch_one(
                "SELECT first_name, username FROM users WHERE user_id=?", (used_by,))
            uname_tag = f"@{(u or {}).get('username','')}" if (u or {}).get("username") else ""
            user_name = (u or {}).get("first_name", "") or str(used_by)
            self.db.execute(
                "UPDATE users SET subscription_end=date('now','-1 day') WHERE user_id=?",
                (used_by,))
            if self.bot:
                try:
                    await self.bot.send_message(used_by,
                        "🔴 **تم إلغاء اشتراكك**\n━━━━━━━━━━━━━━━━━━━━━━\n"
                        "تم حذف كودك من قِبل الإدارة.\nللاستفسار تواصل مع الدعم.",
                        parse_mode="Markdown")
                except Exception: pass
            logout_note = f"🔴 Logout: `{used_by}` — {user_name} {uname_tag}"
        self.db.delete_code(code)
        notify_msg = (f"🗑️ **تم حذف كود**\n━━━━━━━━━━━━━━━━━━━━━━\n"
                      f"🎫 الكود: `{code}`\n{logout_note}\n"
                      f"🕒 {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        for a in self.admin_ids:
            try:
                if self.bot and a != update.effective_user.id:
                    await self.bot.send_message(a, notify_msg, parse_mode="Markdown")
            except Exception: pass
        await self.safe_ans(update.callback_query,
            "✅ حُذف" + (" + Logout المستخدم" if used_by else ""))
        await update.callback_query.message.reply_text(
            f"✅ **تمت المهمة**\n🗑️ `{code}` حُذف\n{logout_note}",
            parse_mode="Markdown")
        await self.admin_delete_code_prompt(update, ctx)

    async def admin_sales_report(self, update, ctx):
        rows = self.db.fetch_all("""
            SELECT sc.code,sc.days,sc.owner_name,sc.used_by,sc.used_at,u.first_name,u.username
            FROM subscription_codes sc LEFT JOIN users u ON sc.used_by=u.user_id
            WHERE sc.used_by IS NOT NULL ORDER BY sc.used_at DESC LIMIT 20""")
        if not rows:
            await self.safe_edit(update.callback_query, "📭 لا توجد مبيعات.", back("admin_manage_codes")); return
        text = "💰 **آخر 20 تفعيل:**\n━━━━━━━━━━━━━━━━━━━━━━\n"
        for r in rows:
            nm   = r["first_name"] or str(r["used_by"])
            lbl  = f"{int(r['days']*24)}ساعة" if (r["days"] or 0) < 1 else f"{int(r['days'] or 0)}يوم"
            text += f"🔹 `{r['code']}` — {lbl} — {nm} — {(r['used_at'] or '')[:16]}\n"
        await self.safe_edit(update.callback_query, text, back("admin_manage_codes"))

    # ══════════════════════════════════════════════════════════════
    #  دوال إضافية مطلوبة من router.py
    # ══════════════════════════════════════════════════════════════
    async def admin_live_codes(self, update, ctx):
        """عرض الأكواد النشطة حالياً"""
        if not self._is_admin(update.effective_user.id):
            await self.safe_ans(update.callback_query, "❌"); return
        rows = self.db.fetch_all("""
            SELECT sc.code, sc.days, u.first_name, u.subscription_end
            FROM subscription_codes sc
            JOIN users u ON sc.used_by = u.user_id
            WHERE sc.used_by IS NOT NULL
              AND u.subscription_end >= date('now')
            ORDER BY u.subscription_end DESC LIMIT 20
        """)
        text = "🟢 **الأكواد النشطة الآن:**\n━━━━━━━━━━━━━━━━━━━━━━\n"
        for r in rows:
            lbl = f"{int(r['days']*24)}ساعة" if (r['days'] or 0) < 1 else f"{int(r['days'] or 0)}يوم"
            text += f"🔹 `{r['code']}` — {lbl} — {r.get('first_name','—')} — حتى: `{r.get('subscription_end','—')}`\n"
        if not rows: text += "لا توجد أكواد نشطة."
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_manage_codes")]])
        await self.safe_edit(update.callback_query, text, kb)

    async def admin_purge_no_code(self, update, ctx):
        """عرض المستخدمين الذين انتهى اشتراكهم"""
        if not self._is_admin(update.effective_user.id):
            await self.safe_ans(update.callback_query, "❌"); return
        expired = self.db.fetch_all(
            "SELECT user_id, first_name, subscription_end FROM users "
            "WHERE subscription_end < date('now') OR subscription_end IS NULL "
            "ORDER BY subscription_end ASC LIMIT 20")
        text = "🗑 **المستخدمون منتهي الاشتراك:**\n━━━━━━━━━━━━━━━━━━━━━━\n"
        for u in expired:
            text += f"👤 {u.get('first_name','—')} (`{u['user_id']}`) — {u.get('subscription_end','—')}\n"
        if not expired: text += "✅ لا يوجد مستخدمون منتهي الاشتراك."
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🗑 تنفيذ الحذف", callback_data="admin_purge_exec")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="admin_manage_codes")]
        ])
        await self.safe_edit(update.callback_query, text, kb)

    async def admin_purge_execute(self, update, ctx):
        """حذف المستخدمين منتهي الاشتراك"""
        if not self._is_admin(update.effective_user.id):
            await self.safe_ans(update.callback_query, "❌"); return
        expired = self.db.fetch_all(
            "SELECT user_id FROM users WHERE subscription_end < date('now') OR subscription_end IS NULL")
        count = 0
        for u in expired:
            try:
                self.db.execute("DELETE FROM numbers WHERE user_id=?", (u["user_id"],))
                self.db.execute("DELETE FROM ads WHERE user_id=?", (u["user_id"],))
                self.db.execute("DELETE FROM settings WHERE user_id=?", (u["user_id"],))
                self.db.execute("DELETE FROM users WHERE user_id=?", (u["user_id"],))
                count += 1
            except Exception: pass
        await self.safe_ans(update.callback_query, f"✅ تم حذف {count} مستخدم منتهي", True)
        await update.callback_query.message.reply_text(f"✅ تمت المهمة — تم حذف {count} مستخدم منتهي الاشتراك.")

    async def admin_revoke_confirm(self, update, ctx, uid: int, code: str):
        """تأكيد إلغاء كود مستخدم"""
        if not self._is_admin(update.effective_user.id): return
        u = self.db.fetch_one("SELECT first_name, subscription_end FROM users WHERE user_id=?", (uid,))
        name = (u or {}).get("first_name", str(uid))
        sub  = (u or {}).get("subscription_end", "—")
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ نعم — إلغاء الكود فوراً",
                                  callback_data=f"admin_rev_exec_{uid}_{code}")],
            [InlineKeyboardButton("❌ إلغاء", callback_data="sm_revoke_menu")]
        ])
        await self.safe_edit(update.callback_query,
            f"⚠️ **تأكيد إلغاء الكود**\n━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 `{uid}` — {name}\n🎫 الكود: `{code}`\n"
            f"📅 ينتهي: `{sub}`\n\nهل تريد إلغاء اشتراكه فوراً؟", kb)

    async def admin_revoke_execute(self, update, ctx, uid: int, code: str):
        """تنفيذ إلغاء كود مستخدم"""
        if not self._is_admin(update.effective_user.id): return
        self.db.execute("UPDATE subscription_codes SET used_by=NULL WHERE code=?", (code,))
        self.db.execute("UPDATE users SET subscription_end=date('now','-1 day') WHERE user_id=?", (uid,))
        try:
            if self.bot:
                await self.bot.send_message(uid,
                    "🔴 **تم إلغاء اشتراكك**\n━━━━━━━━━━━━━━━━━━━━━━\n"
                    "تم إلغاء اشتراكك من قِبل الإدارة.\nللاستفسار تواصل مع الدعم.",
                    parse_mode="Markdown")
        except Exception: pass
        await self.safe_ans(update.callback_query, "✅ تم إلغاء الاشتراك", True)
        await update.callback_query.message.reply_text(
            f"✅ تم إلغاء كود `{code}` وتسجيل خروج المستخدم `{uid}` فوراً.")


    async def notify_code_activation(self, code, uid):
        u   = self.db.fetch_one("SELECT first_name, username FROM users WHERE user_id=?", (uid,))
        ci  = self.db.fetch_one("SELECT days, owner_name FROM subscription_codes WHERE code=?", (code,))
        sub = self.db.fetch_one("SELECT subscription_end FROM users WHERE user_id=?", (uid,))
        if not ci or not self.bot: return
        nm    = (u or {}).get("first_name", "") or str(uid)
        uname = f"@{(u or {}).get('username','')}" if (u or {}).get("username") else ""
        lbl   = f"{int(ci['days']*24)}ساعة" if (ci["days"] or 0) < 1 else f"{int(ci['days'] or 0)}يوم"
        sub_end = (sub or {}).get("subscription_end", "—")
        msg = (f"🔔 **تفعيل كود جديد!**\n━━━━━━━━━━━━━━━━━━━━━━\n"
               f"👤 `{uid}` — {nm} {uname}\n"
               f"🎫 الكود: `{code}`\n"
               f"⏳ المدة: {lbl}\n"
               f"📅 الاشتراك حتى: `{sub_end}`\n"
               f"🕒 {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        for a in self.admin_ids:
            try: await self.bot.send_message(a, msg, parse_mode=ParseMode.MARKDOWN)
            except Exception: pass

    # ══════════════════════════════════════════════════════════════
    #   📱 إدارة الأرقام
    # ══════════════════════════════════════════════════════════════
    async def admin_numbers_menu(self, update, ctx):
        if not self._is_admin(update.effective_user.id):
            await self.safe_ans(update.callback_query, "❌"); return
        active  = (self.db.fetch_one("SELECT COUNT(*) as c FROM numbers WHERE is_active=1") or {}).get("c", 0)
        banned  = (self.db.fetch_one("SELECT COUNT(*) as c FROM numbers WHERE health=0") or {}).get("c", 0)
        total   = (self.db.fetch_one("SELECT COUNT(*) as c FROM numbers") or {}).get("c", 0)
        text    = (f"📱 **إدارة الأرقام**\n━━━━━━━━━━━━━━━━━━━━━━\n"
                   f"📊 الإجمالي: `{total}` | ✅ النشطة: `{active}` | 🚫 المحظورة: `{banned}`")
        kb = InlineKeyboardMarkup([
            [btn("📱 الأرقام النشطة",         "admin_active_numbers")],
            [btn("📊 إحصائيات الأرقام",       "admin_numbers_stats")],
            [btn("🚫 الأرقام المحظورة",        "admin_banned_numbers")],
            [btn("⚠️ الأرقام المعرضة للحظر",  "admin_risky_numbers")],
            [btn("🔙 رجوع", "admin_panel")]
        ])
        await self.safe_edit(update.callback_query, text, kb)

    async def admin_active_numbers(self, update, ctx):
        nums = self.db.fetch_all("""
            SELECT n.id, n.phone, n.health, n.is_busy, n.added_at, u.first_name
            FROM numbers n LEFT JOIN users u ON n.user_id=u.user_id
            WHERE n.is_active=1 ORDER BY n.health DESC LIMIT 30""")
        text = "📱 **الأرقام النشطة:**\n━━━━━━━━━━━━━━━━━━━━━━\n"
        for n in nums:
            busy = "🔵" if n["is_busy"] else "🟢"
            text += f"{busy} {n['phone']} — صحة: {n['health']}% — {n.get('first_name','—')}\n"
        if not nums: text += "لا أرقام نشطة."
        await self.safe_edit(update.callback_query, text, back("admin_numbers_menu"))

    async def admin_numbers_stats(self, update, ctx):
        total  = (self.db.fetch_one("SELECT COUNT(*) as c FROM numbers") or {}).get("c", 0)
        active = (self.db.fetch_one("SELECT COUNT(*) as c FROM numbers WHERE is_active=1") or {}).get("c", 0)
        busy   = (self.db.fetch_one("SELECT COUNT(*) as c FROM numbers WHERE is_busy=1") or {}).get("c", 0)
        low_h  = (self.db.fetch_one("SELECT COUNT(*) as c FROM numbers WHERE health < 50 AND is_active=1") or {}).get("c", 0)
        text   = (f"📊 **إحصائيات الأرقام**\n━━━━━━━━━━━━━━━━━━━━━━\n"
                  f"📊 الإجمالي: `{total}`\n"
                  f"✅ النشطة: `{active}`\n"
                  f"🔵 المشغولة: `{busy}`\n"
                  f"⚠️ صحة منخفضة (<50%): `{low_h}`\n"
                  f"🚫 المعطلة: `{total-active}`")
        await self.safe_edit(update.callback_query, text, back("admin_numbers_menu"))

    async def admin_banned_numbers(self, update, ctx):
        nums = self.db.fetch_all("""
            SELECT n.phone, u.first_name, n.last_flood
            FROM numbers n LEFT JOIN users u ON n.user_id=u.user_id
            WHERE n.health=0 OR n.is_active=0""")
        text = "🚫 **الأرقام المحظورة/المعطلة:**\n━━━━━━━━━━━━━━━━━━━━━━\n"
        for n in nums:
            text += f"🔴 {n['phone']} — {n.get('first_name','—')}\n"
        if not nums: text += "لا أرقام محظورة."
        await self.safe_edit(update.callback_query, text, back("admin_numbers_menu"))

    async def admin_risky_numbers(self, update, ctx):
        nums = self.db.fetch_all("""
            SELECT n.phone, n.health, n.last_flood, u.first_name
            FROM numbers n LEFT JOIN users u ON n.user_id=u.user_id
            WHERE n.health < 50 AND n.is_active=1 ORDER BY n.health ASC""")
        text = "⚠️ **الأرقام المعرضة للحظر (صحة <50%):**\n━━━━━━━━━━━━━━━━━━━━━━\n"
        for n in nums:
            text += f"⚠️ {n['phone']} — صحة: {n['health']}% — {n.get('first_name','—')}\n"
        if not nums: text += "✅ لا أرقام معرضة للخطر."
        await self.safe_edit(update.callback_query, text, back("admin_numbers_menu"))

    # ══════════════════════════════════════════════════════════════
    #   📢 نظام الإذاعة
    # ══════════════════════════════════════════════════════════════
    async def admin_broadcast_menu(self, update, ctx):
        if not self._is_admin(update.effective_user.id):
            await self.safe_ans(update.callback_query, "❌"); return
        kb = InlineKeyboardMarkup([
            [btn("📢 رسالة جماعية للجميع",     "admin_broadcast_all")],
            [btn("📢 إرسال إعلان",              "admin_broadcast_announce")],
            [btn("📢 إرسال تحديث",              "admin_broadcast_update")],
            [btn("⭐ إرسال للمشتركين فقط",      "admin_broadcast_subscribed")],
            [btn("🔙 رجوع", "admin_panel")]
        ])
        await self.safe_edit(update.callback_query, "📢 **نظام الإذاعة**\nاختر نوع الإرسال:", kb)

    async def admin_broadcast(self, update, ctx):
        ctx.user_data["state"]          = "ADMIN_BROADCAST"
        ctx.user_data["broadcast_type"] = "all"
        await self.safe_edit(update.callback_query, "📢 أرسل رسالة الإذاعة:", back("admin_broadcast_menu"))

    async def admin_broadcast_all(self, update, ctx):
        ctx.user_data["state"]          = "ADMIN_BROADCAST"
        ctx.user_data["broadcast_type"] = "all"
        await self.safe_edit(update.callback_query, "📢 أرسل الرسالة الجماعية:", back("admin_broadcast_menu"))

    async def admin_broadcast_announce(self, update, ctx):
        ctx.user_data["state"]          = "ADMIN_BROADCAST"
        ctx.user_data["broadcast_type"] = "announce"
        await self.safe_edit(update.callback_query, "📢 أرسل نص الإعلان:", back("admin_broadcast_menu"))

    async def admin_broadcast_update(self, update, ctx):
        ctx.user_data["state"]          = "ADMIN_BROADCAST"
        ctx.user_data["broadcast_type"] = "update"
        await self.safe_edit(update.callback_query, "📢 أرسل نص التحديث:", back("admin_broadcast_menu"))

    async def admin_broadcast_subscribed(self, update, ctx):
        ctx.user_data["state"]          = "ADMIN_BROADCAST"
        ctx.user_data["broadcast_type"] = "subscribed"
        await self.safe_edit(update.callback_query, "⭐ أرسل الرسالة للمشتركين:", back("admin_broadcast_menu"))

    async def handle_broadcast(self, update, ctx):
        if ctx.user_data.get("state") != "ADMIN_BROADCAST": return
        msg    = update.message.text or ""
        btype  = ctx.user_data.pop("broadcast_type", "all")
        ctx.user_data.pop("state", None)
        if btype == "subscribed":
            users = self.db.fetch_all("SELECT user_id FROM users WHERE subscription_end >= date('now')")
        else:
            users = self.db.fetch_all("SELECT user_id FROM users")
        prefix = {"all": "📢 إذاعة:\n", "announce": "📣 إعلان:\n", "update": "🔔 تحديث:\n"}.get(btype, "")
        full_msg = prefix + msg
        ok = fail = 0
        status_msg = await update.message.reply_text(
            f"📤 جاري الإرسال لـ {len(users)} مستخدم...")
        for i, u in enumerate(users):
            try:
                await update.message.bot.send_message(
                    u["user_id"], full_msg,
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=True)
                ok += 1
            except Exception:
                fail += 1
            if (i + 1) % 20 == 0:
                try:
                    await status_msg.edit_text(
                        f"📤 جاري الإرسال... {i+1}/{len(users)}")
                except Exception:
                    pass
            await asyncio.sleep(0.08)
        try:
            await status_msg.edit_text(
                f"✅ اكتملت الإذاعة\n📤 أُرسلت: {ok} | ❌ فشل: {fail}")
        except Exception:
            await update.message.reply_text(
                f"✅ اكتملت الإذاعة\n📤 أُرسلت: {ok} | ❌ فشل: {fail}")

    # ══════════════════════════════════════════════════════════════
    #   🤖 إدارة البوت
    # ══════════════════════════════════════════════════════════════
    async def admin_bot_control(self, update, ctx):
        if not self._is_admin(update.effective_user.id):
            await self.safe_ans(update.callback_query, "❌"); return
        kb = InlineKeyboardMarkup([
            [btn("🔄 إعادة تشغيل البوت",      "admin_restart"),
             btn("⏸ إيقاف البوت",            "admin_stop_bot")],
            [btn("▶️ تشغيل البوت",            "admin_start_bot")],
            [btn("🧹 تنظيف الجلسات المنتهية", "admin_clean_sessions")],
            [btn("📜 عرض اللوج",             "admin_error_log")],
            [btn("🔙 رجوع", "admin_panel")]
        ])
        await self.safe_edit(update.callback_query, "🤖 **إدارة البوت**\nاختر الإجراء:", kb)

    async def admin_restart(self, update, ctx):
        await self.safe_edit(update.callback_query, "🔄 **جاري إعادة التشغيل...**")
        await asyncio.sleep(1)
        os.execv(sys.executable, [sys.executable] + sys.argv)

    async def admin_stop_bot(self, update, ctx):
        await self.safe_edit(update.callback_query, "⏸ **إيقاف البوت...**")
        await update.callback_query.message.reply_text("✅ تمت المهمة — سيتم إيقاف البوت.")
        await asyncio.sleep(2)
        sys.exit(0)

    async def admin_start_bot(self, update, ctx):
        await self.safe_ans(update.callback_query, "✅ البوت يعمل بالفعل!", True)

    async def admin_clean_sessions(self, update, ctx):
        """تنظيف جلسات المستخدمين منتهي الاشتراك"""
        expired_users = self.db.fetch_all(
            "SELECT user_id FROM users WHERE subscription_end < date('now') OR subscription_end IS NULL")
        count = 0
        for u in expired_users:
            try:
                self.db.execute("UPDATE numbers SET is_active=0 WHERE user_id=?", (u["user_id"],))
                count += 1
            except Exception:
                pass
        await self.safe_ans(update.callback_query, f"✅ تمت المهمة — تم تنظيف جلسات {count} مستخدم", True)
        await update.callback_query.message.reply_text(f"✅ تمت المهمة — تم تعطيل أرقام {count} مستخدم منتهي الاشتراك.")

    async def admin_error_log(self, update, ctx):
        log_path = "logs/bot.log"
        if not os.path.exists(log_path):
            log_path = "logs/error.log"
        if not os.path.exists(log_path):
            await self.safe_edit(update.callback_query, "📭 لا يوجد سجل.", back("admin_bot_control")); return
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()[-30:]
        text = "📜 **آخر السجلات:**\n```\n" + "".join(lines)[-3000:] + "\n```"
        await self.safe_edit(update.callback_query, text, back("admin_bot_control"))

    # ══════════════════════════════════════════════════════════════
    #   🛡 نظام الأمان
    # ══════════════════════════════════════════════════════════════
    async def admin_security(self, update, ctx):
        if not self._is_admin(update.effective_user.id):
            await self.safe_ans(update.callback_query, "❌"); return
        kb = InlineKeyboardMarkup([
            [btn("🛡 رادار التهديدات",    "admin_threat_radar")],
            [btn("🚫 كشف السبام",         "admin_spam_detect")],
            [btn("📡 مراقبة الطلبات",     "admin_req_monitor")],
            [btn("🔐 إدارة الصلاحيات",    "admin_manage_perms")],
            [btn("🌐 البروكسي",           "admin_proxy_menu")],
            [btn("🔙 رجوع", "admin_panel")]
        ])
        await self.safe_edit(update.callback_query, "🛡 **نظام الأمان**", kb)

    async def admin_threat_radar(self, update, ctx):
        viols = self.db.fetch_all(
            "SELECT v.user_id,v.number_id,v.reason,v.count,u.first_name FROM violations v LEFT JOIN users u ON v.user_id=u.user_id ORDER BY v.count DESC LIMIT 10")
        text = "🛡️ **رادار التهديدات — أعلى المخالفات:**\n━━━━━━━━━━━━━━━━━━━━━━\n"
        for v in viols:
            text += f"⚠️ {v.get('first_name','—')} (`{v['user_id']}`) — #{v['number_id']}: {v['reason']} x{v['count']}\n"
        if not viols: text += "✅ لا تهديدات."
        await self.safe_edit(update.callback_query, text, back("admin_security"))

    async def admin_spam_detect(self, update, ctx):
        # المستخدمون الذين لديهم مخالفات متعددة
        spam = self.db.fetch_all("""
            SELECT v.user_id, u.first_name, SUM(v.count) as total
            FROM violations v LEFT JOIN users u ON v.user_id=u.user_id
            GROUP BY v.user_id HAVING total > 5 ORDER BY total DESC LIMIT 10""")
        text = "🚫 **كشف السبام — مستخدمون مشبوهون:**\n━━━━━━━━━━━━━━━━━━━━━━\n"
        for s in spam:
            text += f"🔴 {s.get('first_name','—')} (`{s['user_id']}`) — مخالفات: {s['total']}\n"
        if not spam: text += "✅ لا نشاط مشبوه."
        await self.safe_edit(update.callback_query, text, back("admin_security"))

    async def admin_req_monitor(self, update, ctx):
        pub_w  = len(self.pub._campaigns) if self.pub else 0
        fldr_w = len(self.folder._tasks)  if self.folder else 0
        stats  = helpers.get_server_stats()
        text = (f"📡 **مراقبة الطلبات**\n━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🚀 عمليات نشر نشطة: `{pub_w}`\n"
                f"📁 مهام مجلدات: `{fldr_w}`\n"
                f"🖥 CPU: `{stats['cpu']}%`\n"
                f"🧠 RAM: `{stats['mem_pct']}%`")
        await self.safe_edit(update.callback_query, text, back("admin_security"))

    async def admin_manage_perms(self, update, ctx):
        await self.admin_manage_assistants(update, ctx)

    # ══════════════════════════════════════════════════════════════
    #   📡 مراقبة السيرفر
    # ══════════════════════════════════════════════════════════════
    async def admin_server_status(self, update, ctx):
        if not self._is_admin(update.effective_user.id):
            await self.safe_ans(update.callback_query, "❌"); return
        s = helpers.get_server_stats()
        import psutil
        procs = len(psutil.pids())
        cpu_icon  = helpers.health_icon(max(0, 100 - s['cpu']))
        ram_icon  = helpers.health_icon(max(0, 100 - s['mem_pct']))
        disk_icon = helpers.health_icon(max(0, 100 - s['disk_pct']))
        text = (f"📡 **مراقبة السيرفر**\n━━━━━━━━━━━━━━━━━━━━━━\n"
                f"{cpu_icon} CPU: `{s['cpu']}%`\n"
                f"{ram_icon} RAM: `{helpers.fmt_size(s['mem_used'])}` / `{helpers.fmt_size(s['mem_total'])}` ({s['mem_pct']}%)\n"
                f"{disk_icon} DISK: `{helpers.fmt_size(s['disk_used'])}` / `{helpers.fmt_size(s['disk_total'])}` ({s['disk_pct']:.1f}%)\n"
                f"⚙️ العمليات: `{procs}`")
        kb = InlineKeyboardMarkup([
            [btn("🔄 تحديث", "admin_server_status")],
            [btn("🔙 رجوع", "admin_panel")]
        ])
        await self.safe_edit(update.callback_query, text, kb)

    # ══════════════════════════════════════════════════════════════
    #   📂 قاعدة البيانات
    # ══════════════════════════════════════════════════════════════
    async def admin_database_menu(self, update, ctx):
        if not self._is_admin(update.effective_user.id):
            await self.safe_ans(update.callback_query, "❌"); return
        kb = InlineKeyboardMarkup([
            [btn("📤 تصدير قاعدة البيانات",  "admin_export_db")],
            [btn("📥 استيراد قاعدة البيانات", "admin_import_db")],
            [btn("🧹 تنظيف البيانات",         "admin_clean_db")],
            [btn("📊 تحليل البيانات",         "admin_analyze_db")],
            [btn("🔙 رجوع", "admin_panel")]
        ])
        await self.safe_edit(update.callback_query, "📂 **قاعدة البيانات**\nاختر الإجراء:", kb)

    async def admin_export_db(self, update, ctx):
        from utils import DATABASE_PATH
        from utils import create_db_backup
        try:
            data = create_db_backup(DATABASE_PATH)
            buf  = io.BytesIO(data)
            buf.name = f"muharram_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
            await update.callback_query.message.reply_document(
                document=buf, filename=buf.name, caption="✅ تمت المهمة — نسخة احتياطية من قاعدة البيانات")
        except Exception as e:
            await self.safe_edit(update.callback_query, f"❌ فشل: {e}", back("admin_database_menu"))

    async def admin_import_db(self, update, ctx):
        await self.safe_edit(update.callback_query,
            "📥 **استيراد قاعدة البيانات**\n\n⚠️ هذه العملية متقدمة.\nأرسل ملف .db أو تواصل مع المطور.",
            back("admin_database_menu"))

    async def admin_clean_db(self, update, ctx):
        try:
            # حذف السجلات القديمة من activity_logs
            self.db.execute("DELETE FROM activity_logs WHERE created_at < date('now', '-30 days')")
            # تنظيف fetch_history القديمة
            self.db.execute("DELETE FROM fetch_history WHERE updated_at < date('now', '-7 days')")
            await self.safe_ans(update.callback_query, "✅ تمت المهمة — تم تنظيف البيانات القديمة", True)
            await update.callback_query.message.reply_text("✅ تمت المهمة — تم تنظيف البيانات القديمة (30+ يوم).")
        except Exception as e:
            await self.safe_ans(update.callback_query, f"❌ خطأ: {e}", True)

    async def admin_analyze_db(self, update, ctx):
        users   = (self.db.fetch_one("SELECT COUNT(*) as c FROM users") or {}).get("c", 0)
        numbers = (self.db.fetch_one("SELECT COUNT(*) as c FROM numbers") or {}).get("c", 0)
        codes   = (self.db.fetch_one("SELECT COUNT(*) as c FROM subscription_codes") or {}).get("c", 0)
        sessions= (self.db.fetch_one("SELECT COUNT(*) as c FROM numbers WHERE is_active=1") or {}).get("c", 0)
        logs    = (self.db.fetch_one("SELECT COUNT(*) as c FROM activity_logs") or {}).get("c", 0)
        folders = (self.db.fetch_one("SELECT COUNT(*) as c FROM folders") or {}).get("c", 0)
        text    = (f"📊 **تحليل قاعدة البيانات**\n━━━━━━━━━━━━━━━━━━━━━━\n"
                   f"👥 users: `{users}` سجل\n"
                   f"📱 numbers: `{numbers}` سجل (جلسات نشطة: {sessions})\n"
                   f"🎫 subscription_codes: `{codes}` سجل\n"
                   f"📁 folders: `{folders}` سجل\n"
                   f"📋 activity_logs: `{logs}` سجل")
        await self.safe_edit(update.callback_query, text, back("admin_database_menu"))

    # ══════════════════════════════════════════════════════════════
    #   ⚙️ الإعدادات
    # ══════════════════════════════════════════════════════════════
    async def admin_bot_settings(self, update, ctx):
        from utils import SETTINGS
        text = (f"⚙️ **إعدادات البوت**\n━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💰 السعر: `{SETTINGS.get('subscription_price','—')}`\n"
                f"💳 رقم الدفع: `{SETTINGS.get('payment_number','—')}`\n"
                f"🔗 رابط الدعم: `{SETTINGS.get('whatsapp_link','—')}`\n"
                f"⏳ مدة صلاحية الأكواد: `7 أيام` (قبل التفعيل)")
        kb = InlineKeyboardMarkup([
            [btn("💳 تعديل رقم حساب الدفع", "admin_edit_payment"),
             btn("🔗 تعديل رابط الدعم",     "admin_edit_whatsapp")],
            [btn("💰 تعديل السعر",           "admin_edit_price")],
            [btn("⏳ تعديل مدة صلاحية الأكواد", "admin_edit_code_expiry")],
            [btn("👮 إدارة الأدمن",           "admin_manage_assistants")],
            [btn("🔙 رجوع", "admin_panel")]
        ])
        await self.safe_edit(update.callback_query, text, kb)

    async def admin_edit_price(self, update, ctx):
        ctx.user_data["state"]            = "ADMIN_EDIT_PRICE"
        ctx.user_data["admin_edit_field"] = "subscription_price"
        await self.safe_edit(update.callback_query, "💰 أرسل السعر الجديد:", back("admin_bot_settings"))

    async def admin_edit_payment(self, update, ctx):
        ctx.user_data["state"]            = "ADMIN_EDIT_PAYMENT"
        ctx.user_data["admin_edit_field"] = "payment_number"
        await self.safe_edit(update.callback_query, "💳 أرسل رقم حساب الدفع الجديد:", back("admin_bot_settings"))

    async def admin_edit_whatsapp(self, update, ctx):
        ctx.user_data["state"]            = "ADMIN_EDIT_WA"
        ctx.user_data["admin_edit_field"] = "whatsapp_link"
        await self.safe_edit(update.callback_query, "🔗 أرسل رابط الدعم الجديد:", back("admin_bot_settings"))

    async def admin_edit_code_expiry(self, update, ctx):
        await self.safe_edit(update.callback_query,
            "⏳ **تعديل مدة صلاحية الأكواد**\n\nأرسل عدد الأيام لصلاحية الكود قبل الاستخدام:",
            back("admin_bot_settings"))
        ctx.user_data["state"] = "ADMIN_EDIT_CODE_EXPIRY"

    async def handle_admin_edit(self, update, ctx):
        state = ctx.user_data.get("state", "")
        if state not in ("ADMIN_EDIT_PRICE", "ADMIN_EDIT_PAYMENT", "ADMIN_EDIT_WA"): return
        field = ctx.user_data.pop("admin_edit_field", None)
        val   = (update.message.text or "").strip()
        ctx.user_data.pop("state", None)
        if field:
            from utils import SETTINGS
            SETTINGS[field] = val
            await update.message.reply_text(f"✅ تمت المهمة — تم تحديث `{field}` = `{val}`",
                                            parse_mode=ParseMode.MARKDOWN)

    # ══════════════════════════════════════════════════════════════
    #   📝 النصوص والتعليمات
    # ══════════════════════════════════════════════════════════════
    async def admin_edit_texts(self, update, ctx):
        if not self._is_admin(update.effective_user.id):
            await self.safe_ans(update.callback_query, "❌"); return

        default_texts = {
            "welcome_message":    "رسالة البداية",
            "payment_message":    "رسالة الدفع",
            "enter_code_message": "رسالة إدخال الكود",
            "login_message":      "رسالة تسجيل الدخول",
            "logout_message":     "رسالة تسجيل الخروج",
            "help_instructions":  "تعليمات المساعدة",
        }
        # إنشاء النصوص الافتراضية إن لم تكن موجودة
        for key in default_texts:
            if not self.db.fetch_one("SELECT key FROM bot_texts WHERE key=?", (key,)):
                self.db.set_text(key, "")

        texts = self.db.fetch_all("SELECT key,value FROM bot_texts")
        rows  = []
        for t in texts:
            label = default_texts.get(t["key"], t["key"])
            rows.append([btn(f"✏️ {label}", f"edit_text_{t['key']}")])
        rows.append([btn("🔙 رجوع", "admin_panel")])
        await self.safe_edit(update.callback_query, "📝 **النصوص القابلة للتعديل:**", InlineKeyboardMarkup(rows))

    async def edit_text_prompt(self, update, ctx, key):
        current = self.db.get_text(key, "لا يوجد نص")
        ctx.user_data["edit_text_key"] = key
        ctx.user_data["state"]         = "EDIT_TEXT"
        await self.safe_edit(update.callback_query,
            f"✏️ **تعديل:** `{key}`\n\n📋 النص الحالي:\n{current[:200]}\n\nأرسل النص الجديد:",
            back("admin_edit_texts"))

    async def handle_edit_text(self, update, ctx):
        if ctx.user_data.get("state") != "EDIT_TEXT": return
        key = ctx.user_data.pop("edit_text_key", None)
        if key:
            self.db.set_text(key, update.message.text or "")
            await update.message.reply_text("✅ تمت المهمة — تم تحديث النص.")
        ctx.user_data.pop("state", None)

    # ══════════════════════════════════════════════════════════════
    #   🔑 التوكين الاحتياطي
    # ══════════════════════════════════════════════════════════════
    async def admin_backup_token(self, update, ctx):
        if not self._is_admin(update.effective_user.id):
            await self.safe_ans(update.callback_query, "❌"); return
        from utils import SETTINGS
        current_mirror = SETTINGS.get("mirror_token", "")
        text = (f"🔑 **التوكين الاحتياطي**\n━━━━━━━━━━━━━━━━━━━━━━\n"
                f"في حال حظر تيليجرام للتوكين الحالي،\n"
                f"يتم التبديل تلقائياً للتوكين الاحتياطي\n"
                f"مع الاحتفاظ بقاعدة البيانات والجلسات وكل البيانات.\n\n"
                f"📌 التوكين الاحتياطي الحالي:\n`{current_mirror or 'لم يُضبط بعد'}`")
        kb = InlineKeyboardMarkup([
            [btn("➕ إضافة/تعديل التوكين الاحتياطي", "admin_set_mirror_token")],
            [btn("🔄 تفعيل التوكين الاحتياطي الآن",  "admin_activate_mirror")],
            [btn("🔙 رجوع", "admin_panel")]
        ])
        await self.safe_edit(update.callback_query, text, kb)

    async def admin_set_mirror_token(self, update, ctx):
        ctx.user_data["state"] = "ADMIN_SET_MIRROR_TOKEN"
        await self.safe_edit(update.callback_query,
            "🔑 أرسل التوكين الاحتياطي الجديد:\n(مثال: `1234567890:AABBCCddEEff...`)",
            back("admin_backup_token"))

    async def handle_set_mirror_token(self, update, ctx):
        if ctx.user_data.get("state") != "ADMIN_SET_MIRROR_TOKEN": return
        token = (update.message.text or "").strip()
        ctx.user_data.pop("state", None)
        if not token or ":" not in token:
            await update.message.reply_text("❌ التوكين غير صالح."); return
        from utils import SETTINGS
        SETTINGS["mirror_token"] = token
        # حفظ التوكين في قاعدة البيانات
        self.db.set_text("mirror_token", token)
        await update.message.reply_text("✅ تمت المهمة — تم حفظ التوكين الاحتياطي.")

    async def admin_activate_mirror(self, update, ctx):
        from utils import SETTINGS
        mirror = SETTINGS.get("mirror_token", "") or self.db.get_text("mirror_token", "")
        if not mirror:
            await self.safe_ans(update.callback_query, "❌ لا يوجد توكين احتياطي مضبوط!", True); return
        # كتابة التوكين الجديد في ملف config
        config_path = os.path.join(os.path.dirname(__file__), "..", "config.py")
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                content = f.read()
            import re
            old_token = SETTINGS.get("BOT_TOKEN_CURRENT", "")
            # استبدال التوكين الحالي بالاحتياطي
            content_new = re.sub(
                r'BOT_TOKEN\s*=\s*"[^"]*"',
                f'BOT_TOKEN = "{mirror}"',
                content)
            with open(config_path, "w", encoding="utf-8") as f:
                f.write(content_new)
            await self.safe_edit(update.callback_query,
                f"✅ **تمت المهمة**\n\n"
                f"🔄 تم تفعيل التوكين الاحتياطي.\n"
                f"🔑 التوكين الجديد: `{mirror[:20]}...`\n\n"
                f"⚡ سيتم إعادة التشغيل الآن لتطبيق التغييرات.")
            await asyncio.sleep(2)
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception as e:
            await self.safe_ans(update.callback_query, f"❌ فشل: {e}", True)

    # ══════════════════════════════════════════════════════════════
    #   مراقبة النشاط المباشر القديمة (للتوافق)
    # ══════════════════════════════════════════════════════════════
    async def admin_manage_users_compat(self, update, ctx):
        await self.admin_list_users(update, ctx)

    # ══════════════════════════════════════════════════════════════
    #   🌐 البروكسي
    # ══════════════════════════════════════════════════════════════
    async def admin_proxy_menu(self, update, ctx):
        proxies = self.db.get_active_proxies()
        text = "🌐 **البروكسي**\n━━━━━━━━━━━━━━━━━━━━━━\n"
        for p in proxies:
            text += f"🔹 #{p['id']}: {p['proxy_string'][:40]}\n"
        if not proxies: text += "لا توجد بروكسيات."
        await self.safe_edit(update.callback_query, text,
            InlineKeyboardMarkup([
                [btn("➕ إضافة بروكسي",    "admin_add_proxy")],
                [btn("🔄 تفعيل/تعطيل",     "admin_toggle_proxy")],
                [btn("🔙 رجوع", "admin_security")]
            ]))

    async def admin_add_proxy_prompt(self, update, ctx):
        ctx.user_data["state"] = "ADD_PROXY"
        await self.safe_edit(update.callback_query,
            "🌐 أرسل بروكسي بصيغة:\n`socks5://user:pass@host:port`",
            back("admin_proxy_menu"))

    async def handle_add_proxy(self, update, ctx):
        if ctx.user_data.get("state") != "ADD_PROXY": return
        s = (update.message.text or "").strip()
        ctx.user_data.pop("state", None)
        if self.db.add_proxy(s):
            await update.message.reply_text("✅ تمت المهمة — تمت إضافة البروكسي.")
        else:
            await update.message.reply_text("❌ فشل أو موجود مسبقاً.")

    async def admin_toggle_proxy_prompt(self, update, ctx):
        proxies = self.db.fetch_all("SELECT id,proxy_string,is_active FROM proxies")
        rows = [[btn(f"{'✅' if p['is_active'] else '❌'} #{p['id']} {p['proxy_string'][:30]}",
                     f"toggle_proxy_{p['id']}")] for p in proxies]
        rows.append([btn("🔙 رجوع", "admin_proxy_menu")])
        await self.safe_edit(update.callback_query, "اختر للتبديل:", InlineKeyboardMarkup(rows))

    async def toggle_proxy(self, update, ctx, pid):
        self.db.toggle_proxy(pid)
        await self.safe_ans(update.callback_query, "✅ تمت المهمة")
        await self.admin_toggle_proxy_prompt(update, ctx)

    # ══════════════════════════════════════════════════════════════
    #   🤝 المساعدون
    # ══════════════════════════════════════════════════════════════
    async def admin_manage_assistants(self, update, ctx):
        assts = self.db.get_assistants()
        text  = "🤝 **المساعدون:**\n━━━━━━━━━━━━━━━━━━━━━━\n"
        for a in assts:
            text += f"👤 {a.get('first_name', '—')} (`{a['user_id']}`)\n"
        if not assts: text += "لا مساعدون."
        await self.safe_edit(update.callback_query, text,
            InlineKeyboardMarkup([
                [btn("➕ إضافة مساعد", "admin_add_assistant")],
                [btn("🔙 رجوع", "admin_bot_settings")]
            ]))

    async def admin_add_assistant_prompt(self, update, ctx):
        ctx.user_data["state"] = "ADMIN_ADD_ASSISTANT"
        await self.safe_edit(update.callback_query,
            "📝 أرسل ID المساعد الجديد (رقم):", back("admin_manage_assistants"))

    async def handle_add_assistant(self, update, ctx):
        if ctx.user_data.get("state") != "ADMIN_ADD_ASSISTANT": return
        txt = (update.message.text or "").strip()
        ctx.user_data.pop("state", None)
        if not txt.isdigit():
            await update.message.reply_text("❌ أرسل ID رقمي صحيح."); return
        self.db.add_assistant(int(txt), update.effective_user.id)
        await update.message.reply_text(f"✅ تمت المهمة — تم إضافة المساعد `{txt}`.")

