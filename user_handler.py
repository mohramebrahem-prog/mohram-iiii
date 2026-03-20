# -*- coding: utf-8 -*-
import asyncio, io, logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
import helpers
from ad_protector import AdProtector

logger = logging.getLogger(__name__)

def btn(text, cb): return InlineKeyboardButton(text, callback_data=cb)
def back(cb):      return InlineKeyboardMarkup([[btn("🔙 رجوع", cb)]])

def main_kb(uid=None, admin_ids=[]):
    rows = [
        [btn("📱 إدارة الأرقام","manage_numbers"),      btn("🚀 محرك النشر","publish_engine")],
        [btn("⚡️ النشر السريع (Turbo)","flash_menu"),                                        ],
        [btn("📁 إدارة المجلدات والروابط","folder_dashboard"), btn("🔍 جلب الروابط","fetch_links_menu")],
        [btn("🛡️ حماية الإعلان","ad_protect_menu"),    btn("💬 الرد التلقائي","auto_reply")],
        [btn("👤 حسابي","my_account"),                   btn("❓ مساعدة","help")],
        [btn("📚 شرح البوت","bot_tutorial")],
        [btn("🛡️ قسم الإعلانات الذكي","eng_smart_ads_menu"),
         btn("📹 فيديوهات تعليمية","vid_menu")],
        [btn("🚪 تسجيل الخروج / نقل الاشتراك","sm_logout")],
    ]
    if uid and uid in admin_ids:
        rows.append([btn("⚙️ لوحة الأدمن","admin_panel")])
    return InlineKeyboardMarkup(rows)

