# -*- coding: utf-8 -*-
"""
معالج نظام المهندس v3 — Reverse Engineering + Smart Templates
الجديد:
  • قسم الآدمن: يرسل إعلاناً حقيقياً → البوت يحلّل entities → يحفظ Blueprint
  • قسم المشترك: يرسل نصه ورقمه → البوت يُطبّق Blueprint → إعلان جاهز
"""
import asyncio, logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

logger = logging.getLogger(__name__)

def btn(text, cb): return InlineKeyboardButton(text, callback_data=cb)
def back(cb):      return InlineKeyboardMarkup([[btn("🔙 رجوع", cb)]])


class EngineerHandler:
    def __init__(self, db, engineer_svc, admin_ids):
        self.db        = db
        self.eng       = engineer_svc
        self.admin_ids = admin_ids

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

    # ══════════════════════════════════════════════════════════════
    #   👤 قسم المشترك — تطبيق القالب الذكي
    # ══════════════════════════════════════════════════════════════

    async def smart_ads_menu(self, update, ctx):
        tpl   = self.eng.get_best_template()
        tpl_s = (f"✅ قالب نشط: `{tpl['template_name']}`"
                 if tpl else "⚠️ لا يوجد قالب معتمد حالياً")
        has_bp = bool(tpl and tpl.get("blueprint"))
        mode   = "🧠 وضع Blueprint الذكي" if has_bp else "✍️ وضع التشفير اليدوي"
        kb = InlineKeyboardMarkup([
            [btn("✍️ تعديل إعلان مشفر", "eng_manual_encrypt")],
            [btn("🔙 رجوع", "main_menu")]
        ])
        await self.safe_edit(update.callback_query,
            f"🛡️ **قسم الإعلانات الذكي**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{tpl_s}\n"
            f"⚙️ {mode}\n\n"
            f"اضغط لإنشاء إعلانك المشفر جاهزاً للنسخ.", kb)

    # خطوة 1: طلب النص
    async def eng_manual_encrypt(self, update, ctx):
        tpl = self.eng.get_best_template()
        has_bp = bool(tpl and tpl.get("blueprint"))
        if has_bp:
            # وضع Blueprint: سنطلب النص أولاً ثم الرابط
            ctx.user_data["state"] = "ENG_SMART_TEXT"
            hint = ("🧠 **إعلان ذكي — Blueprint نشط**\n"
                    "━━━━━━━━━━━━━━━━━━━━━━\n"
                    "📝 **الخطوة 1/2:** أرسل **نص إعلانك** الآن:\n"
                    "_سيتم تضمينه في القالب الجاهز_")
        else:
            ctx.user_data["state"] = "ENG_MANUAL_ENCRYPT"
            hint = ("✍️ **إعلان مشفر**\n"
                    "━━━━━━━━━━━━━━━━━━━━━━\n"
                    "📝 أرسل نص إعلانك الآن:")
        await self.safe_edit(update.callback_query, hint,
                             back("eng_smart_ads_menu"))

    # خطوة 1 — استقبال النص (Blueprint)
    async def handle_smart_text(self, update, ctx):
        if ctx.user_data.get("state") != "ENG_SMART_TEXT": return
        text = (update.message.text or "").strip()
        if not text:
            await update.message.reply_text("❌ النص فارغ."); return
        ctx.user_data["eng_user_text"] = text
        ctx.user_data["state"] = "ENG_SMART_LINK"
        await update.message.reply_text(
            "🔗 **الخطوة 2/2:** أرسل **رابطك أو رقم هاتفك** الآن:\n"
            "_مثال: https://t.me/username أو +9665xxxxxxxx_\n"
            "أو أرسل `-` لتخطي هذه الخطوة",
            parse_mode=ParseMode.MARKDOWN)

    # خطوة 2 — استقبال الرابط ثم إرسال النتيجة
    async def handle_smart_link(self, update, ctx):
        if ctx.user_data.get("state") != "ENG_SMART_LINK": return
        raw = (update.message.text or "").strip()
        ctx.user_data.pop("state", None)
        user_text = ctx.user_data.pop("eng_user_text", "")

        # تحديد: رابط أم رقم؟
        if raw == "-":
            user_link = user_number = ""
        elif raw.startswith(("http", "t.me", "@")):
            user_link  = raw
            user_number = ""
        elif raw.startswith("+") or raw.isdigit():
            user_number = raw
            user_link   = ""
        else:
            user_link   = raw
            user_number = ""

        tpl = self.eng.get_best_template()
        if not tpl:
            result = self.eng.apply_manual_encryption(user_text)
            await update.message.reply_text(result)
            return

        final_text, entities = self.eng.render_smart_template(
            tpl, user_text, user_link, user_number)

        # إرسال مع entities أو بدون parse_mode لضمان عدم ParseError
        try:
            if entities:
                await update.message.reply_text(
                    final_text, entities=entities)
            else:
                await update.message.reply_text(final_text)
        except Exception as e:
            logger.warning(f"send with entities failed: {e}, fallback plain")
            await update.message.reply_text(final_text)

    # وضع التشفير اليدوي (fallback بدون Blueprint)
    async def handle_manual_encrypt(self, update, ctx):
        if ctx.user_data.get("state") != "ENG_MANUAL_ENCRYPT": return
        ctx.user_data.pop("state", None)
        text = (update.message.text or "").strip()
        if not text:
            await update.message.reply_text("❌ النص فارغ."); return
        tpl = self.eng.get_best_template()
        if tpl:
            result, _ = self.eng.render_smart_template(tpl, text)
        else:
            result = self.eng.apply_manual_encryption(text)
        await update.message.reply_text(result)

    # ══════════════════════════════════════════════════════════════
    #   🛠️ قسم الآدمن — تحليل الإعلانات العكسي
    # ══════════════════════════════════════════════════════════════

    async def admin_engineer_menu(self, update, ctx):
        if not self._is_admin(update.effective_user.id):
            await self.safe_ans(update.callback_query, "❌"); return
        total_t  = (self.db.fetch_one(
            "SELECT COUNT(*) as c FROM captured_templates") or {}).get("c", 0)
        approved = (self.db.fetch_one(
            "SELECT COUNT(*) as c FROM captured_templates WHERE status='approved'"
            ) or {}).get("c", 0)
        pending  = (self.db.fetch_one(
            "SELECT COUNT(*) as c FROM captured_templates WHERE status='pending'"
            ) or {}).get("c", 0)
        bots_c   = (self.db.fetch_one(
            "SELECT COUNT(*) as c FROM monitored_bots WHERE is_active=1"
            ) or {}).get("c", 0)
        timeout  = self.eng.get_snipe_timeout()
        text = (f"🛠️ **نظام المهندس الذكي v3**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📂 القوالب: `{total_t}` | ✅ معتمدة: `{approved}` | ⏳ معلقة: `{pending}`\n"
                f"🤖 البوتات: `{bots_c}` | ⏱️ وقت القنص: `{timeout}` دقيقة\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🆕 **جديد:** أرسل إعلاناً للبوت مباشرة → يُحلَّل ويُحفظ كـ Blueprint")
        kb = InlineKeyboardMarkup([
            [btn("🔬 تحليل إعلان → Blueprint", "eng_admin_capture"),
             btn("➕ إضافة قالب يدوياً",        "eng_admin_add_manual_tpl")],
            [btn("📂 القوالب",                   "eng_admin_templates"),
             btn("🗑️ حذف قالب",                 "eng_admin_del_template")],
            [btn("🧪 اختبار قالب",               "eng_admin_test_template"),
             btn("➕ إضافة بوت",                 "eng_admin_add_bot")],
            [btn("⏱️ ضبط وقت القنص",            "eng_admin_set_timeout"),
             btn("🔄 تحديث ZWS",                "eng_admin_update_zws")],
            [btn("📢 إرسال تنبيه ثغرة",          "eng_admin_notify_vuln")],
            [btn("🔙 رجوع", "admin_panel")]
        ])
        await self.safe_edit(update.callback_query, text, kb)

    # ── تحليل إعلان حقيقي (Capture → Blueprint) ─────────────────
    async def admin_capture_prompt(self, update, ctx):
        """يطلب من الآدمن إرسال الإعلان الحقيقي للتحليل"""
        if not self._is_admin(update.effective_user.id): return
        ctx.user_data["state"] = "ENG_CAPTURE_NAME"
        await self.safe_edit(update.callback_query,
            "🔬 **تحليل إعلان → Blueprint**\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "**الخطوة 1/3:** أرسل **اسم** القالب الجديد:\n"
            "_مثال: قالب روز المشفر_",
            back("eng_admin_menu"))

    async def handle_capture_name(self, update, ctx):
        if ctx.user_data.get("state") != "ENG_CAPTURE_NAME": return
        name = (update.message.text or "").strip()
        if not name:
            await update.message.reply_text("❌ الاسم فارغ."); return
        ctx.user_data["eng_cap_name"] = name
        ctx.user_data["state"] = "ENG_CAPTURE_BOT"
        await update.message.reply_text(
            f"✅ الاسم: `{name}`\n\n"
            "**الخطوة 2/3:** أرسل اسم البوت المستهدف (مثال: `@Rose`)\n"
            "أو أرسل `-` لتخطي:",
            parse_mode=ParseMode.MARKDOWN)

    async def handle_capture_bot(self, update, ctx):
        if ctx.user_data.get("state") != "ENG_CAPTURE_BOT": return
        bot_name = (update.message.text or "").strip()
        ctx.user_data["eng_cap_bot"] = "" if bot_name == "-" else bot_name
        ctx.user_data["state"] = "ENG_CAPTURE_MSG"
        await update.message.reply_text(
            "📨 **الخطوة 3/3:** الآن **أعد توجيه** (Forward) الإعلان الجاهز إلى هنا\n"
            "أو أرسله مباشرة كما هو مع كامل تنسيقه (bold/spoiler/روابط...).\n\n"
            "⚠️ مهم: أرسل الرسالة **بتنسيقها الكامل** وليس كنص عادي.",
            parse_mode=ParseMode.MARKDOWN)

    async def handle_capture_msg(self, update, ctx):
        """
        يستقبل الرسالة الكاملة، يحلّل entities، يبني Blueprint، يحفظه.
        هذا هو قلب نظام Reverse Engineering.
        """
        if ctx.user_data.get("state") != "ENG_CAPTURE_MSG": return
        ctx.user_data.pop("state", None)
        name     = ctx.user_data.pop("eng_cap_name", "قالب محلَّل")
        bot_name = ctx.user_data.pop("eng_cap_bot", "")

        msg = update.message
        if not msg:
            await update.effective_chat.send_message("❌ لم أتلقَّ رسالة."); return

        text     = msg.text or msg.caption or ""
        entities = list(msg.entities or msg.caption_entities or [])

        if not text:
            await msg.reply_text("❌ الرسالة لا تحتوي على نص."); return

        # بناء Blueprint
        from engineer_svc import build_blueprint
        blueprint = build_blueprint(text, entities)

        import json as _json
        bp_json  = _json.dumps(blueprint, ensure_ascii=False)

        # حفظ في DB
        result = self.eng.add_template(
            name, text,
            target_bot=bot_name,
            source_group="reverse_engineering",
            notify_admin=False,
            blueprint_json=bp_json)

        if result["status"] == "duplicate":
            # تحديث blueprint للقالب الموجود
            existing = self.db.fetch_one(
                "SELECT id FROM captured_templates WHERE content_hash=?",
                (self.eng._hash(text),))
            if existing:
                self.eng.save_blueprint(existing["id"], blueprint)
                await msg.reply_text(
                    "⚠️ محتوى مكرر — تم **تحديث Blueprint** للقالب الموجود.\n"
                    "✅ القالب جاهز للاستخدام.",
                    parse_mode=ParseMode.MARKDOWN)
            return

        tpl_id = result.get("id")
        # اعتماد فوري
        if tpl_id:
            self.db.execute(
                "UPDATE captured_templates SET status='approved' WHERE id=?",
                (tpl_id,))

        # عرض ملخص Blueprint للآدمن
        seg_types = {}
        for s in blueprint.get("segments", []):
            k = s["k"]
            seg_types[k] = seg_types.get(k, 0) + 1

        summary_lines = []
        labels = {
            "user_text":   "📝 نص المستخدم",
            "user_link":   "🔗 رابط المستخدم",
            "user_number": "📞 رقم المستخدم",
            "bold":        "**굵음** Bold",
            "italic":      "_مائل_ Italic",
            "spoiler":     "👁️ Spoiler",
            "code":        "💻 Code",
            "plain":       "📄 نص ثابت",
        }
        for k, cnt in seg_types.items():
            lbl = labels.get(k, k)
            summary_lines.append(f"  • {lbl}: {cnt}")

        await msg.reply_text(
            f"✅ **تم تحليل الإعلان وحفظ Blueprint!**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📛 الاسم: `{name}`\n"
            f"🤖 البوت: `{bot_name or '—'}`\n"
            f"📦 عدد الأجزاء: `{len(blueprint.get('segments', []))}`\n\n"
            f"**محتوى البلوبرينت:**\n" +
            "\n".join(summary_lines) +
            "\n\n✅ القالب معتمد وجاهز للمشتركين فوراً.",
            parse_mode=ParseMode.MARKDOWN)

    # ── قائمة القوالب ────────────────────────────────────────────
    async def admin_templates_list(self, update, ctx):
        if not self._is_admin(update.effective_user.id): return
        rows = self.db.fetch_all(
            "SELECT * FROM captured_templates ORDER BY created_at DESC LIMIT 20")
        if not rows:
            await self.safe_edit(update.callback_query,
                "📭 لا توجد قوالب بعد.", back("eng_admin_menu")); return
        text = "📂 **القوالب:**\n━━━━━━━━━━━━━━━━━━━━━━\n"
        btns = []
        for r in rows:
            st  = "✅" if r["status"] == "approved" else ("⏳" if r["status"] == "pending" else "❌")
            has_bp = "🧠" if r.get("blueprint") else "📝"
            text += f"{st}{has_bp} `{r['template_name']}` — {(r.get('created_at') or '')[:10]}\n"
            if r["status"] == "pending":
                btns.append([
                    btn(f"✅ اعتماد: {r['template_name']}", f"eng_approve_tpl_{r['id']}"),
                    btn("🗑️ حذف", f"eng_del_tpl_{r['id']}")
                ])
        btns.append([btn("🔙 رجوع", "eng_admin_menu")])
        await self.safe_edit(update.callback_query, text, InlineKeyboardMarkup(btns))

    async def admin_approve_template(self, update, ctx, tpl_id: int):
        if not self._is_admin(update.effective_user.id): return
        self.db.execute(
            "UPDATE captured_templates SET status='approved' WHERE id=?", (tpl_id,))
        await self.safe_ans(update.callback_query, "✅ تم اعتماد القالب", True)
        await self.admin_templates_list(update, ctx)

    async def admin_del_template_prompt(self, update, ctx):
        if not self._is_admin(update.effective_user.id): return
        rows = self.db.fetch_all(
            "SELECT id,template_name,status FROM captured_templates ORDER BY created_at DESC")
        if not rows:
            await self.safe_edit(update.callback_query, "📭 لا قوالب.",
                                 back("eng_admin_menu")); return
        btns = [[btn(f"🗑️ {r['template_name']} ({r['status']})",
                     f"eng_del_tpl_{r['id']}")] for r in rows]
        btns.append([btn("🔙 رجوع", "eng_admin_menu")])
        await self.safe_edit(update.callback_query,
                             "🗑️ اختر القالب للحذف:", InlineKeyboardMarkup(btns))

    async def admin_del_template(self, update, ctx, tpl_id: int):
        if not self._is_admin(update.effective_user.id): return
        self.db.execute("DELETE FROM captured_templates WHERE id=?", (tpl_id,))
        await self.safe_ans(update.callback_query, "✅ تم الحذف", True)
        await self.admin_del_template_prompt(update, ctx)

    # ── إضافة قالب يدوي ──────────────────────────────────────────
    async def admin_add_manual_template_prompt(self, update, ctx):
        if not self._is_admin(update.effective_user.id): return
        ctx.user_data["state"] = "ENG_ADD_MANUAL_TPL_NAME"
        await self.safe_edit(update.callback_query,
            "➕ **إضافة قالب يدوياً**\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "أرسل **اسم** القالب:",
            back("eng_admin_menu"))

    async def handle_add_manual_tpl_name(self, update, ctx):
        if ctx.user_data.get("state") != "ENG_ADD_MANUAL_TPL_NAME": return
        name = (update.message.text or "").strip()
        if not name:
            await update.message.reply_text("❌ الاسم فارغ."); return
        ctx.user_data["eng_new_tpl_name"] = name
        ctx.user_data["state"] = "ENG_ADD_MANUAL_TPL_BOT"
        await update.message.reply_text(
            f"✅ الاسم: `{name}`\n\n"
            "🤖 أرسل اسم البوت المستهدف أو `-` لتخطي:",
            parse_mode=ParseMode.MARKDOWN)

    async def handle_add_manual_tpl_bot(self, update, ctx):
        if ctx.user_data.get("state") != "ENG_ADD_MANUAL_TPL_BOT": return
        bot_name = (update.message.text or "").strip()
        ctx.user_data["eng_new_tpl_bot"] = "" if bot_name == "-" else bot_name
        ctx.user_data["state"] = "ENG_ADD_MANUAL_TPL_CONTENT"
        await update.message.reply_text(
            "📝 أرسل **محتوى القالب**.\n"
            "استخدم `{{AD_TEXT}}` لموضع النص:\n"
            "مثال: `إعلان: {{AD_TEXT}}`",
            parse_mode=ParseMode.MARKDOWN)

    async def handle_add_manual_tpl_content(self, update, ctx):
        if ctx.user_data.get("state") != "ENG_ADD_MANUAL_TPL_CONTENT": return
        content = (update.message.text or "").strip()
        if not content:
            await update.message.reply_text("❌ المحتوى فارغ."); return
        name     = ctx.user_data.pop("eng_new_tpl_name", "قالب يدوي")
        bot_name = ctx.user_data.pop("eng_new_tpl_bot", "")
        ctx.user_data.pop("state", None)
        result = self.eng.add_template(name, content, target_bot=bot_name,
                                       source_group="يدوي", notify_admin=False)
        if result["status"] == "duplicate":
            await update.message.reply_text("⚠️ هذا القالب مكرر."); return
        tpl_id = result.get("id")
        if tpl_id:
            self.db.execute(
                "UPDATE captured_templates SET status='approved' WHERE id=?", (tpl_id,))
        await update.message.reply_text(
            f"✅ **تمت الإضافة!**\n"
            f"📛 الاسم: `{name}`\n🤖 البوت: `{bot_name or '—'}`",
            parse_mode=ParseMode.MARKDOWN)

    # ── اختبار قالب ──────────────────────────────────────────────
    async def admin_test_template_prompt(self, update, ctx):
        if not self._is_admin(update.effective_user.id): return
        rows = self.db.fetch_all(
            "SELECT id,template_name FROM captured_templates WHERE status='approved'")
        if not rows:
            await self.safe_edit(update.callback_query,
                "⚠️ لا قوالب معتمدة.", back("eng_admin_menu")); return
        btns = [[btn(f"🧪 {r['template_name']}", f"eng_test_tpl_{r['id']}")] for r in rows]
        btns.append([btn("🔙 رجوع", "eng_admin_menu")])
        await self.safe_edit(update.callback_query, "🧪 اختر القالب:",
                             InlineKeyboardMarkup(btns))

    # ── بوت مستهدف ───────────────────────────────────────────────
    async def admin_add_bot_prompt(self, update, ctx):
        if not self._is_admin(update.effective_user.id): return
        ctx.user_data["state"] = "ENG_ADD_BOT"
        await self.safe_edit(update.callback_query,
            "➕ **إضافة بوت مستهدف**\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "أرسل معرف البوت مثال: `@Rose`",
            back("eng_admin_menu"))

    async def handle_add_bot(self, update, ctx):
        if ctx.user_data.get("state") != "ENG_ADD_BOT": return
        ctx.user_data.pop("state", None)
        bot_username = (update.message.text or "").strip()
        if not bot_username.startswith("@"):
            bot_username = "@" + bot_username
        if self.db.fetch_one(
                "SELECT id FROM monitored_bots WHERE bot_username=?",
                (bot_username,)):
            await update.message.reply_text(
                f"⚠️ `{bot_username}` مضاف مسبقاً.",
                parse_mode=ParseMode.MARKDOWN); return
        await update.message.reply_text(
            f"🔄 جاري الكشف عن `{bot_username}`...",
            parse_mode=ParseMode.MARKDOWN)
        try:
            count = await self.eng.estimate_bot_presence(bot_username)
        except Exception:
            count = 0
        self.db.execute(
            "INSERT INTO monitored_bots(bot_username, estimated_groups) VALUES(?,?)",
            (bot_username, count))
        await update.message.reply_text(
            f"✅ **تمت الإضافة!**\n"
            f"🤖 `{bot_username}` | تقدير الانتشار: `{count}`",
            parse_mode=ParseMode.MARKDOWN)

    # ── ضبط وقت القنص ────────────────────────────────────────────
    async def admin_set_timeout_prompt(self, update, ctx):
        if not self._is_admin(update.effective_user.id): return
        ctx.user_data["state"] = "ENG_SET_TIMEOUT"
        current = self.eng.get_snipe_timeout()
        await self.safe_edit(update.callback_query,
            f"⏱️ **ضبط وقت القنص**\n"
            f"الحالي: `{current}` دقيقة\n\nأرسل الوقت الجديد:",
            back("eng_admin_menu"))

    async def handle_set_timeout(self, update, ctx):
        if ctx.user_data.get("state") != "ENG_SET_TIMEOUT": return
        ctx.user_data.pop("state", None)
        txt = (update.message.text or "").strip()
        if not txt.isdigit() or int(txt) <= 0:
            await update.message.reply_text("❌ أرسل رقماً صحيحاً."); return
        self.db.execute(
            "INSERT OR REPLACE INTO engineer_settings(key,value)"
            " VALUES('snipe_timeout',?)", (txt,))
        await update.message.reply_text(
            f"✅ وقت القنص: `{txt}` دقيقة",
            parse_mode=ParseMode.MARKDOWN)

    # ── تحديث ZWS ────────────────────────────────────────────────
    async def admin_update_zws_prompt(self, update, ctx):
        if not self._is_admin(update.effective_user.id): return
        ctx.user_data["state"] = "ENG_UPDATE_ZWS"
        current = self.db.fetch_one(
            "SELECT value FROM engineer_settings WHERE key='zws_chars'")
        cur_val = (current or {}).get("value", "افتراضي")
        await self.safe_edit(update.callback_query,
            f"🔄 **تحديث رموز ZWS**\n"
            f"الحالية: `{cur_val}`\n\nأرسل الرموز الجديدة مفصولة بفاصلة:",
            back("eng_admin_menu"))

    async def handle_update_zws(self, update, ctx):
        if ctx.user_data.get("state") != "ENG_UPDATE_ZWS": return
        ctx.user_data.pop("state", None)
        val = (update.message.text or "").strip()
        if not val:
            await update.message.reply_text("❌ أرسل الرموز."); return
        self.db.execute(
            "INSERT OR REPLACE INTO engineer_settings(key,value)"
            " VALUES('zws_chars',?)", (val,))
        await update.message.reply_text(
            f"✅ تم تحديث ZWS!\n`{val}`",
            parse_mode=ParseMode.MARKDOWN)

    # ── تنبيه ثغرة ───────────────────────────────────────────────
    async def admin_notify_vuln(self, update, ctx):
        if not self._is_admin(update.effective_user.id): return
        ctx.user_data["state"] = "ENG_NOTIFY_VULN"
        await self.safe_edit(update.callback_query,
            "📢 **إرسال تنبيه ثغرة**\n"
            "أرسل نص التنبيه للمشتركين النشطين:",
            back("eng_admin_menu"))

    async def handle_notify_vuln(self, update, ctx):
        if ctx.user_data.get("state") != "ENG_NOTIFY_VULN": return
        ctx.user_data.pop("state", None)
        text = (update.message.text or "").strip()
        if not text: await update.message.reply_text("❌ النص فارغ."); return
        msg   = (f"🔔 **تنبيه من نظام المهندس**\n"
                 f"━━━━━━━━━━━━━━━━━━━━━━\n{text}")
        users = self.db.fetch_all(
            "SELECT user_id FROM users WHERE subscription_end >= date('now')")
        sent = 0
        for u in users:
            try:
                await update.get_bot().send_message(
                    u["user_id"], msg, parse_mode=ParseMode.MARKDOWN)
                sent += 1
                await asyncio.sleep(0.1)
            except Exception:
                pass
        await update.message.reply_text(
            f"✅ تم الإرسال لـ `{sent}` مشترك.",
            parse_mode=ParseMode.MARKDOWN)

    async def admin_disable_user_code(self, update, ctx, uid: int):
        if not self._is_admin(update.effective_user.id): return
        self.db.execute(
            "UPDATE users SET subscription_end=date('now','-1 day')"
            " WHERE user_id=?", (uid,))
        await self.safe_ans(update.callback_query,
                            f"✅ تم إيقاف اشتراك {uid}", True)
        await update.callback_query.message.reply_text(
            f"✅ تم إيقاف كود المشترك `{uid}` فوراً.",
            parse_mode=ParseMode.MARKDOWN)
