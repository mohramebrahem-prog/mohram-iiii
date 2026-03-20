# -*- coding: utf-8 -*-
"""معالج قسم الفيديوهات التعليمية"""
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

logger = logging.getLogger(__name__)

def btn(text, cb): return InlineKeyboardButton(text, callback_data=cb)
def back(cb):      return InlineKeyboardMarkup([[btn("🔙 رجوع", cb)]])


class VideoHandler:
    def __init__(self, db, video_svc, admin_ids):
        self.db        = db
        self.vid       = video_svc
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

    # ══ المشترك ══════════════════════════════════════════════════

    async def videos_menu(self, update, ctx):
        """قائمة الفيديوهات التعليمية للمشترك"""
        videos = self.vid.get_videos()
        if not videos:
            await self.safe_edit(update.callback_query,
                "📹 **مكتبة الفيديوهات التعليمية**\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "📭 لا توجد فيديوهات متاحة حالياً.",
                back("main_menu")); return
        text = "📹 **مكتبة الفيديوهات التعليمية**\n━━━━━━━━━━━━━━━━━━━━━━\n"
        btns = []
        for v in videos:
            btns.append([btn(f"▶️ {v['title']}", f"vid_watch_{v['id']}")])
        btns.append([btn("🔙 رجوع", "main_menu")])
        await self.safe_edit(update.callback_query, text, InlineKeyboardMarkup(btns))

    async def video_watch(self, update, ctx, vid_id: int):
        """عرض فيديو محدد"""
        v = self.vid.get_video(vid_id)
        if not v:
            await self.safe_ans(update.callback_query, "❌ الفيديو غير موجود", True); return
        kb = InlineKeyboardMarkup([[btn("🔙 رجوع للمكتبة", "vid_menu")]])
        if v.get("url"):
            await self.safe_edit(update.callback_query,
                f"▶️ **{v['title']}**\n━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔗 [اضغط لمشاهدة الفيديو]({v['url']})", kb,
                pm=ParseMode.MARKDOWN)
        elif v.get("file_id"):
            await self.safe_ans(update.callback_query, "📤 جاري إرسال الفيديو...")
            try:
                await update.callback_query.message.reply_video(
                    video=v["file_id"], caption=f"▶️ {v['title']}")
            except Exception as e:
                await update.callback_query.message.reply_text(
                    f"❌ تعذر إرسال الفيديو: {e}")
        else:
            await self.safe_edit(update.callback_query,
                f"▶️ **{v['title']}**\n⚠️ لا يوجد رابط أو ملف.", kb)

    # ══ الآدمن ═══════════════════════════════════════════════════

    async def admin_videos_menu(self, update, ctx):
        if not self._is_admin(update.effective_user.id):
            await self.safe_ans(update.callback_query, "❌"); return
        total = (self.db.fetch_one(
            "SELECT COUNT(*) as c FROM tutorial_videos WHERE is_active=1") or {}).get("c", 0)
        kb = InlineKeyboardMarkup([
            [btn(f"📋 عرض الفيديوهات ({total})", "vid_admin_list")],
            [btn("➕ إضافة فيديو (رابط)",          "vid_admin_add_url"),
             btn("➕ إضافة فيديو (ملف)",            "vid_admin_add_file")],
            [btn("🗑️ حذف فيديو",                   "vid_admin_delete")],
            [btn("🔙 رجوع", "admin_panel")]
        ])
        await self.safe_edit(update.callback_query,
            f"📹 **إدارة الفيديوهات التعليمية**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 الإجمالي: `{total}` فيديو", kb)

    async def admin_add_video_url_start(self, update, ctx):
        if not self._is_admin(update.effective_user.id): return
        ctx.user_data["state"]    = "VID_ADD_TITLE"
        ctx.user_data["vid_type"] = "url"
        await self.safe_edit(update.callback_query,
            "➕ **إضافة فيديو برابط**\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "أرسل **عنوان** الفيديو:",
            back("vid_admin_menu"))

    async def admin_add_video_file_start(self, update, ctx):
        if not self._is_admin(update.effective_user.id): return
        ctx.user_data["state"]    = "VID_ADD_TITLE"
        ctx.user_data["vid_type"] = "file"
        await self.safe_edit(update.callback_query,
            "➕ **إضافة فيديو بملف**\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "أرسل **عنوان** الفيديو:",
            back("vid_admin_menu"))

    async def handle_vid_add_title(self, update, ctx):
        if ctx.user_data.get("state") != "VID_ADD_TITLE": return
        title = (update.message.text or "").strip()
        if not title:
            await update.message.reply_text("❌ العنوان فارغ."); return
        ctx.user_data["vid_title"] = title
        vid_type = ctx.user_data.get("vid_type", "url")
        if vid_type == "url":
            ctx.user_data["state"] = "VID_ADD_URL"
            await update.message.reply_text(
                f"✅ العنوان: `{title}`\n\n🔗 أرسل رابط الفيديو:",
                parse_mode=ParseMode.MARKDOWN)
        else:
            ctx.user_data["state"] = "VID_ADD_FILE"
            await update.message.reply_text(
                f"✅ العنوان: `{title}`\n\n📤 أرسل ملف الفيديو الآن:",
                parse_mode=ParseMode.MARKDOWN)

    async def handle_vid_add_url(self, update, ctx):
        if ctx.user_data.get("state") != "VID_ADD_URL": return
        url   = (update.message.text or "").strip()
        title = ctx.user_data.pop("vid_title", "فيديو")
        ctx.user_data.pop("state", None)
        ctx.user_data.pop("vid_type", None)
        if not url:
            await update.message.reply_text("❌ الرابط فارغ."); return
        self.vid.add_video(title=title, url=url, added_by=update.effective_user.id)
        await update.message.reply_text(
            f"✅ تمت الإضافة!\n📹 `{title}`\n🔗 {url}",
            parse_mode=ParseMode.MARKDOWN)

    async def handle_vid_add_file(self, update, ctx):
        if ctx.user_data.get("state") != "VID_ADD_FILE": return
        if not update.message.video:
            await update.message.reply_text("❌ أرسل ملف فيديو."); return
        file_id = update.message.video.file_id
        title   = ctx.user_data.pop("vid_title", "فيديو")
        ctx.user_data.pop("state", None)
        ctx.user_data.pop("vid_type", None)
        self.vid.add_video(title=title, file_id=file_id, added_by=update.effective_user.id)
        await update.message.reply_text(
            f"✅ تمت إضافة الفيديو!\n📹 `{title}`",
            parse_mode=ParseMode.MARKDOWN)

    async def admin_list_videos(self, update, ctx):
        if not self._is_admin(update.effective_user.id): return
        videos = self.vid.get_videos()
        if not videos:
            await self.safe_edit(update.callback_query,
                "📭 لا توجد فيديوهات.", back("vid_admin_menu")); return
        text = "📋 **الفيديوهات:**\n━━━━━━━━━━━━━━━━━━━━━━\n"
        for v in videos:
            lnk = f"🔗" if v.get("url") else "📁"
            text += f"{lnk} `{v['id']}` — {v['title']}\n"
        await self.safe_edit(update.callback_query, text, back("vid_admin_menu"))

    async def admin_delete_video_prompt(self, update, ctx):
        if not self._is_admin(update.effective_user.id): return
        videos = self.vid.get_videos()
        if not videos:
            await self.safe_edit(update.callback_query,
                "📭 لا فيديوهات للحذف.", back("vid_admin_menu")); return
        btns = [[btn(f"🗑️ {v['title']}", f"vid_del_{v['id']}")] for v in videos]
        btns.append([btn("🔙 رجوع", "vid_admin_menu")])
        await self.safe_edit(update.callback_query,
                             "🗑️ اختر الفيديو للحذف:", InlineKeyboardMarkup(btns))

    async def admin_delete_video(self, update, ctx, vid_id: int):
        if not self._is_admin(update.effective_user.id): return
        self.vid.delete_video(vid_id)
        await self.safe_ans(update.callback_query, "✅ تم الحذف", True)
        await self.admin_delete_video_prompt(update, ctx)