class UserHandlers:
    def __init__(self, db, auth_svc, pub_svc, folder_svc, fetch_svc, admin_ids, admin_handlers=None):
        self.db        = db
        self.auth      = auth_svc
        self.pub       = pub_svc
        self.folder    = folder_svc
        self.fetch     = fetch_svc
        self.admin_ids = admin_ids
        self.admin_hdl = admin_handlers

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

    async def send(self, update, text, kb=None, pm=ParseMode.MARKDOWN):
        kw = {"parse_mode": pm}
        if kb: kw["reply_markup"] = kb
        if update.callback_query:
            await self.safe_edit(update.callback_query, text, kb, pm)
        else:
            await update.message.reply_text(text, **kw)

    async def start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        u = update.effective_user
        self.db.get_or_create_user(u.id, u.username, u.first_name)
        if ctx.args and ctx.args[0].startswith("ref_"):
            ctx.user_data["pending_ref"] = ctx.args[0][4:]
        if self.db.is_subscribed(u.id, self.admin_ids):
            await self.show_main(update, ctx)
        else:
            await self.show_sub_required(update, ctx)

    async def show_main(self, update, ctx):
        uid   = update.effective_user.id
        stats = helpers.dashboard_stats(uid, self.db)
        if stats:
            text = (
                "📊 **لوحة المعلومات**\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🆔 المعرف: `{uid}`\n"
                f"📅 الاشتراك: `{stats['subscription']}` | متبقي: **{stats['remaining_days']} يوم**\n"
                f"📱 الأرقام: **{stats['numbers']}/10**\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📤 نشر: `{stats['posts']}` | 🔍 جلب: `{stats['fetches']}`"
            )
        else:
            text = "⚠️ تعذّر جلب البيانات."
        await self.send(update, text, main_kb(uid, self.admin_ids))

    async def show_sub_required(self, update, ctx):
        from config import SETTINGS
        kb = InlineKeyboardMarkup([
            [btn("🔑 إدخال كود الاشتراك","enter_sub_code")],
            [InlineKeyboardButton("📞 الدعم", url=SETTINGS["whatsapp_link"])]
        ])
        text = (
            "🌟 **مرحباً في بوت محرم!**\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "🚀 نشر ذكي • 📁 مجلدات تيليجرام • 🔍 جلب روابط\n\n"
            "🔒 جميع الجلسات مشفرة بـ AES-256\n"
            "⚡ نظام حماية تلقائي من الحظر\n\n"
            "⬇️ أرسل كود الاشتراك أو تواصل مع الدعم"
        )
        await self.send(update, text, kb)

    async def enter_code_prompt(self, update, ctx):
        await self.safe_edit(update.callback_query, "🔑 **أرسل كود الاشتراك:**", back("main_menu"))
        ctx.user_data["state"] = "WAIT_CODE"

    async def handle_sub_code(self, update, ctx):
        if ctx.user_data.get("state") != "WAIT_CODE": return
        code = (update.message.text or "").strip()
        # فحص إذا كان كود نقل (Transfer Code)
        if code.startswith("TR-"):
            ctx.user_data.pop("state", None)
            await ctx.bot_data["sm_hdl"].user_use_transfer_code(update, ctx, code)
            return
        uid  = update.effective_user.id
        days = self.db.use_code(code, uid)
        if days:
            ref = ctx.user_data.pop("pending_ref", None)
            if ref:
                r = self.db.fetch_one("SELECT user_id FROM users WHERE referral_code=?", (ref,))
                if r:
                    self.db.execute("UPDATE users SET bonus_days=bonus_days+3 WHERE user_id=?", (r["user_id"],))
            ctx.user_data.pop("state", None)
            await update.message.reply_text(f"✅ **تم التفعيل!** مدة الاشتراك: **{days} يوم**",
                                            parse_mode=ParseMode.MARKDOWN)
            await self.show_main(update, ctx)
            if self.admin_hdl:
                await self.admin_hdl.notify_code_activation(code, uid)
        else:
            await update.message.reply_text("❌ كود غير صالح أو مستخدم مسبقاً.")

    # ══ إدارة الأرقام ═════════════════════════════════════════════
    async def manage_numbers_menu(self, update, ctx):
        await self.safe_edit(update.callback_query,
            "📱 **إدارة الأرقام**\n━━━━━━━━━━━━━━━━━━━━━━",
            InlineKeyboardMarkup([
                [btn("➕ إضافة رقم","add_number")],
                [btn("📋 عرض أرقامي","list_numbers"), btn("🔍 فحص رقم","check_number")],
                [btn("🗑️ حذف رقم","delete_number"),   btn("🔄 تبديل رقم","switch_number")],
                [btn("🔒 تعليمات الأمان","security_tips_numbers")],
                [btn("🔙 رجوع","main_menu")]
            ]))

    async def add_number_start(self, update, ctx):
        uid  = update.effective_user.id
        nums = self.db.get_user_numbers(uid)
        if len(nums) >= 10:
            await self.safe_edit(update.callback_query, "❌ وصلت للحد الأقصى (10 أرقام).", back("manage_numbers"))
            return
        await self.safe_edit(update.callback_query,
            "📞 **إضافة رقم**\n━━━━━━━━━━━━━━━━━━━━━━\n"
            "أرسل رقم الهاتف بالصيغة الدولية:\n`967XXXXXXXXX`\n\n"
            "🔒 سيتم تشفير جلسة الحساب تلقائياً.",
            back("manage_numbers"))
        ctx.user_data["state"] = "WAIT_PHONE"

    async def handle_phone(self, update, ctx):
        if ctx.user_data.get("state") not in ("WAIT_PHONE","WAIT_PHONE_SWITCH"): return
        phone   = update.message.text.strip().replace("+","")
        uid     = update.effective_user.id
        is_sw   = ctx.user_data.get("state") == "WAIT_PHONE_SWITCH"
        old_nid = ctx.user_data.pop("switch_nid", None) if is_sw else None
        msg = await update.message.reply_text("📡 **جاري الاتصال...**", parse_mode=ParseMode.MARKDOWN)
        ok, err = await self.auth.start_login(uid, phone, number_id=old_nid)
        if ok:
            await msg.edit_text("📲 **تم إرسال كود التحقق!**\nأرسل الكود (يمكن بمسافات: `1 2 3 4 5`)",
                                parse_mode=ParseMode.MARKDOWN)
            ctx.user_data["state"] = "WAIT_CODE_AUTH"
        else:
            await msg.edit_text(f"❌ فشل: {err}")
            ctx.user_data.pop("state", None)

    async def handle_code_auth(self, update, ctx):
        if ctx.user_data.get("state") != "WAIT_CODE_AUTH": return
        code   = helpers.clean_phone_code(update.message.text.strip())
        uid    = update.effective_user.id
        msg    = await update.message.reply_text("🔐 **جاري التحقق...**", parse_mode=ParseMode.MARKDOWN)
        result = await self.auth.submit_code(uid, code)
        if result[0] is True:
            me = result[1]
            await msg.edit_text(f"✅ **تمت الإضافة بنجاح!**\n📱 `{me.phone}`\n👤 {me.first_name}",
                                reply_markup=back("main_menu"), parse_mode=ParseMode.MARKDOWN)
            ctx.user_data.pop("state", None)
        elif result[0] == "2fa":
            await msg.edit_text("🔐 **أدخل كلمة مرور التحقق بخطوتين:**", parse_mode=ParseMode.MARKDOWN)
            ctx.user_data["state"] = "WAIT_PASS"
        else:
            await msg.edit_text(f"❌ {result[1]}")
            ctx.user_data.pop("state", None)

    async def handle_password(self, update, ctx):
        if ctx.user_data.get("state") != "WAIT_PASS": return
        uid = update.effective_user.id
        msg = await update.message.reply_text("🔐 جاري التحقق...", parse_mode=ParseMode.MARKDOWN)
        ok, me = await self.auth.submit_password(uid, update.message.text.strip())
        if ok:
            await msg.edit_text(f"✅ **تمت الإضافة!**\n📱 `{me.phone}`", parse_mode=ParseMode.MARKDOWN)
        else:
            await msg.edit_text(f"❌ {me}")
        ctx.user_data.pop("state", None)

    async def list_numbers(self, update, ctx):
        uid  = update.effective_user.id
        nums = self.db.get_user_numbers(uid)
        if not nums:
            await self.safe_edit(update.callback_query, "📭 لا توجد أرقام.", back("manage_numbers"))
            return
        lines = ["📋 **أرقامك:**\n━━━━━━━━━━━━━━━━━━━━━━"]
        for n in nums:
            dot = helpers.status_dot(n["is_active"], n["is_busy"])
            h   = helpers.health_icon(n["health"])
            lines.append(f"{dot} `{n['phone']}` {h} صحة:{n['health']}%")
        await self.safe_edit(update.callback_query, "\n".join(lines), back("manage_numbers"))

    async def check_number_start(self, update, ctx):
        uid  = update.effective_user.id
        nums = [n for n in self.db.get_user_numbers(uid) if n["is_active"]]
        if not nums:
            await self.safe_edit(update.callback_query, "📭 لا توجد أرقام نشطة.", back("manage_numbers"))
            return
        rows = [[btn(f"🔍 {n['phone']}", f"check_number_do_{n['id']}")] for n in nums]
        rows.append([btn("🔙 رجوع","manage_numbers")])
        await self.safe_edit(update.callback_query, "اختر رقماً للفحص:", InlineKeyboardMarkup(rows))

    async def check_number_do(self, update, ctx, nid):
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        n = self.db.get_number(nid)
        if not n:
            await self.safe_edit(update.callback_query, "❌ الرقم غير موجود.", back("manage_numbers"))
            return
        await self.safe_edit(update.callback_query, "🔍 **جاري الفحص...**")
        proxy = helpers.parse_proxy(n.get("proxy")) if n.get("proxy") else None
        c = TelegramClient(StringSession(n["session_string"]), self.auth.api_id, self.auth.api_hash,
                           proxy=proxy, device_model=n.get("device_model"), system_version=n.get("system_version"))
        try:
            await asyncio.wait_for(c.connect(), timeout=10)
            if not await asyncio.wait_for(c.is_user_authorized(), timeout=5):
                await self.safe_edit(update.callback_query, "❌ الجلسة منتهية، أعد الإضافة.", back("manage_numbers"))
                return
            me = await asyncio.wait_for(c.get_me(), timeout=5)
            h  = helpers.health_icon(n["health"])
            text = (f"✅ **الرقم سليم**\n━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"📱 `{me.phone}`\n👤 {me.first_name}\n"
                    f"{h} الصحة: {n['health']}%\n"
                    f"📲 {n.get('device_model','—')} / {n.get('system_version','—')}")
        except asyncio.TimeoutError:
            text = "⌛ انتهت المهلة"
        except Exception as e:
            text = f"❌ فشل الاتصال: {e}"
        finally:
            try: await c.disconnect()
            except Exception: pass
        await self.safe_edit(update.callback_query, text, back("manage_numbers"))

    async def delete_number_start(self, update, ctx):
        uid  = update.effective_user.id
        nums = self.db.get_user_numbers(uid)
        if not nums:
            await self.safe_edit(update.callback_query, "📭 لا توجد أرقام.", back("manage_numbers"))
            return
        rows = [[btn(f"🗑️ {n['phone']}", f"delete_number_confirm_{n['id']}")] for n in nums]
        rows.append([btn("🔙 رجوع","manage_numbers")])
        await self.safe_edit(update.callback_query, "اختر الرقم للحذف:", InlineKeyboardMarkup(rows))

    async def delete_number_confirm(self, update, ctx, nid):
        ctx.user_data["del_nid"] = nid
        await self.safe_edit(update.callback_query, "⚠️ **تأكيد الحذف** — هل أنت متأكد؟",
            InlineKeyboardMarkup([[btn("✅ نعم احذف","delete_number_final"),
                                   btn("❌ لا","manage_numbers")]]))

    async def delete_number_final(self, update, ctx):
        nid = ctx.user_data.pop("del_nid", None)
        if nid:
            self.db.execute("DELETE FROM numbers WHERE id=? AND user_id=?", (nid, update.effective_user.id))
        await self.safe_edit(update.callback_query, "✅ تم الحذف.", back("main_menu"))

    async def switch_number_start(self, update, ctx):
        uid  = update.effective_user.id
        nums = [n for n in self.db.get_user_numbers(uid) if n["is_active"]]
        if not nums:
            await self.safe_edit(update.callback_query, "📭 لا توجد أرقام.", back("manage_numbers"))
            return
        rows = [[btn(f"🔄 {n['phone']}", f"switch_number_select_{n['id']}")] for n in nums]
        rows.append([btn("🔙 رجوع","manage_numbers")])
        await self.safe_edit(update.callback_query, "اختر الرقم للاستبدال:", InlineKeyboardMarkup(rows))

    async def switch_number_select(self, update, ctx, nid):
        ctx.user_data["switch_nid"] = nid
        n = self.db.get_number(nid)
        phone = n['phone'] if n else str(nid)
        await self.safe_edit(update.callback_query,
            f"⚠️ سيتم استبدال `{phone}` — لن تفقد اشتراكك.",
            InlineKeyboardMarkup([[btn("✅ تأكيد","switch_number_confirm"),
                                   btn("❌ إلغاء","manage_numbers")]]))

    async def switch_number_confirm(self, update, ctx):
        nid = ctx.user_data.get("switch_nid")
        uid = update.effective_user.id
        if nid:
            self.db.execute("DELETE FROM numbers WHERE id=? AND user_id=?", (nid, uid))
        await self.safe_edit(update.callback_query, "📞 أرسل رقم الهاتف الجديد:")
        ctx.user_data["state"] = "WAIT_PHONE_SWITCH"

    async def security_tips_numbers(self, update, ctx):
        await self.safe_edit(update.callback_query,
            "🔒 **تعليمات الأمان**\n━━━━━━━━━━━━━━━━━━━━━━\n"
            "• استخدم أرقاماً ثانوية\n"
            "• فعّل التحقق بخطوتين\n"
            "• افحص الأرقام بشكل دوري\n"
            "• عند التحذير توقف فوراً",
            back("manage_numbers"))

    # ══ النشر ════════════════════════════════════════════════════
    async def publish_engine_menu(self, update, ctx):
        uid  = update.effective_user.id
        prog = await self.pub.get_progress(uid)
        s    = self.db.fetch_one("SELECT min_delay,max_delay,deduplicate FROM settings WHERE user_id=?", (uid,))
        if not s: s = {"min_delay":30,"max_delay":60,"deduplicate":1}
        sel_ids    = ctx.user_data.get("pub_selected_numbers", [])
        sel_ad_ids = ctx.user_data.get("pub_selected_ads", [])
        all_nums   = [n for n in self.db.get_user_numbers(uid) if n["is_active"]]
        all_ads    = self.db.fetch_all("SELECT id FROM ads WHERE user_id=?", (uid,))
        sel_num_cnt = len(sel_ids)  if sel_ids  else len(all_nums)
        sel_ad_cnt  = len(sel_ad_ids) if sel_ad_ids else len(all_ads)

        if prog and prog.get("running"):
            dot       = "🟡" if prog.get("paused") else "🟢"
            state_txt = "⏸️ متوقف مؤقتاً" if prog.get("paused") else "♾️ يعمل"
            last_log  = "\n".join(prog.get("log",[])[-3:])
            fr = prog.get("fail_reasons", {})
            fr_txt = " | ".join(f"{r.split()[0]}:{c}" for r, c in
                                sorted(fr.items(), key=lambda x: -x[1])[:3]) if fr else ""
            elapsed_m = prog.get("elapsed",0) // 60
            elapsed_s = prog.get("elapsed",0) % 60
            stats_txt = (
                f"\n━━━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ ناجح: **{prog.get('success',0)}** | ❌ فشل: **{prog.get('fail',0)}**\n"
                f"⏱️ {elapsed_m}د {elapsed_s}ث"
                + (f"\n📋 {last_log}" if last_log else ""))
        else:
            dot = "🔴"; state_txt = "غير نشط"; stats_txt = ""

        text = (f"🚀 **محرك النشر** {dot} {state_txt}"
                f"{stats_txt}\n━━━━━━━━━━━━━━━━━━━━━━\n"
                f"⏱️ {s['min_delay']}–{s['max_delay']}ث | "
                f"📱 {sel_num_cnt} رقم | 📝 {sel_ad_cnt} إعلان")

        if prog and prog.get("running"):
            kb = InlineKeyboardMarkup([
                [btn("⏸️ إيقاف مؤقت","publish_pause"), btn("⏹️ إيقاف كلي","publish_stop")],
                [btn("📊 إحصائيات","pub_stats"),        btn("▶️ استئناف","publish_resume")],
                [btn("🔙 رجوع","main_menu")]
            ])
        else:
            kb = InlineKeyboardMarkup([
                [btn("▶️ بدء النشر","publish_start")],
                [btn("📝 إعلاناتي","publish_ads_menu"), btn("⚙️ الإعدادات","publish_settings_menu")],
                [btn("📱 اختيار الأرقام","pub_select_numbers"), btn("📝 اختيار الإعلانات","pub_select_ads")],
                [btn("🧠 نشر ذكي","smart_publish_menu"), btn("📚 نصائح","publish_safety_tips")],
                [btn("🔙 رجوع","main_menu")]
            ])
        await self.safe_edit(update.callback_query, text, kb)

    async def publish_start(self, update, ctx):
        uid = update.effective_user.id
        s   = self.db.fetch_one("SELECT min_delay,max_delay,deduplicate FROM settings WHERE user_id=?", (uid,))
        if not s: s = {"min_delay":30,"max_delay":60}
        selected_numbers = ctx.user_data.get("pub_selected_numbers",[])
        selected_ads     = ctx.user_data.get("pub_selected_ads",[])
        ok, msg = await self.pub.start_publish(uid, s, selected_numbers, selected_ads)
        await self.safe_ans(update.callback_query, msg, not ok)
        await self.publish_engine_menu(update, ctx)

    async def publish_stop(self, update, ctx):
        ok = await self.pub.stop_publish(update.effective_user.id)
        await self.safe_ans(update.callback_query, "⏹️ تم الإيقاف" if ok else "⚠️ لا يوجد نشر", True)
        await self.publish_engine_menu(update, ctx)

    async def publish_pause(self, update, ctx):
        ok = await self.pub.pause_publish(update.effective_user.id)
        await self.safe_ans(update.callback_query, "⏸️ إيقاف مؤقت" if ok else "⚠️ لا يوجد نشر", True)

    async def publish_resume(self, update, ctx):
        ok = await self.pub.resume_publish(update.effective_user.id)
        await self.safe_ans(update.callback_query, "▶️ استُؤنف" if ok else "⚠️", True)

    async def pub_stats(self, update, ctx):
        uid  = update.effective_user.id
        prog = await self.pub.get_progress(uid)
        if not prog:
            await self.safe_edit(update.callback_query, "ℹ️ لا يوجد نشر نشط.", back("publish_engine")); return
        ns   = prog.get("num_status", {})
        fr   = prog.get("fail_reasons", {})
        log  = "\n".join(prog.get("log",[])[-8:]) or "—"
        fr_txt = "\n".join(f"  {r}: {c}" for r, c in sorted(fr.items(), key=lambda x: -x[1])[:5]) or "—"
        ns_txt = "\n".join(f"  ...{str(k)[-4:]}: {v}" for k, v in list(ns.items())[:5]) or "—"
        elapsed_m = prog.get("elapsed",0)//60; elapsed_s = prog.get("elapsed",0)%60
        text = (
            f"📊 **إحصائيات النشر**\n━━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ ناجح: `{prog.get('success',0)}`\n❌ فشل: `{prog.get('fail',0)}`\n"
            f"⏳ فلود: `{prog.get('flood',0)}`\n"
            f"⏱️ منقضي: `{elapsed_m}د {elapsed_s}ث`\n\n"
            f"❌ **أسباب الفشل:**\n{fr_txt}\n\n"
            f"📱 **حالة الأرقام:**\n{ns_txt}\n\n"
            f"📋 **آخر النشاطات:**\n{log}")
        await self.safe_edit(update.callback_query, text, back("publish_engine"))

    async def pub_select_numbers(self, update, ctx):
        uid  = update.effective_user.id
        nums = [n for n in self.db.get_user_numbers(uid) if n["is_active"]]
        sel  = ctx.user_data.get("pub_selected_numbers", [])
        rows = []
        for n in nums:
            chk = "✅" if n["id"] in sel else "⬜"
            rows.append([btn(f"{chk} {n['phone']}", f"pub_toggle_num_{n['id']}")])
        rows.append([btn("✔️ تحديد الكل","pub_select_all_nums"), btn("❌ إلغاء الكل","pub_deselect_all_nums")])
        rows.append([btn("🔙 رجوع","publish_engine")])
        await self.safe_edit(update.callback_query, "📱 **اختر أرقام النشر:**", InlineKeyboardMarkup(rows))

    async def pub_toggle_number(self, update, ctx, nid):
        sel = ctx.user_data.get("pub_selected_numbers", [])
        if nid in sel: sel.remove(nid)
        else: sel.append(nid)
        ctx.user_data["pub_selected_numbers"] = sel
        await self.pub_select_numbers(update, ctx)

    async def pub_select_ads(self, update, ctx):
        uid = update.effective_user.id
        ads = self.db.fetch_all("SELECT id,content FROM ads WHERE user_id=?", (uid,))
        sel = ctx.user_data.get("pub_selected_ads", [])
        rows = []
        for ad in ads:
            chk   = "✅" if ad["id"] in sel else "⬜"
            short = (ad["content"][:25]+"…") if len(ad["content"])>25 else ad["content"]
            rows.append([btn(f"{chk} #{ad['id']}: {short}", f"pub_toggle_ad_{ad['id']}")])
        rows.append([btn("🔙 رجوع","publish_engine")])
        await self.safe_edit(update.callback_query, "📝 **اختر الإعلانات:**", InlineKeyboardMarkup(rows))

    async def pub_toggle_ad(self, update, ctx, ad_id):
        sel = ctx.user_data.get("pub_selected_ads", [])
        if ad_id in sel: sel.remove(ad_id)
        else: sel.append(ad_id)
        ctx.user_data["pub_selected_ads"] = sel
        await self.pub_select_ads(update, ctx)

    async def publish_ads_menu(self, update, ctx):
        uid  = update.effective_user.id
        ads  = self.db.fetch_all("SELECT id,content,title FROM ads WHERE user_id=?", (uid,))
        rows = []
        if ads:
            text = "📋 **إعلاناتك:**\n━━━━━━━━━━━━━━━━━━━━━━\n"
            for ad in ads:
                short = (ad["content"][:35]+"…") if len(ad["content"])>35 else ad["content"]
                text += f"🆔{ad['id']}: {short}\n"
                rows.append([btn(f"🗑️ حذف #{ad['id']}", f"publish_delete_ad_{ad['id']}")])
        else:
            text = "📭 لا توجد إعلانات."
        rows.append([btn("➕ إعلان جديد","publish_new_ad")])
        rows.append([btn("🔙 رجوع","publish_engine")])
        await self.safe_edit(update.callback_query, text, InlineKeyboardMarkup(rows))

    async def publish_new_ad_start(self, update, ctx):
        uid   = update.effective_user.id
        count = (self.db.fetch_one("SELECT COUNT(*) as c FROM ads WHERE user_id=?", (uid,)) or {}).get("c",0)
        if count >= 10:
            await self.safe_edit(update.callback_query, "❌ الحد الأقصى 10 إعلانات.", back("publish_ads_menu")); return
        await self.safe_edit(update.callback_query, "📝 **أرسل نص الإعلان الجديد:**", back("publish_ads_menu"))
        ctx.user_data["state"] = "WAIT_AD_TEXT"

    async def publish_save_ad(self, update, ctx):
        if ctx.user_data.get("state") != "WAIT_AD_TEXT": return
        uid = update.effective_user.id
        self.db.execute("INSERT INTO ads(user_id,content) VALUES(?,?)", (uid, update.message.text.strip()))
        ctx.user_data.pop("state", None)
        await update.message.reply_text("✅ تم حفظ الإعلان!", parse_mode=ParseMode.MARKDOWN)

    async def publish_delete_ad(self, update, ctx, ad_id):
        self.db.execute("DELETE FROM ads WHERE id=? AND user_id=?", (ad_id, update.effective_user.id))
        await self.safe_ans(update.callback_query, "✅ تم الحذف.")
        await self.publish_ads_menu(update, ctx)

    async def publish_settings_menu(self, update, ctx):
        uid = update.effective_user.id
        s   = self.db.fetch_one("SELECT min_delay,max_delay,deduplicate FROM settings WHERE user_id=?", (uid,))
        if not s: s = {"min_delay":30,"max_delay":60,"deduplicate":1}
        text = (f"⚙️ **إعدادات النشر**\n━━━━━━━━━━━━━━━━━━━━━━\n"
                f"⏱️ الفاصل: `{s['min_delay']}–{s['max_delay']}` ثانية\n"
                f"🔁 منع التكرار: {'✅' if s['deduplicate'] else '❌'}")
        kb = InlineKeyboardMarkup([
            [btn("⏱️ الفاصل الأدنى","set_pub_min_delay"), btn("⏱️ الفاصل الأقصى","set_pub_max_delay")],
            [btn(f"🔁 منع التكرار: {'تعطيل' if s['deduplicate'] else 'تفعيل'}","toggle_deduplicate")],
            [btn("🔙 رجوع","publish_engine")]
        ])
        await self.safe_edit(update.callback_query, text, kb)

    async def toggle_deduplicate(self, update, ctx):
        uid = update.effective_user.id
        s   = self.db.fetch_one("SELECT deduplicate FROM settings WHERE user_id=?", (uid,))
        nv  = 0 if (s and s["deduplicate"]) else 1
        self.db.execute("UPDATE settings SET deduplicate=? WHERE user_id=?", (nv, uid))
        await self.safe_ans(update.callback_query, f"✅ {'فعّل' if nv else 'عطّل'} منع التكرار")
        await self.publish_settings_menu(update, ctx)

    async def publish_setting_edit_start(self, update, ctx, key):
        ctx.user_data["state"] = f"WAIT_SET_{key}"
        labels = {"min_delay":"الفاصل الأدنى (ث)","max_delay":"الفاصل الأقصى (ث)"}
        await self.safe_edit(update.callback_query,
            f"📝 أرسل القيمة الجديدة لـ **{labels.get(key,key)}**:",
            InlineKeyboardMarkup([[btn("❌ إلغاء","publish_settings_menu")]]))

    async def smart_publish_menu(self, update, ctx):
        await self.safe_edit(update.callback_query,
            "🧠 **النشر الذكي**\n━━━━━━━━━━━━━━━━━━━━━━\nاختر مستوى الأمان:",
            InlineKeyboardMarkup([
                [btn("🟢 عادي (30–60ث)","smart_pub_normal"),
                 btn("🟡 متوسط (60–90ث)","smart_pub_medium"),
                 btn("🔴 عالي (90–180ث)","smart_pub_high")],
                [btn("🔙 رجوع","publish_engine")]
            ]))

    async def smart_publish_start(self, update, ctx, level):
        levels = {"normal":(30,60),"medium":(60,90),"high":(90,180)}
        mn, mx = levels.get(level, (30,60))
        uid = update.effective_user.id
        self.db.execute("UPDATE settings SET min_delay=?,max_delay=?,deduplicate=1 WHERE user_id=?", (mn, mx, uid))
        await self.safe_ans(update.callback_query, f"✅ تم ضبط مستوى {level}: {mn}–{mx}ث")
        await self.publish_engine_menu(update, ctx)

    async def publish_safety_tips(self, update, ctx):
        await self.safe_edit(update.callback_query,
            "📚 **نصائح النشر الآمن**\n━━━━━━━━━━━━━━━━━━━━━━\n"
            "• لا تتجاوز 30 رسالة/يوم لكل حساب\n"
            "• فاصل لا يقل عن 60 ثانية\n"
            "• عند FloodWait توقف فوراً",
            back("publish_engine"))

    # ══════════════════════════════════════════════════════════════
    #   📁 نظام إدارة المجلدات — الشاشة الأولى: لوحة الأرقام
    # ══════════════════════════════════════════════════════════════
    async def folder_dashboard(self, update, ctx):
        """الشاشة الأولى: لوحة أرقام المستخدم مع سعة كل رقم"""
        uid  = update.effective_user.id
        nums = [n for n in self.db.get_user_numbers(uid) if n["is_active"]]
        if not nums:
            await self.safe_edit(update.callback_query,
                "📱 **إدارة المجلدات**\n━━━━━━━━━━━━━━━━━━━━\n"
                "⚠️ لا توجد أرقام مضافة. أضف رقماً أولاً من قائمة الأرقام.",
                back("main_menu"))
            return

        await self.safe_edit(update.callback_query,
            "⏳ **جاري جلب بيانات المجلدات...**\n_يُرجى الانتظار_")

        rows = []
        for n in nums:
            folder_count = await self.folder.get_folder_count(n["id"])
            is_full = folder_count >= 10
            icon = "🔴" if is_full else "🟢"
            full_label = " ممتلئ" if is_full else ""
            phone_short = n["phone"][-7:]
            rows.append([btn(
                f"📱 +{phone_short} | المجلدات: {folder_count}/10 {icon}{full_label}",
                f"folder_number_{n['id']}")])

        rows.append([btn("🔙 رجوع للرئيسية","main_menu")])
        text = (
            "📱 **إدارة أرقامك ومجلداتها**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "اختر الرقم الذي تريد العمل عليه.\n"
            "💡 الحساب العادي يستوعب **10 مجلدات** كحد أقصى."
        )
        await self.safe_edit(update.callback_query, text, InlineKeyboardMarkup(rows))

    # ══ الشاشة الثانية: غرفة عمليات الرقم ════════════════════════
    async def folder_number_control(self, update, ctx, nid):
        """لوحة تحكم رقم محدد"""
        uid = update.effective_user.id
        n   = self.db.get_number(nid)
        if not n:
            await self.safe_edit(update.callback_query, "❌ الرقم غير موجود.", back("folder_dashboard")); return

        ctx.user_data["folder_nid"] = nid

        # إحصائيات الرقم
        folder_count  = await self.folder.get_folder_count(nid)
        db_folders    = self.db.get_number_folders(nid, uid)

        # إجمالي المحادثات من قاعدة البيانات
        total_chats = sum(f.get("channels_count",0) + f.get("groups_count",0) for f in db_folders)

        # مؤشر الأمان
        s = self.db.fetch_one(
            "SELECT join_delay_min, join_delay_max, big_break_duration, groups_per_break "
            "FROM settings WHERE user_id=?", (uid,)) or {}
        jd_min = s.get("join_delay_min", 60)
        jd_max = s.get("join_delay_max", 120)
        bb_dur = s.get("big_break_duration", 10)
        gpb    = s.get("groups_per_break", 20)
        score  = helpers.safety_score(jd_min, jd_max, bb_dur, gpb)
        s_icon = helpers.safety_icon(score)

        phone_short = n["phone"][-7:]
        text = (
            f"⚙️ **لوحة تحكم الرقم: +{phone_short}**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 **إحصائيات الرقم الحالية:**\n"
            f"📂 المجلدات المنشأة: **{folder_count}** من 10\n"
            f"💬 إجمالي المحادثات المسجلة: **{total_chats}** (مجموعات/قنوات)\n\n"
            f"{s_icon} **نسبة الأمان: {score}%**\n"
            f"⏱️ فاصل الانضمام: `{jd_min}–{jd_max}` ث | "
            f"😴 استراحة: كل `{gpb}` مجموعة / `{bb_dur}` د\n\n"
            f"⚠️ _إذا كان الرقم ممتلئاً، احذف مجلدات قديمة لإنشاء مجلدات جديدة._"
        )
        kb = InlineKeyboardMarkup([
            [btn("➕ إنشاء مجلدات جديدة",      f"folder_create_start_{nid}")],
            [btn("📂 عرض وإدارة مجلداتي",      f"folder_list_{nid}")],
            [btn("🧹 تنظيف المجموعات الميتة",  f"folder_clean_{nid}")],
            [btn("⚙️ إعدادات الأمان",          f"folder_safety_settings_{nid}")],
            [btn("🔙 عودة للأرقام","folder_dashboard")]
        ])
        await self.safe_edit(update.callback_query, text, kb)

    # ══ إعدادات الأمان الديناميكي للمجلدات ══════════════════════
    async def folder_safety_settings(self, update, ctx, nid):
        uid = update.effective_user.id
        s   = self.db.fetch_one(
            "SELECT join_delay_min, join_delay_max, big_break_duration, groups_per_break "
            "FROM settings WHERE user_id=?", (uid,)) or {}
        jd_min = s.get("join_delay_min", 60)
        jd_max = s.get("join_delay_max", 120)
        bb_dur = s.get("big_break_duration", 10)
        gpb    = s.get("groups_per_break", 20)
        score  = helpers.safety_score(jd_min, jd_max, bb_dur, gpb)
        s_icon = helpers.safety_icon(score)

        ctx.user_data["folder_safety_nid"] = nid
        text = (
            f"⚙️ **إعدادات الأمان الديناميكي**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{s_icon} **نسبة الأمان الحالية: {score}%**\n\n"
            f"⏱️ **فاصل الانضمام العشوائي:**\n"
            f"  الأدنى: `{jd_min}` ث | الأقصى: `{jd_max}` ث\n\n"
            f"😴 **الاستراحة الكبرى:**\n"
            f"  مدتها: `{bb_dur}` دقيقة\n"
            f"  تُنفَّذ بعد كل: `{gpb}` مجموعة\n\n"
            f"💡 **دليل الإعدادات المثالية:**\n"
            f"• فاصل `120–180ث` + استراحة `15د` كل `15` مجموعة → 🟢 أمان عالي\n"
            f"• فاصل `60–120ث` + استراحة `10د` كل `20` مجموعة → 🟡 أمان متوسط\n"
            f"• فاصل `30–60ث` + استراحة `5د` كل `30` مجموعة → 🔴 خطر حظر"
        )
        kb = InlineKeyboardMarkup([
            [btn("⏱️ الفاصل الأدنى",  f"set_folder_delay_min_{nid}"),
             btn("⏱️ الفاصل الأقصى", f"set_folder_delay_max_{nid}")],
            [btn("😴 مدة الاستراحة",  f"set_folder_break_dur_{nid}"),
             btn("📊 مجموعات/استراحة", f"set_folder_gpb_{nid}")],
            [btn("🟢 آمن (120-180/15د/15)", f"folder_safety_preset_safe_{nid}"),
             btn("🟡 متوسط (60-120/10د/20)", f"folder_safety_preset_med_{nid}")],
            [btn("🔴 سريع (30-60/5د/30)", f"folder_safety_preset_fast_{nid}")],
            [btn("🔙 رجوع", f"folder_number_{nid}")]
        ])
        await self.safe_edit(update.callback_query, text, kb)

    async def folder_safety_preset(self, update, ctx, preset, nid):
        uid = update.effective_user.id
        presets = {
            "safe":  (120, 180, 15, 15),
            "med":   (60,  120, 10, 20),
            "fast":  (30,   60,  5, 30),
        }
        if preset not in presets:
            await self.safe_ans(update.callback_query, "❌ إعداد غير معروف", True); return
        jd_min, jd_max, bb_dur, gpb = presets[preset]
        self.db.execute(
            "UPDATE settings SET join_delay_min=?, join_delay_max=?, "
            "big_break_duration=?, groups_per_break=? WHERE user_id=?",
            (jd_min, jd_max, bb_dur, gpb, uid))
        icons = {"safe": "🟢", "med": "🟡", "fast": "🔴"}
        await self.safe_ans(update.callback_query,
            f"{icons[preset]} تم تطبيق إعداد {preset}", True)
        await self.folder_safety_settings(update, ctx, nid)

    async def folder_safety_set_start(self, update, ctx, field, nid):
        labels = {
            "join_delay_min": "الفاصل الأدنى (ثانية) — مثال: 60",
            "join_delay_max": "الفاصل الأقصى (ثانية) — مثال: 120",
            "big_break_duration": "مدة الاستراحة (دقيقة) — مثال: 10",
            "groups_per_break": "عدد المجموعات قبل الاستراحة — مثال: 20",
        }
        ctx.user_data["state"] = f"WAIT_FOLDER_SAFETY_{field}"
        ctx.user_data["folder_safety_nid"] = nid
        await self.safe_edit(update.callback_query,
            f"📝 أرسل قيمة **{labels.get(field, field)}**:",
            back(f"folder_safety_settings_{nid}"))

    # ══ الشاشة الثالثة: مسار إنشاء مجلدات جديدة ══════════════════
    async def folder_create_start(self, update, ctx, nid):
        """الخطوة 1: اختيار نوع المحتوى"""
        ctx.user_data["folder_nid"] = nid
        n = self.db.get_number(nid)
        phone_short = n["phone"][-7:] if n else str(nid)

        await self.safe_edit(update.callback_query,
            f"🔍 **إنشاء مجلدات — الرقم: +{phone_short}**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "ما نوع المحتوى الذي تريد إضافته للمجلد؟",
            InlineKeyboardMarkup([
                [btn("👥 مجموعات فقط",  f"folder_type_groups_{nid}"),
                 btn("📢 قنوات فقط",    f"folder_type_channels_{nid}")],
                [btn("🔄 الكل",          f"folder_type_all_{nid}")],
                [btn("🔙 رجوع",         f"folder_number_{nid}")]
            ]))

    async def folder_set_type(self, update, ctx, nid, ftype):
        """الخطوة 2: استلام الروابط"""
        ctx.user_data["folder_nid"]  = nid
        ctx.user_data["folder_type"] = ftype
        n = self.db.get_number(nid)
        phone_short = n["phone"][-7:] if n else str(nid)

        type_labels = {"groups":"👥 مجموعات فقط","channels":"📢 قنوات فقط","all":"🔄 الكل"}
        type_lbl = type_labels.get(ftype, ftype)

        await self.safe_edit(update.callback_query,
            f"📤 **أرسل الروابط الآن**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🔢 النوع المختار: **{type_lbl}**\n"
            f"📱 الرقم: `+{phone_short}`\n\n"
            "أرسل الروابط نصاً (كل رابط في سطر) أو ملف `.txt`\n"
            "_(سيقوم النظام بتقسيمها تلقائياً: 100 رابط لكل مجلد)_",
            back(f"folder_create_start_{nid}"))
        ctx.user_data["state"] = "WAIT_FOLDER_LINKS"

    async def handle_folder_links(self, update, ctx):
        """استقبال الروابط وبدء العملية"""
        if ctx.user_data.get("state") != "WAIT_FOLDER_LINKS": return

        uid   = update.effective_user.id
        nid   = ctx.user_data.get("folder_nid")
        ftype = ctx.user_data.get("folder_type", "all")

        if not nid:
            await update.message.reply_text("❌ اختر رقماً أولاً.")
            ctx.user_data.pop("state", None)
            return

        if update.message.document:
            f    = await update.message.document.get_file()
            data = await f.download_as_bytearray()
            text = data.decode("utf-8", errors="ignore")
        else:
            text = update.message.text or ""

        links = helpers.extract_telegram_links(text)
        if not links:
            await update.message.reply_text("❌ لم يتم العثور على روابط تيليجرام.")
            return

        ctx.user_data.pop("state", None)

        # إرسال رسالة التقدم
        n = self.db.get_number(nid)
        phone_short = n["phone"][-7:] if n else str(nid)
        prog_msg = await update.message.reply_text(
            f"⏳ **جاري العمل في الخلفية...**\n"
            f"_(يمكنك استخدام البوت لمهام أخرى)_\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔍 تم استخراج: **{len(links)}** رابط\n"
            f"📱 الرقم: `+{phone_short}`\n"
            f"🔄 جاري التهيئة...",
            parse_mode=ParseMode.MARKDOWN)

        ok, msg = await self.folder.start_create_folders(
            uid, nid, links, ftype,
            progress_msg_id=prog_msg.message_id,
            progress_chat_id=update.effective_chat.id)

        if not ok:
            await prog_msg.edit_text(f"❌ {msg}", parse_mode=ParseMode.MARKDOWN)

    # ══ الشاشة الرابعة: عرض وإدارة المجلدات ══════════════════════
    async def folder_list(self, update, ctx, nid):
        """قائمة المجلدات المحفوظة في قاعدة البيانات"""
        uid = update.effective_user.id
        n   = self.db.get_number(nid)
        phone_short = n["phone"][-7:] if n else str(nid)

        db_folders = self.db.get_number_folders(nid, uid)

        if not db_folders:
            await self.safe_edit(update.callback_query,
                f"📂 **مجلدات الرقم: +{phone_short}**\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "📭 لا توجد مجلدات محفوظة لهذا الرقم.\n"
                "_أنشئ مجلدات جديدة من الخيار أعلاه._",
                back(f"folder_number_{nid}"))
            return

        rows = []
        for f in db_folders:
            name = f.get("folder_name","مجلد")
            ch   = f.get("channels_count",0)
            gr   = f.get("groups_count",0)
            rows.append([btn(f"📁 {name} ({ch}📢+{gr}👥)", f"folder_detail_{f['id']}_{nid}")])

        rows.append([btn("🔙 رجوع", f"folder_number_{nid}")])
        text = (f"📂 **مجلدات الرقم: +{phone_short}**\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "اختر المجلد لعرض تفاصيله أو حذفه:")
        await self.safe_edit(update.callback_query, text, InlineKeyboardMarkup(rows))

    async def folder_detail(self, update, ctx, folder_id, nid):
        """تفاصيل مجلد محدد"""
        uid = update.effective_user.id
        f   = self.db.get_folder(folder_id, uid)
        n   = self.db.get_number(nid)
        phone_short = n["phone"][-7:] if n else str(nid)

        if not f:
            await self.safe_edit(update.callback_query, "❌ المجلد غير موجود.", back(f"folder_list_{nid}"))
            return

        name         = f.get("folder_name","مجلد")
        invite_link  = f.get("invite_link","") or "—"
        ch_count     = f.get("channels_count",0)
        gr_count     = f.get("groups_count",0)
        total_mem    = f.get("total_members",0)
        created_at   = (f.get("created_at","") or "")[:16]

        text = (
            f"📊 **تفاصيل المجلد: [{name}]**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🔗 رابط المجلد: `{invite_link}`\n"
            f"👥 يحتوي على: **{gr_count} مجموعة** | **{ch_count} قناة**\n"
            f"👁️ إجمالي المشتركين: `{total_mem:,}`\n"
            f"📅 تاريخ الإنشاء: `{created_at}`\n\n"
            "⚠️ **ماذا سيحدث عند الحذف؟**\n"
            "🗑️ **حذف المجلد فقط**: يُلغى رابط المجلد، لكن تبقى المحادثات في حسابك.\n"
            "🧹 **حذف + مغادرة**: يُلغى رابط المجلد وتُغادر جميع المحادثات نهائياً."
        )
        kb = InlineKeyboardMarkup([
            [btn("🗑️ حذف المجلد فقط",          f"folder_del_only_{folder_id}_{nid}")],
            [btn("🧹 حذف المجلد + مغادرة المحادثات", f"folder_del_leave_{folder_id}_{nid}")],
            [btn("🔙 رجوع",                      f"folder_list_{nid}")]
        ])
        await self.safe_edit(update.callback_query, text, kb)

    async def folder_delete_only(self, update, ctx, folder_id, nid):
        uid = update.effective_user.id
        ctx.user_data["folder_del_confirm"] = {"fid": folder_id, "nid": nid, "mode": "only"}
        await self.safe_edit(update.callback_query,
            "⚠️ **تأكيد الحذف**\n━━━━━━━━━━━━━━━━━━━━\n"
            "سيُحذف المجلد وينتهي رابطه، لكن المحادثات تبقى في حسابك.\n"
            "هل أنت متأكد؟",
            InlineKeyboardMarkup([
                [btn("✅ نعم، احذف المجلد",    "folder_confirm_delete")],
                [btn("❌ إلغاء",               f"folder_detail_{folder_id}_{nid}")]
            ]))

    async def folder_delete_and_leave(self, update, ctx, folder_id, nid):
        uid = update.effective_user.id
        ctx.user_data["folder_del_confirm"] = {"fid": folder_id, "nid": nid, "mode": "leave"}
        await self.safe_edit(update.callback_query,
            "⚠️ **تأكيد الحذف مع المغادرة**\n━━━━━━━━━━━━━━━━━━━━\n"
            "🔴 سيُحذف المجلد **ويُغادر الرقم** جميع محادثاته!\n"
            "هذا الإجراء لا يمكن التراجع عنه.\n\n"
            "هل أنت متأكد؟",
            InlineKeyboardMarkup([
                [btn("✅ نعم، احذف وغادر",      "folder_confirm_delete")],
                [btn("❌ إلغاء",                f"folder_detail_{folder_id}_{nid}")]
            ]))

    async def folder_confirm_delete(self, update, ctx):
        uid  = update.effective_user.id
        conf = ctx.user_data.pop("folder_del_confirm", None)
        if not conf:
            await self.safe_edit(update.callback_query, "❌ انتهت الجلسة.", back("folder_dashboard")); return

        fid  = conf["fid"]
        nid  = conf["nid"]
        mode = conf["mode"]

        await self.safe_edit(update.callback_query,
            "⏳ **جاري المعالجة...**\n_الرجاء الانتظار_")

        if mode == "only":
            ok, msg = await self.folder.delete_folder_only(uid, nid, fid)
        else:
            ok, msg = await self.folder.delete_folder_and_leave(uid, nid, fid, update.effective_chat.id)

        await self.safe_edit(update.callback_query, msg, back(f"folder_list_{nid}"))

    # ══ الشاشة الخامسة: تنظيف المجموعات الميتة ══════════════════
    async def folder_clean_start(self, update, ctx, nid):
        """صفحة تأكيد التنظيف"""
        n = self.db.get_number(nid)
        phone_short = n["phone"][-7:] if n else str(nid)
        ctx.user_data["folder_nid"] = nid
        await self.safe_edit(update.callback_query,
            f"🧹 **منظف الحساب الذكي**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"📱 الرقم: `+{phone_short}`\n\n"
            "سيقوم النظام بفحص **جميع المجموعات** في هذا الرقم، ومغادرة:\n"
            "• المجموعات التي تم **حظر الرقم** منها.\n"
            "• المجموعات **المحذوفة** أو المُقيَّدة.\n"
            "• _(هذا يساعد في تخفيف الضغط وتحسين أداء الحساب)_",
            InlineKeyboardMarkup([
                [btn(f"🚀 بدء التنظيف الآن",    f"folder_clean_confirm_{nid}")],
                [btn("❌ إلغاء",                f"folder_number_{nid}")]
            ]))

    async def folder_clean_confirm(self, update, ctx, nid):
        uid = update.effective_user.id
        await self.safe_edit(update.callback_query, "⏳ **جاري بدء التنظيف في الخلفية...**")
        asyncio.create_task(
            self.folder.clean_dead_groups(uid, nid, update.effective_chat.id))
        await self.safe_edit(update.callback_query,
            "✅ **بدأ التنظيف في الخلفية!**\n"
            "_ستصلك رسالة بالنتائج عند الانتهاء._",
            back(f"folder_number_{nid}"))

    async def folder_stop_task(self, update, ctx):
        uid = update.effective_user.id
        ok  = self.folder.stop_task(uid)
        await self.safe_ans(update.callback_query, "⏹️ تم إيقاف العملية" if ok else "⚠️ لا توجد عملية نشطة", True)

    # ══ جلب الروابط ═══════════════════════════════════════════════
    async def fetch_links_menu(self, update, ctx):
        uid  = update.effective_user.id
        nid  = ctx.user_data.get("fetch_nid")
        ltyp = ctx.user_data.get("fetch_type","telegram")
        mode = ctx.user_data.get("fetch_mode","messages")
        days = ctx.user_data.get("fetch_days",1)
        dlbl = {1:"آخر 24س",7:"7 أيام",30:"30 يوم",90:"90 يوم"}.get(days,"آخر 24س")
        n_dot = "🟢" if nid else "🔴"
        n_lbl = "محدد" if nid else "لم يُحدد"
        if nid:
            n_obj = self.db.get_number(nid)
            n_lbl = n_obj["phone"] if n_obj else f"#{nid}"
        # حجم ذاكرة الرام المؤقتة
        mem_count = len(self.fetch._temp_links)
        mem_txt   = f"🧠 الذاكرة المؤقتة: `{mem_count}` رابط" if mem_count > 0 else "🧠 الذاكرة المؤقتة: فارغة"
        text = (
            f"🔍 **جلب الروابط — دليل الاستخدام**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{n_dot} الرقم: `{n_lbl}`\n"
            f"📡 النوع: `{ltyp}` | 📅 النطاق: `{dlbl}`\n"
            f"🔎 الوضع: `{mode}`\n"
            f"{mem_txt}\n\n"
            f"💡 **كيف يعمل النظام؟**\n"
            f"• **مجموعاتي**: يجلب روابط المجموعات التي أنت عضو فيها مباشرة.\n"
            f"• **الرسائل**: يفحص محتوى رسائل محادثاتك ويستخرج الروابط.\n"
            f"• **الكل**: يجمع الطريقتين للحصول على أكبر قدر من الروابط.\n\n"
            f"🛡️ النظام يتجاهل الروابط المكررة تلقائياً ويحفظ فقط الجديدة."
        )
        kb = InlineKeyboardMarkup([
            [btn(f"{n_dot} اختيار رقم","fetch_select_number"),
             btn("📡 نوع الروابط","fetch_select_type")],
            [btn("📅 فلتر التاريخ","fetch_date_settings"),
             btn("💬 من مجموعاتي","fetch_mode_my_groups")],
            [btn("📨 من الرسائل","fetch_mode_messages"),
             btn("🔄 الكل","fetch_mode_all")],
            [btn("🧹 تنظيف الذاكرة","fetch_clear_memory"),
             btn("⁉️ مساعدة","fetch_help")],
            [btn("🚀 بدء الجلب","fetch_start"),
             btn("⏹️ إيقاف","fetch_stop")],
            [btn("🔙 رجوع","main_menu")]
        ])
        await self.safe_edit(update.callback_query, text, kb)

    async def fetch_select_number(self, update, ctx):
        uid  = update.effective_user.id
        nums = [n for n in self.db.get_user_numbers(uid) if n["is_active"]]
        if not nums:
            await self.safe_edit(update.callback_query, "📭 لا توجد أرقام.", back("fetch_links_menu")); return
        rows = [[btn(f"{helpers.status_dot(n['is_active'])} {n['phone']}", f"fetch_set_number_{n['id']}")] for n in nums]
        rows.append([btn("🔙 رجوع","fetch_links_menu")])
        await self.safe_edit(update.callback_query, "📱 اختر الرقم:", InlineKeyboardMarkup(rows))

    async def fetch_set_number(self, update, ctx, nid):
        ctx.user_data["fetch_nid"] = nid
        await self.safe_ans(update.callback_query, "✅ تم اختيار الرقم")
        await self.fetch_links_menu(update, ctx)

    async def fetch_select_type(self, update, ctx):
        await self.safe_edit(update.callback_query, "📡 **اختر نوع الروابط:**",
            InlineKeyboardMarkup([
                [btn("📲 تيليجرام","fetch_type_telegram"), btn("💬 واتساب","fetch_type_whatsapp"), btn("🔄 الكل","fetch_type_both")],
                [btn("🔙 رجوع","fetch_links_menu")]
            ]))

    async def fetch_set_type(self, update, ctx, ftype):
        ctx.user_data["fetch_type"] = ftype
        await self.safe_ans(update.callback_query, f"✅ النوع: {ftype}")
        await self.fetch_links_menu(update, ctx)

    async def fetch_date_settings(self, update, ctx):
        days = ctx.user_data.get("fetch_days", 1)
        labels = {1:"✅ آخر 24س", 7:"✅ أسبوع", 30:"✅ شهر", 90:"✅ ثلاثة أشهر"}
        def d(v,l): return btn(labels.get(v,l) if days==v else l, f"fetch_setdate_{v}")
        await self.safe_edit(update.callback_query, "📅 **النطاق الزمني:**\nاختر الفترة الزمنية للجلب:",
            InlineKeyboardMarkup([
                [d(1,"📅 آخر 24س"), d(7,"📅 أسبوع"), d(30,"📅 شهر"), d(90,"📅 ثلاثة أشهر")],
                [btn("🔙 رجوع","fetch_links_menu")]
            ]))

    async def fetch_setdate_handler(self, update, ctx, days):
        ctx.user_data["fetch_days"] = days
        await self.safe_ans(update.callback_query, "✅ تم")
        await self.fetch_links_menu(update, ctx)

    async def fetch_mode_my_groups(self, update, ctx):
        ctx.user_data["fetch_mode"] = "my_groups"
        await self.safe_ans(update.callback_query, "✅ وضع: مجموعاتي")
        await self.fetch_links_menu(update, ctx)

    async def fetch_mode_messages(self, update, ctx):
        ctx.user_data["fetch_mode"] = "messages"
        await self.safe_ans(update.callback_query, "✅ وضع: الرسائل")
        await self.fetch_links_menu(update, ctx)

    async def fetch_mode_all(self, update, ctx):
        ctx.user_data["fetch_mode"] = "all"
        await self.safe_ans(update.callback_query, "✅ وضع: الكل")
        await self.fetch_links_menu(update, ctx)

    async def fetch_set_msglimit_start(self, update, ctx):
        ctx.user_data["state"] = "WAIT_FETCH_MSGLIMIT"
        await self.safe_edit(update.callback_query,
            "📊 أرسل عدد الرسائل للفحص لكل محادثة (مثال: 300):",
            back("fetch_links_menu"))

    async def handle_fetch_msglimit(self, update, ctx):
        if ctx.user_data.get("state") != "WAIT_FETCH_MSGLIMIT": return
        txt = (update.message.text or "").strip()
        if txt.isdigit() and int(txt) > 0:
            ctx.user_data["fetch_msg_limit"] = int(txt)
        ctx.user_data.pop("state", None)
        await update.message.reply_text(f"✅ حد الرسائل: {ctx.user_data.get('fetch_msg_limit',300)}")

    async def fetch_start(self, update, ctx):
        uid  = update.effective_user.id
        nid  = ctx.user_data.get("fetch_nid")
        if not nid:
            await self.safe_ans(update.callback_query, "❌ اختر رقماً أولاً", True); return
        ltyp = ctx.user_data.get("fetch_type","telegram")
        days = ctx.user_data.get("fetch_days",1)
        mode = ctx.user_data.get("fetch_mode","messages")
        await self.safe_edit(update.callback_query,
            "🔍 **جاري الجلب...**\n_يُفحص المحادثات حتى حدود النطاق الزمني..._")
        msg_ref = update.callback_query.message

        async def prog_cb(done, total, found, dupes):
            try:
                await msg_ref.edit_text(
                    f"🔍 **جاري الجلب...**\n"
                    f"{helpers.progress_bar(done,total)} {helpers.pct(done,total)}\n"
                    f"📋 {done}/{total} محادثة | 🔗 جديد: {found} | 🔁 مكرر: {dupes}",
                    parse_mode=ParseMode.MARKDOWN)
            except Exception: pass

        tg, wa, stats = await self.fetch.fetch_links(uid, nid, ltyp, days, mode, prog_cb)
        groups_checked = stats.get("dialogs", 0)
        new_count      = stats.get("new", len(tg)+len(wa))
        dup_count      = stats.get("dup", 0)

        if not tg and not wa:
            err = stats.get("error","لم يُعثر على روابط جديدة.")
            summary = (f"📭 **انتهى الجلب**\n━━━━━━━━━━━━━━━━━━━━━━\n"
                       f"📂 فُحص: {groups_checked} مجموعة\n"
                       f"🔗 جديد: 0 | 🔁 مكرر: {dup_count}\n"
                       f"⚠️ {err}")
            await msg_ref.edit_text(summary, parse_mode=ParseMode.MARKDOWN)
            return

        import os as _os, time as _time
        exports_dir = _os.path.join(_os.path.dirname(__file__), "..", "exports")
        _os.makedirs(exports_dir, exist_ok=True)
        file_path = _os.path.join(exports_dir, f"links_{uid}_{int(_time.time())}.txt")
        with open(file_path, "w", encoding="utf-8") as _f:
            _f.write("\n".join(tg + wa))

        summary_caption = (f"✅ **اكتمل الجلب**\n━━━━━━━━━━━━━━━━━━━━━━\n"
                           f"📂 فُحص: {groups_checked} مجموعة\n"
                           f"🔗 جُلب: {new_count} رابط جديد\n"
                           f"🔁 تجاهل: {dup_count} رابط مكرر\n"
                           f"📲 تيليجرام: {len(tg)} | 💬 واتساب: {len(wa)}")
        try:
            with open(file_path, "rb") as _fh:
                await update.callback_query.message.reply_document(
                    document=_fh, filename="links.txt",
                    caption=summary_caption,
                    parse_mode=ParseMode.MARKDOWN)
            _os.remove(file_path)
        except Exception as e:
            await msg_ref.edit_text(f"✅ {new_count} رابط جديد — فشل إرسال الملف: {e}")
            try: _os.remove(file_path)
            except Exception: pass
            return

        await msg_ref.edit_text(summary_caption, parse_mode=ParseMode.MARKDOWN)
    async def fetch_stop(self, update, ctx):
        self.fetch.stop_fetch(update.effective_user.id)
        await self.safe_ans(update.callback_query, "⏹️ تم الإيقاف", True)

    async def fetch_clear_memory(self, update, ctx):
        count = self.fetch.clear_memory()
        await self.safe_ans(update.callback_query, f"🧹 تم مسح {count} رابط من الذاكرة المؤقتة", True)
        await self.fetch_links_menu(update, ctx)

    async def fetch_help(self, update, ctx):
        await self.safe_edit(update.callback_query,
            "📚 **دليل الجلب التفاعلي**\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🔎 **أوضاع الجلب:**\n"
            "• **مجموعاتي** — يجلب روابط مجموعاتك مباشرة دون قراءة الرسائل. سريع وآمن.\n"
            "• **الرسائل** — يتعمق في رسائل كل محادثة ويستخرج الروابط المنشورة فيها. أكثر شمولاً.\n"
            "• **الكل** — يجمع الطريقتين للنتائج القصوى.\n\n"
            "📡 **أنواع الروابط:**\n"
            "• **تيليجرام** — يجلب روابط t.me فقط.\n"
            "• **واتساب** — يجلب روابط chat.whatsapp.com فقط.\n"
            "• **الكل** — كلا النوعين.\n\n"
            "🧠 **الذاكرة المؤقتة:**\n"
            "الروابط المجلوبة تُحفظ في الرام للاستخدام السريع. استخدم زر [🧹 تنظيف الذاكرة] "
            "لمسحها يدوياً وتوفير الموارد عند الانتهاء.\n\n"
            "🛡️ **نظام مكافحة التكرار:**\n"
            "البوت يتتبع كل رابط جُلب سابقاً ويتجاهل المكررات تلقائياً، "
            "مما يوفر لك روابط جديدة ومفيدة فقط.",
            back("fetch_links_menu"))

    # ══ حماية الإعلان ════════════════════════════════════════════
    async def ad_protect_menu(self, update, ctx):
        await self.safe_edit(update.callback_query,
            "🛡️ **حماية الإعلان**\n━━━━━━━━━━━━━━━━━━━━━━\n"
            "أرسل نص إعلانك لحمايته من البوتات:",
            InlineKeyboardMarkup([
                [btn("🟢 حماية خفيفة","ad_protect_lvl_1"), btn("🔵 حماية متوسطة","ad_protect_lvl_2"), btn("🔴 حماية قوية","ad_protect_lvl_3")],
                [btn("🔙 رجوع","main_menu")]
            ]))
        ctx.user_data["state"] = "WAIT_AD_PROTECT"
        ctx.user_data["ad_protect_level"] = 2

    async def ad_protect_set_level(self, update, ctx, level):
        ctx.user_data["ad_protect_level"] = level
        await self.safe_ans(update.callback_query, f"✅ مستوى الحماية: {level}")

    async def handle_ad_protect(self, update, ctx):
        if ctx.user_data.get("state") != "WAIT_AD_PROTECT": return
        text  = update.message.text or ""
        level = ctx.user_data.get("ad_protect_level", 2)
        protected = AdProtector.protect(text, level)
        ctx.user_data.pop("state", None)
        await update.message.reply_text(
            f"🛡️ **الإعلان المحمي (مستوى {level}):**\n━━━━━━━━━━━━━━━━━━━━━━\n{protected}",
            parse_mode=ParseMode.MARKDOWN)

    # ══ الرد التلقائي ════════════════════════════════════════════
    async def auto_reply_menu(self, update, ctx):
        await self.safe_edit(update.callback_query, "💬 **الرد التلقائي**",
            InlineKeyboardMarkup([
                [btn("➕ إضافة رد","auto_reply_add")],
                [btn("📋 عرض الردود","auto_reply_list")],
                [btn("🔙 رجوع","main_menu")]
            ]))

    async def auto_reply_add_start(self, update, ctx):
        await self.safe_edit(update.callback_query,
            "💬 أرسل **الكلمة المفتاح || الرد**\nمثال: `مرحبا || أهلاً وسهلاً!`",
            back("auto_reply"))
        ctx.user_data["state"] = "WAIT_AUTO_REPLY"

    async def handle_auto_reply_add(self, update, ctx):
        if ctx.user_data.get("state") != "WAIT_AUTO_REPLY": return
        t = (update.message.text or "").strip()
        if "||" not in t:
            await update.message.reply_text("❌ الصيغة الصحيحة: `كلمة || رد`"); return
        kw, resp = map(str.strip, t.split("||", 1))
        self.db.add_auto_reply(update.effective_user.id, kw, resp)
        ctx.user_data.pop("state", None)
        await update.message.reply_text("✅ تم إضافة الرد!")

    async def auto_reply_list(self, update, ctx):
        uid  = update.effective_user.id
        rows = self.db.get_auto_replies(uid)
        if not rows:
            text = "📭 لا توجد ردود مضافة."
        else:
            text = "📋 **الردود التلقائية:**\n━━━━━━━━━━━━━━━━━━━━━━\n"
            for r in rows:
                text += f"✅ `{r['keyword']}` ➜ {r['response'][:30]}\n"
        await self.safe_edit(update.callback_query, text, back("auto_reply"))

    # ══ حسابي ════════════════════════════════════════════════════
    async def my_account_menu(self, update, ctx):
        uid  = update.effective_user.id
        u    = self.db.fetch_one("SELECT * FROM users WHERE user_id=?", (uid,))
        if not u:
            await self.safe_edit(update.callback_query, "❌ خطأ في جلب البيانات.", back("main_menu")); return
        nums = (self.db.fetch_one("SELECT COUNT(*) as c FROM numbers WHERE user_id=?", (uid,)) or {}).get("c",0)
        ads  = (self.db.fetch_one("SELECT COUNT(*) as c FROM ads WHERE user_id=?", (uid,)) or {}).get("c",0)
        sub  = u["subscription_end"] or "غير مشترك"
        rem  = 0
        if u["subscription_end"]:
            try:
                rem = max(0,(datetime.strptime(u["subscription_end"],"%Y-%m-%d")-datetime.now()).days)
            except Exception: rem = 0
        text = (f"👤 **بيانات حسابك**\n━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🆔 `{uid}`\n"
                f"📅 اشتراك: `{sub}` | متبقي: **{rem} يوم**\n"
                f"📱 أرقام: {nums}/10 | 📝 إعلانات: {ads}/10\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📤 نشر: `{u['total_posts']}`\n"
                f"🔍 جلب: `{u['total_fetches']}`")
        await self.safe_edit(update.callback_query, text, back("main_menu"))

    async def referrals_menu(self, update, ctx):
        uid  = update.effective_user.id
        u    = self.db.fetch_one("SELECT referral_code,bonus_days FROM users WHERE user_id=?", (uid,))
        frds = (self.db.fetch_one("SELECT COUNT(*) as c FROM users WHERE referred_by=?", (uid,)) or {}).get("c",0)
        bun  = (await ctx.bot.get_me()).username
        link = f"https://t.me/{bun}?start=ref_{u['referral_code']}"
        text = (f"🤝 **برنامج الإحالة**\n━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👥 أصدقاء مسجلون: {frds}\n"
                f"🎁 رصيد: {u['bonus_days']} يوم\n\n"
                f"🔗 رابطك:\n`{link}`")
        await self.safe_edit(update.callback_query, text, back("main_menu"))

    async def bot_tutorial(self, update, ctx):
        await self.safe_edit(update.callback_query,
            "📚 **دليل الاستخدام التفاعلي — MUHARRAM BOT v3.0**\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "📱 **الأرقام (الحسابات)**\n"
            "يتيح لك إضافة حتى 10 حسابات تيليجرام. كل جلسة مشفرة بـ AES-256 "
            "وتُخزَّن في قاعدة بيانات آمنة. استخدم أرقاماً ثانوية للحماية.\n\n"
            "🚀 **محرك النشر**\n"
            "ينشر إعلانك في آلاف المجموعات باستخدام فواصل زمنية ذكية. "
            "اضبط الفاصل بين 30–180 ثانية لتجنب حظر FloodWait.\n\n"
            "📁 **نظام المجلدات الذكي**\n"
            "يوفر لك إنشاء مجلدات تيليجرام من الروابط تلقائياً. "
            "كل مجلد يستوعب حتى 100 محادثة. إعدادات الأمان الديناميكي "
            "تُدار من داخل لوحة تحكم كل رقم — اضبطها لتناسب نشاطك.\n\n"
            "🔍 **جلب الروابط**\n"
            "يستخرج روابط تيليجرام وواتساب من رسائل محادثاتك ويُصدّرها "
            "ملف txt جاهز للاستخدام. الروابط المكررة تُتجاهل تلقائياً.\n\n"
            "💬 **الرد التلقائي**\n"
            "ردود تلقائية على كلمات محددة — مفيد لبرنامج خدمة العملاء.\n\n"
            "🛡️ **حماية الإعلان**\n"
            "يُعدّل نص إعلانك بتقنيات إخفاء متعددة لتجاوز فلاتر البوتات.",
            back("main_menu"))

    async def help_menu(self, update, ctx):
        from config import SETTINGS
        await self.safe_edit(update.callback_query,
            "❓ **المساعدة**\n━━━━━━━━━━━━━━━━━━━━━━\nتواصل مع الدعم عبر واتساب.",
            InlineKeyboardMarkup([
                [InlineKeyboardButton("📞 واتساب", url=SETTINGS["whatsapp_link"])],
                [btn("🔙 رجوع","main_menu")]
            ]))

    # ══ معالج الرسائل ════════════════════════════════════════════
    async def handle_message(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        uid   = update.effective_user.id
        state = ctx.user_data.get("state","")
        open_states = {
            "WAIT_CODE","WAIT_PHONE","WAIT_CODE_AUTH","WAIT_PASS",
            "WAIT_PHONE_SWITCH","WAIT_FOLDER_LINKS","WAIT_AUTO_REPLY",
            "ADD_CODE","ADMIN_ADD_CODE","ADMIN_ADD_CODE_MANUAL",
            "ADD_PROXY","EDIT_TEXT","ADMIN_SEARCH","ADMIN_BROADCAST",
            "ADMIN_EDIT_PRICE","ADMIN_EDIT_PAYMENT","ADMIN_EDIT_WA",
            "WAIT_FETCH_MSGLIMIT","WAIT_AD_PROTECT","WAIT_AD_TEXT",
            "ADMIN_EXTEND_USER","ADMIN_SET_MIRROR_TOKEN","ADMIN_ADD_ASSISTANT",
            "ADMIN_EDIT_CODE_EXPIRY",
            # نظام المهندس الذكي
            "ENG_MANUAL_ENCRYPT",
            "ENG_SMART_TEXT","ENG_SMART_LINK",
            "ENG_CAPTURE_NAME","ENG_CAPTURE_BOT","ENG_CAPTURE_MSG",
            "ENG_ADD_BOT","ENG_SET_TIMEOUT","ENG_UPDATE_ZWS","ENG_NOTIFY_VULN",
            "ENG_ADD_MANUAL_TPL_NAME","ENG_ADD_MANUAL_TPL_BOT","ENG_ADD_MANUAL_TPL_CONTENT",
            # فيديوهات
            "VID_ADD_TITLE","VID_ADD_URL","VID_ADD_FILE",
        }
        if uid not in self.admin_ids and state not in open_states:
            if not self.db.is_subscribed(uid, self.admin_ids):
                await self.show_sub_required(update, ctx)
                return

        if   state == "WAIT_CODE":           await self.handle_sub_code(update, ctx)
        elif state == "WAIT_PHONE":          await self.handle_phone(update, ctx)
        elif state == "WAIT_PHONE_SWITCH":   await self.handle_phone(update, ctx)
        elif state == "FLASH_ADD_AD":
            fhdl = ctx.bot_data.get("flash_hdl")
            if fhdl: await fhdl.handle_message(update, ctx)
        elif state == "WAIT_CODE_AUTH":      await self.handle_code_auth(update, ctx)
        elif state == "WAIT_PASS":           await self.handle_password(update, ctx)
        elif state == "WAIT_AD_TEXT":        await self.publish_save_ad(update, ctx)
        elif state == "WAIT_FOLDER_LINKS":   await self.handle_folder_links(update, ctx)
        elif state == "WAIT_AUTO_REPLY":     await self.handle_auto_reply_add(update, ctx)
        elif state == "WAIT_FETCH_MSGLIMIT": await self.handle_fetch_msglimit(update, ctx)
        elif state == "WAIT_AD_PROTECT":     await self.handle_ad_protect(update, ctx)
        # ── نظام المهندس الذكي v2 ──
        elif state == "ENG_MANUAL_ENCRYPT":          await ctx.bot_data["eng_hdl"].handle_manual_encrypt(update, ctx)
        elif state == "ENG_SMART_TEXT":              await ctx.bot_data["eng_hdl"].handle_smart_text(update, ctx)
        elif state == "ENG_SMART_LINK":              await ctx.bot_data["eng_hdl"].handle_smart_link(update, ctx)
        elif state == "ENG_CAPTURE_NAME":            await ctx.bot_data["eng_hdl"].handle_capture_name(update, ctx)
        elif state == "ENG_CAPTURE_BOT":             await ctx.bot_data["eng_hdl"].handle_capture_bot(update, ctx)
        elif state == "ENG_CAPTURE_MSG":             await ctx.bot_data["eng_hdl"].handle_capture_msg(update, ctx)
        elif state == "ENG_ADD_BOT":                 await ctx.bot_data["eng_hdl"].handle_add_bot(update, ctx)
        elif state == "ENG_SET_TIMEOUT":             await ctx.bot_data["eng_hdl"].handle_set_timeout(update, ctx)
        elif state == "ENG_UPDATE_ZWS":              await ctx.bot_data["eng_hdl"].handle_update_zws(update, ctx)
        elif state == "ENG_NOTIFY_VULN":             await ctx.bot_data["eng_hdl"].handle_notify_vuln(update, ctx)
        elif state == "ENG_ADD_MANUAL_TPL_NAME":     await ctx.bot_data["eng_hdl"].handle_add_manual_tpl_name(update, ctx)
        elif state == "ENG_ADD_MANUAL_TPL_BOT":      await ctx.bot_data["eng_hdl"].handle_add_manual_tpl_bot(update, ctx)
        elif state == "ENG_ADD_MANUAL_TPL_CONTENT":  await ctx.bot_data["eng_hdl"].handle_add_manual_tpl_content(update, ctx)
        # ── فيديوهات ──
        elif state == "VID_ADD_TITLE":               await ctx.bot_data["vid_hdl"].handle_vid_add_title(update, ctx)
        elif state == "VID_ADD_URL":                 await ctx.bot_data["vid_hdl"].handle_vid_add_url(update, ctx)
        elif state == "VID_ADD_FILE":                await ctx.bot_data["vid_hdl"].handle_vid_add_file(update, ctx)
        elif state in ("ADD_CODE","ADMIN_ADD_CODE_MANUAL","ADD_PROXY",
                       "EDIT_TEXT","ADMIN_SEARCH","ADMIN_BROADCAST",
                       "ADMIN_EDIT_PRICE","ADMIN_EDIT_PAYMENT","ADMIN_EDIT_WA",
                       "ADMIN_EXTEND_USER","ADMIN_SET_MIRROR_TOKEN","ADMIN_ADD_ASSISTANT",
                       "ADMIN_EDIT_CODE_EXPIRY") and self.admin_hdl:
            handler_map = {
                "ADD_CODE":               self.admin_hdl.handle_add_code,
                "ADMIN_ADD_CODE_MANUAL":  self.admin_hdl.handle_add_code_manual,
                "ADD_PROXY":              self.admin_hdl.handle_add_proxy,
                "EDIT_TEXT":              self.admin_hdl.handle_edit_text,
                "ADMIN_SEARCH":           self.admin_hdl.handle_search_user,
                "ADMIN_BROADCAST":        self.admin_hdl.handle_broadcast,
                "ADMIN_EDIT_PRICE":       self.admin_hdl.handle_admin_edit,
                "ADMIN_EDIT_PAYMENT":     self.admin_hdl.handle_admin_edit,
                "ADMIN_EDIT_WA":          self.admin_hdl.handle_admin_edit,
                "ADMIN_EXTEND_USER":      self.admin_hdl.handle_extend_user,
                "ADMIN_SET_MIRROR_TOKEN": self.admin_hdl.handle_set_mirror_token,
                "ADMIN_ADD_ASSISTANT":    self.admin_hdl.handle_add_assistant,
                "ADMIN_EDIT_CODE_EXPIRY": self.admin_hdl.handle_edit_text,
            }
            fn = handler_map.get(state)
            if fn: await fn(update, ctx)
        elif state and state.startswith("WAIT_SET_"):
            key = state[9:]
            txt = (update.message.text or "").strip()
            if not txt.isdigit() or int(txt) <= 0:
                await update.message.reply_text("❌ أرسل رقماً صحيحاً أكبر من صفر.")
                return
            self.db.execute(f"UPDATE settings SET {key}=? WHERE user_id=?", (int(txt), uid))
            ctx.user_data.pop("state", None)
            await update.message.reply_text(f"✅ تم التحديث: {key} = {txt}")
        elif state and state.startswith("WAIT_FOLDER_SAFETY_"):
            field = state[19:]
            txt   = (update.message.text or "").strip()
            nid   = ctx.user_data.get("folder_safety_nid")
            allowed_fields = {"join_delay_min","join_delay_max","big_break_duration","groups_per_break"}
            if field not in allowed_fields or not txt.isdigit() or int(txt) <= 0:
                await update.message.reply_text("❌ أرسل رقماً صحيحاً أكبر من صفر.")
                return
            self.db.execute(f"UPDATE settings SET {field}=? WHERE user_id=?", (int(txt), uid))
            ctx.user_data.pop("state", None)
            await update.message.reply_text(f"✅ تم التحديث: {field} = {txt}")
        else:
            rep = self.db.find_auto_reply(uid, update.message.text or "")
            if rep:
                await update.message.reply_text(rep)
            else:
                await update.message.reply_text("❓ استخدم القائمة.",
                                                reply_markup=main_kb(uid, self.admin_ids))
