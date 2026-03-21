# -*- coding: utf-8 -*-
"""Flash Turbo Engine v2.5 — محرك النشر الفائق"""
import asyncio, itertools, logging, random, time
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError, ChatWriteForbiddenError, UserBannedInChannelError,
    ChatAdminRequiredError, SlowModeWaitError, PeerFloodError,
    UserDeactivatedBanError, AuthKeyUnregisteredError, ChannelPrivateError,
)
from telethon.sessions import StringSession
import utils as helpers

logger = logging.getLogger(__name__)


def btn(text, cb):  return InlineKeyboardButton(text, callback_data=cb)
def back(cb):       return InlineKeyboardMarkup([[btn("🔙 رجوع", cb)]])


# ══════════════════════════════════════════════════════════════════════
#  FlashTurboEngine — قلب المحرك
# ══════════════════════════════════════════════════════════════════════
class FlashTurboEngine:
    def __init__(self, db, api_id, api_hash, bot=None):
        self.db       = db
        self.api_id   = api_id
        self.api_hash = api_hash
        self.bot      = bot
        # حالة كل مستخدم: uid -> campaign_dict
        self._campaigns: dict = {}
        # asyncio.Lock لمنع تداخل النشر العادي
        self._turbo_lock: asyncio.Lock = asyncio.Lock()

    # ── بناء العميل ──────────────────────────────────────────────────
    def _make_client(self, n):
        proxy = helpers.parse_proxy(n.get("proxy")) if n.get("proxy") else None
        return TelegramClient(
            StringSession(n["session_string"]), self.api_id, self.api_hash,
            proxy=proxy,
            device_model=n.get("device_model", "Samsung Galaxy S22"),
            system_version=n.get("system_version", "Android 12"),
            app_version=n.get("app_version", "9.3.3"),
            connection_retries=2, retry_delay=3)

    async def _get_client(self, nid):
        n = self.db.get_number(nid)
        if not n: return None
        c = self._make_client(n)
        try:
            await asyncio.wait_for(c.connect(), timeout=15)
            if not await asyncio.wait_for(c.is_user_authorized(), timeout=5):
                await c.disconnect(); return None
            return c
        except Exception as e:
            logger.error(f"flash connect #{nid}: {e}")
            try: await c.disconnect()
            except Exception: pass
            return None

    async def _notify(self, uid, msg):
        try:
            if self.bot:
                await self.bot.send_message(uid, msg, parse_mode="Markdown")
        except Exception: pass

    # ── الحصول على مجموعات رقم ───────────────────────────────────────
    async def _get_groups(self, n, seen: set) -> list:
        groups = []
        c = await self._get_client(n["id"])
        if not c: return groups
        try:
            async for dlg in c.iter_dialogs(limit=2000):
                if not dlg.is_group: continue
                gid = dlg.entity.id
                if gid in seen: continue
                seen.add(gid)
                groups.append({"entity": dlg.entity, "title": dlg.name, "gid": gid})
        except Exception as e:
            logger.error(f"flash groups #{n['id']}: {e}")
        finally:
            try: await c.disconnect()
            except Exception: pass
        return groups

    # ── Worker لكل رقم (يعمل بالتوازي) ──────────────────────────────
    async def _turbo_worker(self, uid: int, num: dict, ad_cycle,
                            groups: list, camp: dict):
        nid  = num["id"]
        tail = num.get("phone", "")[-4:]
        nkey = str(nid)
        camp["num_status"][nkey] = "🟡 جاري الاتصال..."
        c = await self._get_client(nid)
        if not c:
            camp["num_status"][nkey] = "❌ فشل الاتصال"
            return

        self.db.set_number_busy(nid, True)
        camp["num_status"][nkey] = "🟢 يعمل"
        group_cycle = itertools.cycle(groups)
        wave = 0

        try:
            while True:
                if not camp.get("running"): break
                while camp.get("paused"):
                    camp["num_status"][nkey] = "🟡 موقوف مؤقتاً"
                    await asyncio.sleep(1)
                    if not camp.get("running"): break
                    camp["num_status"][nkey] = "🟢 يعمل"

                # تحقق من الـ blacklist
                if nid in camp.get("blacklist", set()):
                    bl_until = camp.get("blacklist_until", {}).get(nid, 0)
                    remain   = max(0, int(bl_until - time.time()))
                    if remain > 0:
                        camp["num_status"][nkey] = f"🔴 محظور {remain}ث"
                        await asyncio.sleep(5)
                        continue
                    else:
                        camp["blacklist"].discard(nid)
                        camp["num_status"][nkey] = "🟢 يعمل"

                ad_text = next(ad_cycle)
                group   = next(group_cycle)

                try:
                    await asyncio.wait_for(
                        c.send_message(group["entity"], ad_text), timeout=25)
                    camp["success"] += 1
                    camp["num_success"][nkey] = camp["num_success"].get(nkey, 0) + 1
                    camp["num_status"][nkey]  = "🟢 يعمل"
                    wave += 1

                    # دورة تدوير: بعد 500 رسالة -> راحة ثم موجة جديدة
                    if camp.get("rotation_24_7") and wave >= 500:
                        wave = 0
                        rest = camp.get("rotation_rest", 60)
                        camp["num_status"][nkey] = f"🟡 راحة {rest}ث"
                        await asyncio.sleep(rest)
                        random.shuffle(groups)

                except FloodWaitError as e:
                    wait = min(e.seconds, 600)
                    camp.setdefault("blacklist", set()).add(nid)
                    camp.setdefault("blacklist_until", {})[nid] = time.time() + wait
                    camp["num_status"][nkey] = f"🔴 FloodWait {wait}ث"
                    camp["flood"] = camp.get("flood", 0) + 1
                    self.db.add_violation(uid, nid, f"FloodWait {e.seconds}")
                    self.db.decrease_health(nid, 5, "FloodWait")
                    await self._notify(uid, f"⏳ Turbo: رقم ...{tail} محظور {wait}ث")
                    await asyncio.sleep(wait)
                    camp.setdefault("blacklist", set()).discard(nid)
                    camp["num_status"][nkey] = "🟢 يعمل"
                    continue

                except PeerFloodError:
                    camp["num_status"][nkey] = "🔴 PeerFlood"
                    camp["flood"] = camp.get("flood", 0) + 1
                    self.db.add_violation(uid, nid, "PeerFlood")
                    self.db.decrease_health(nid, 10, "PeerFlood")
                    await asyncio.sleep(120)
                    continue

                except (UserDeactivatedBanError, AuthKeyUnregisteredError):
                    camp["num_status"][nkey] = "❌ حساب موقوف"
                    await self._notify(uid, f"🚨 Turbo: رقم ...{tail} موقوف نهائياً!")
                    break

                except (ChatWriteForbiddenError, UserBannedInChannelError,
                        ChatAdminRequiredError, ChannelPrivateError):
                    camp.setdefault("radar_log", []).append(
                        f"❌ ممنوع: {group['title'][:20]}")
                    camp["fail"] = camp.get("fail", 0) + 1

                except SlowModeWaitError as e:
                    camp["num_status"][nkey] = f"🟡 SlowMode {e.seconds}ث"
                    await asyncio.sleep(min(e.seconds, 120))
                    continue

                except asyncio.TimeoutError:
                    camp["fail"] = camp.get("fail", 0) + 1
                    camp.setdefault("radar_log", []).append(
                        f"⏱️ Timeout: {group['title'][:20]}")

                except Exception as ex:
                    camp["fail"] = camp.get("fail", 0) + 1
                    camp.setdefault("radar_log", []).append(
                        f"⚠️ {type(ex).__name__}: {group['title'][:20]}")

                delay = random.uniform(
                    camp.get("min_delay", 8),
                    camp.get("max_delay", 20))
                await asyncio.sleep(delay)

        except asyncio.CancelledError:
            pass
        finally:
            camp["num_status"][nkey] = "⏹️ انتهى"
            self.db.set_number_busy(nid, False)
            try: await c.disconnect()
            except Exception: pass

    # ── Campaign Manager ──────────────────────────────────────────────
    async def _campaign_manager(self, uid: int):
        camp = self._campaigns[uid]
        sel_nids  = camp.get("selected_numbers", [])
        sel_adids = camp.get("selected_ads", [])

        all_nums = [n for n in self.db.get_user_numbers(uid) if n.get("is_active")]
        nums     = [n for n in all_nums if not sel_nids or n["id"] in sel_nids]
        all_ads  = self.db.fetch_all("SELECT id,content FROM ads WHERE user_id=?", (uid,))
        ads      = [a for a in all_ads if not sel_adids or a["id"] in sel_adids]

        if not nums or not ads:
            camp["running"] = False
            await self._notify(uid, "❌ Turbo: لا أرقام أو إعلانات مختارة.")
            return

        # جمع المجموعات بالتوازي
        seen = set()
        groups_per_num = {}
        gather_tasks = [self._get_groups(n, seen) for n in nums]
        results = await asyncio.gather(*gather_tasks, return_exceptions=True)
        all_groups = []
        for r in results:
            if isinstance(r, list): all_groups += r

        if not all_groups:
            camp["running"] = False
            await self._notify(uid, "❌ Turbo: لا مجموعات.")
            return

        camp["groups_count"]  = len(all_groups)
        camp["numbers_count"] = len(nums)
        camp["start_time"]    = time.time()
        camp["blacklist"]      = set()
        camp["blacklist_until"] = {}

        ad_texts = itertools.cycle([a["content"] for a in ads])

        # إطلاق كل الأرقام بالتوازي
        workers = [
            asyncio.create_task(
                self._turbo_worker(uid, num, ad_texts, all_groups, camp))
            for num in nums
        ]
        camp["workers"] = workers

        while camp.get("running"):
            await asyncio.sleep(5)
            elapsed = int(time.time() - camp["start_time"])
            camp["elapsed"] = elapsed
            total = camp.get("success", 0) + camp.get("fail", 0)
            camp["rate"] = round(total / max(elapsed / 60, 0.01), 1)
            if all(w.done() for w in workers): break

        camp["running"] = False
        for w in workers:
            if not w.done(): w.cancel()
        for w in workers:
            try: await w
            except asyncio.CancelledError: pass

        try:
            self.db.execute(
                "UPDATE users SET total_posts=total_posts+? WHERE user_id=?",
                (camp.get("success", 0), uid))
        except Exception: pass
        await self._notify(uid,
            f"⚡️ Turbo انتهى\n✅ نجح: {camp.get('success',0)} | ❌ فشل: {camp.get('fail',0)}")

    # ── واجهة التحكم العامة ───────────────────────────────────────────
    def is_turbo_active(self, uid: int) -> bool:
        return bool(self._campaigns.get(uid, {}).get("running"))

    async def start_turbo(self, uid: int, settings: dict) -> tuple:
        if self._turbo_lock.locked():
            return False, "⚠️ النظام قيد العمل في وضع Turbo، يرجى الإيقاف أولاً."
        async with self._turbo_lock:
            if self.is_turbo_active(uid):
                return False, "⚠️ التوربو يعمل بالفعل."
            self._campaigns[uid] = {
                "running": True, "paused": False,
                "success": 0, "fail": 0, "flood": 0,
                "elapsed": 0, "rate": 0,
                "groups_count": 0, "numbers_count": 0,
                "num_status": {}, "num_success": {},
                "radar_log": [],
                "selected_numbers": settings.get("selected_numbers", []),
                "selected_ads":     settings.get("selected_ads", []),
                "min_delay":        settings.get("min_delay", 8),
                "max_delay":        settings.get("max_delay", 20),
                "rotation_24_7":    settings.get("rotation_24_7", False),
                "rotation_rest":    settings.get("rotation_rest", 60),
            }
            asyncio.create_task(self._campaign_manager(uid))
            return True, "⚡️ تم إشعال المحرك التوربيني!"

    async def stop_turbo(self, uid: int):
        if uid in self._campaigns:
            self._campaigns[uid]["running"] = False
            self._campaigns[uid]["paused"]  = False


# ══════════════════════════════════════════════════════════════════════
#  FlashHandler — معالج الأزرار والواجهة
# ══════════════════════════════════════════════════════════════════════
class FlashHandler:
    def __init__(self, db, engine: FlashTurboEngine, admin_ids: list):
        self.db        = db
        self.eng       = engine
        self.admin_ids = admin_ids

    def _is_sub(self, uid):
        u = self.db.fetch_one(
            "SELECT subscription_end FROM users WHERE user_id=?", (uid,))
        if not u: return False
        try:
            from datetime import datetime as dt
            return dt.strptime(u["subscription_end"], "%Y-%m-%d") >= dt.now()
        except Exception:
            return False

    async def _safe_edit(self, q, text, kb=None):
        try:
            kw = {"parse_mode": ParseMode.MARKDOWN}
            if kb: kw["reply_markup"] = kb
            await q.edit_message_text(text, **kw)
        except Exception as e:
            if "not modified" not in str(e).lower():
                logger.debug(f"flash safe_edit: {e}")

    async def _safe_ans(self, q, text="", alert=False):
        try: await q.answer(text, show_alert=alert)
        except Exception: pass

    # ── اللوحة الرئيسية ──────────────────────────────────────────────
    async def flash_menu(self, update, ctx):
        uid = update.effective_user.id
        if not self._is_sub(uid) and uid not in self.admin_ids:
            if update.callback_query:
                await self._safe_ans(update.callback_query, "❌ لا يوجد اشتراك", True)
            return

        camp    = self.eng._campaigns.get(uid, {})
        active  = camp.get("running", False)
        is_24_7 = ctx.user_data.get("turbo_24_7", False)

        sel_nums = ctx.user_data.get("turbo_sel_nums", [])
        sel_ads  = ctx.user_data.get("turbo_sel_ads", [])
        total_nums = len(self.db.fetch_all(
            "SELECT id FROM numbers WHERE user_id=? AND is_active=1", (uid,)))
        total_ads  = len(self.db.fetch_all(
            "SELECT id FROM ads WHERE user_id=?", (uid,)))
        n_count = len(sel_nums) if sel_nums else total_nums
        a_count = len(sel_ads)  if sel_ads  else total_ads

        status_icon = "🟢 يعمل" if active else "⚪️ جاهز (Ready)"
        speed_note  = f"⚡️ السرعة: {camp.get('rate', 0)} رسالة/د" if active else "⚡️ السرعة: متوازي"

        text = (
            f"⚡️ *محرك النشر السريع (Flash Turbo Engine)*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🟢 الحالة: {status_icon} | 🔒 مانع التداخل: نشط ✅\n"
            f"📱 الأرقام المختارة: `{n_count}` | 📢 الإعلانات: `{a_count}`\n"
            f"📟 الوضع: Turbo (متوازي) | {speed_note}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"_النظام يعزل أي رقم محظور تلقائياً ويستمر بالبقية_"
        )
        if active:
            text += (
                f"\n\n📊 نجح: `{camp.get('success',0)}` | فشل: `{camp.get('fail',0)}`"
                f" | وقت: `{camp.get('elapsed',0)}ث`"
            )

        fire_btn = btn("⏸️ إيقاف المحرك", "flash_stop") if active else btn("🚀 إشعال المحرك التوربيني", "flash_start")
        rot_lbl  = f"🔄 تدوير 24/7: {'🟢' if is_24_7 else '🔴'}"

        kb = InlineKeyboardMarkup([
            [fire_btn],
            [btn("📱 اختيار الأرقام",        "flash_sel_nums"),
             btn("📢 اختيار الإعلانات",       "flash_sel_ads")],
            [btn("⚙️ الإعدادات الذكية",       "flash_settings"),
             btn("📢 بنك الإعلانات",           "flash_ad_bank")],
            [btn("📱 مراقبة الأرقام (Live)",   "flash_live"),
             btn("📊 تقرير الرادار",           "flash_radar")],
            [btn(rot_lbl,                       "flash_toggle_24_7"),
             btn("🧹 التنظيف الذكي",           "flash_clean_menu")],
            [btn("🔙 خروج للرئيسية",           "main_menu")],
        ])
        if update.callback_query:
            await self._safe_edit(update.callback_query, text, kb)
        else:
            await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)

    # ── تشغيل / إيقاف ────────────────────────────────────────────────
    async def flash_start(self, update, ctx):
        uid = update.effective_user.id
        await self._safe_ans(update.callback_query)
        settings = {
            "selected_numbers": ctx.user_data.get("turbo_sel_nums", []),
            "selected_ads":     ctx.user_data.get("turbo_sel_ads", []),
            "min_delay":        ctx.user_data.get("turbo_min_delay", 8),
            "max_delay":        ctx.user_data.get("turbo_max_delay", 20),
            "rotation_24_7":    ctx.user_data.get("turbo_24_7", False),
            "rotation_rest":    ctx.user_data.get("turbo_rest", 60),
        }
        ok, msg = await self.eng.start_turbo(uid, settings)
        await self._safe_ans(update.callback_query, msg, not ok)
        await self.flash_menu(update, ctx)

    async def flash_stop(self, update, ctx):
        uid = update.effective_user.id
        await self.eng.stop_turbo(uid)
        await self._safe_ans(update.callback_query, "⏹️ تم الإيقاف")
        await self.flash_menu(update, ctx)

    # ── اختيار الأرقام ───────────────────────────────────────────────
    async def flash_sel_nums(self, update, ctx):
        uid  = update.effective_user.id
        nums = self.db.fetch_all(
            "SELECT id, phone, health, is_active FROM numbers WHERE user_id=? AND is_active=1",
            (uid,))
        if not nums:
            await self._safe_ans(update.callback_query, "❌ لا توجد أرقام نشطة", True); return
        sel = set(ctx.user_data.get("turbo_sel_nums", []))
        rows = []
        for n in nums:
            tail = n["phone"][-4:]
            icon = "✅" if n["id"] in sel else "◻️"
            rows.append([btn(f"{icon} ...{tail} | صحة: {n['health']}%",
                             f"flash_num_{n['id']}")])
        rows.append([btn("✅ تحديد الكل", "flash_num_all"),
                     btn("❌ إلغاء الكل",  "flash_num_none")])
        rows.append([btn("🔙 رجوع", "flash_menu")])
        count = len(sel) if sel else len(nums)
        await self._safe_edit(update.callback_query,
            f"📱 *اختيار الأرقام*\nمحدد: `{count}`/{len(nums)}\n"
            "_اضغط على رقم لتحديده/إلغائه_",
            InlineKeyboardMarkup(rows))

    async def flash_toggle_num(self, update, ctx, nid: int):
        sel = set(ctx.user_data.get("turbo_sel_nums", []))
        if nid in sel: sel.discard(nid)
        else: sel.add(nid)
        ctx.user_data["turbo_sel_nums"] = list(sel)
        await self._safe_ans(update.callback_query)
        await self.flash_sel_nums(update, ctx)

    async def flash_num_all(self, update, ctx):
        uid  = update.effective_user.id
        nums = self.db.fetch_all(
            "SELECT id FROM numbers WHERE user_id=? AND is_active=1", (uid,))
        ctx.user_data["turbo_sel_nums"] = [n["id"] for n in nums]
        await self._safe_ans(update.callback_query, "✅ تم تحديد الكل")
        await self.flash_sel_nums(update, ctx)

    async def flash_num_none(self, update, ctx):
        ctx.user_data["turbo_sel_nums"] = []
        await self._safe_ans(update.callback_query, "❌ تم إلغاء الكل")
        await self.flash_sel_nums(update, ctx)

    # ── اختيار الإعلانات ─────────────────────────────────────────────
    async def flash_sel_ads(self, update, ctx):
        uid = update.effective_user.id
        ads = self.db.fetch_all("SELECT id, title, content FROM ads WHERE user_id=?", (uid,))
        if not ads:
            await self._safe_ans(update.callback_query, "❌ لا توجد إعلانات", True); return
        sel = set(ctx.user_data.get("turbo_sel_ads", []))
        rows = []
        for a in ads:
            lbl  = a.get("title") or a["content"][:25]
            icon = "✅" if a["id"] in sel else "◻️"
            rows.append([btn(f"{icon} {lbl}", f"flash_ad_{a['id']}")])
        rows.append([btn("✅ تحديد الكل", "flash_ad_all"),
                     btn("❌ إلغاء الكل",  "flash_ad_none")])
        rows.append([btn("🔙 رجوع", "flash_menu")])
        count = len(sel) if sel else len(ads)
        await self._safe_edit(update.callback_query,
            f"📢 *اختيار الإعلانات*\nمحدد: `{count}`/{len(ads)}\n"
            "_اضغط على إعلان لتحديده/إلغائه_",
            InlineKeyboardMarkup(rows))

    async def flash_toggle_ad(self, update, ctx, aid: int):
        sel = set(ctx.user_data.get("turbo_sel_ads", []))
        if aid in sel: sel.discard(aid)
        else: sel.add(aid)
        ctx.user_data["turbo_sel_ads"] = list(sel)
        await self._safe_ans(update.callback_query)
        await self.flash_sel_ads(update, ctx)

    async def flash_ad_all(self, update, ctx):
        uid = update.effective_user.id
        ads = self.db.fetch_all("SELECT id FROM ads WHERE user_id=?", (uid,))
        ctx.user_data["turbo_sel_ads"] = [a["id"] for a in ads]
        await self._safe_ans(update.callback_query, "✅ تم تحديد الكل")
        await self.flash_sel_ads(update, ctx)

    async def flash_ad_none(self, update, ctx):
        ctx.user_data["turbo_sel_ads"] = []
        await self._safe_ans(update.callback_query, "❌ تم إلغاء الكل")
        await self.flash_sel_ads(update, ctx)

    # ── بنك الإعلانات ────────────────────────────────────────────────
    async def flash_ad_bank(self, update, ctx):
        uid = update.effective_user.id
        ads = self.db.fetch_all("SELECT id, title, content FROM ads WHERE user_id=?", (uid,))
        text = f"📢 *بنك الإعلانات* — {len(ads)} إعلان\n━━━━━━━━━━━━━━━━━━━━━━\n"
        for a in ads[:15]:
            lbl = a.get("title") or a["content"][:30]
            text += f"• `{a['id']}` {lbl}\n"
        if len(ads) > 15:
            text += f"...و{len(ads)-15} آخرين\n"
        kb = InlineKeyboardMarkup([
            [btn("➕ إضافة إعلان جديد", "flash_ad_add")],
            [btn("🗑 حذف إعلان",        "flash_ad_del_list")],
            [btn("🔙 رجوع",             "flash_menu")],
        ])
        await self._safe_edit(update.callback_query, text, kb)

    async def flash_ad_add_prompt(self, update, ctx):
        await self._safe_edit(update.callback_query,
            "📝 *إضافة إعلان*\nأرسل: `اسم_الإعلان|نص الإعلان`\nمثال: `إعلاني|هذا إعلاني الرائع...`",
            back("flash_ad_bank"))
        ctx.user_data["state"] = "FLASH_ADD_AD"

    async def flash_ad_del_list(self, update, ctx):
        uid = update.effective_user.id
        ads = self.db.fetch_all("SELECT id, title, content FROM ads WHERE user_id=?", (uid,))
        if not ads:
            await self._safe_ans(update.callback_query, "❌ لا توجد إعلانات", True); return
        rows = []
        for a in ads[:20]:
            lbl = a.get("title") or a["content"][:25]
            rows.append([btn(f"🗑️ {lbl}", f"flash_ad_del_{a['id']}")])
        rows.append([btn("🔙 رجوع", "flash_ad_bank")])
        await self._safe_edit(update.callback_query,
            "🗑 *حذف إعلان* — اختر الإعلان:",
            InlineKeyboardMarkup(rows))

    async def flash_ad_del_confirm(self, update, ctx, aid: int):
        a = self.db.fetch_one("SELECT title, content FROM ads WHERE id=?", (aid,))
        if not a:
            await self._safe_ans(update.callback_query, "❌ الإعلان غير موجود", True); return
        lbl = a.get("title") or a["content"][:30]
        kb = InlineKeyboardMarkup([
            [btn("✅ تأكيد الحذف", f"flash_ad_del_exec_{aid}")],
            [btn("❌ إلغاء",        "flash_ad_del_list")],
        ])
        await self._safe_edit(update.callback_query,
            f"⚠️ *تأكيد حذف الإعلان*\n\n`{lbl}`\n\nهل تريد حذف هذا الإعلان؟", kb)

    async def flash_ad_del_execute(self, update, ctx, aid: int):
        uid = update.effective_user.id
        self.db.execute("DELETE FROM ads WHERE id=? AND user_id=?", (aid, uid))
        await self._safe_ans(update.callback_query, "✅ تم الحذف")
        await self.flash_ad_bank(update, ctx)

    # ── الإعدادات الذكية ─────────────────────────────────────────────
    async def flash_settings(self, update, ctx):
        min_d = ctx.user_data.get("turbo_min_delay", 8)
        max_d = ctx.user_data.get("turbo_max_delay", 20)
        rest  = ctx.user_data.get("turbo_rest", 60)
        text  = (
            f"⚙️ *الإعدادات الذكية*\n━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⏱️ تأخير بين الرسائل: `{min_d}` - `{max_d}` ثانية\n"
            f"🔄 راحة التدوير: `{rest}` ثانية\n"
        )
        kb = InlineKeyboardMarkup([
            [btn("⏱️ تأخير أسرع (5-10ث)",  "flash_delay_fast"),
             btn("⏱️ تأخير متوسط (8-20ث)",  "flash_delay_med")],
            [btn("⏱️ تأخير آمن (15-40ث)",   "flash_delay_safe")],
            [btn("🔄 راحة 30ث",  "flash_rest_30"),
             btn("🔄 راحة 60ث",  "flash_rest_60"),
             btn("🔄 راحة 120ث", "flash_rest_120")],
            [btn("🔙 رجوع", "flash_menu")],
        ])
        await self._safe_edit(update.callback_query, text, kb)

    async def flash_set_delay(self, update, ctx, mn: int, mx: int):
        ctx.user_data["turbo_min_delay"] = mn
        ctx.user_data["turbo_max_delay"] = mx
        await self._safe_ans(update.callback_query, f"✅ تأخير: {mn}-{mx}ث")
        await self.flash_settings(update, ctx)

    async def flash_set_rest(self, update, ctx, rest: int):
        ctx.user_data["turbo_rest"] = rest
        await self._safe_ans(update.callback_query, f"✅ راحة: {rest}ث")
        await self.flash_settings(update, ctx)

    # ── تدوير 24/7 ───────────────────────────────────────────────────
    async def flash_toggle_24_7(self, update, ctx):
        cur = ctx.user_data.get("turbo_24_7", False)
        ctx.user_data["turbo_24_7"] = not cur
        # تحديث الحملة الجارية إن وجدت
        uid  = update.effective_user.id
        camp = self.eng._campaigns.get(uid)
        if camp: camp["rotation_24_7"] = not cur
        await self._safe_ans(update.callback_query,
            f"{'🟢 تم تفعيل التدوير 24/7' if not cur else '🔴 تم إيقاف التدوير'}")
        await self.flash_menu(update, ctx)

    # ── مراقبة حية ───────────────────────────────────────────────────
    async def flash_live(self, update, ctx):
        uid  = update.effective_user.id
        camp = self.eng._campaigns.get(uid)
        if not camp or not camp.get("running"):
            await self._safe_edit(update.callback_query,
                "📱 *مراقبة الأرقام*\n\n_المحرك غير مشغّل حالياً_",
                back("flash_menu")); return

        nums = self.db.fetch_all(
            "SELECT id, phone FROM numbers WHERE user_id=? AND is_active=1", (uid,))
        text = (
            f"📱 *مراقبة الأرقام (Live)*\n━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⏱️ وقت: `{camp.get('elapsed',0)}ث` | "
            f"⚡️ معدل: `{camp.get('rate',0)}` رسالة/د\n"
            f"✅ نجح: `{camp.get('success',0)}` | ❌ فشل: `{camp.get('fail',0)}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
        )
        ns = camp.get("num_status", {})
        nsucc = camp.get("num_success", {})
        for n in nums:
            nkey   = str(n["id"])
            tail   = n["phone"][-4:]
            status = ns.get(nkey, "⚪️ غير نشط")
            sent   = nsucc.get(nkey, 0)
            text  += f"`...{tail}` {status} | أرسل: {sent}\n"
        kb = InlineKeyboardMarkup([
            [btn("🔄 تحديث", "flash_live"),
             btn("⏸️ إيقاف التوربو", "flash_stop")],
            [btn("🔙 رجوع", "flash_menu")],
        ])
        await self._safe_edit(update.callback_query, text, kb)

    # ── تقرير الرادار ────────────────────────────────────────────────
    async def flash_radar(self, update, ctx):
        uid  = update.effective_user.id
        camp = self.eng._campaigns.get(uid, {})
        radar_log = camp.get("radar_log", [])

        # تحليل أسباب الفشل
        fail_reasons: dict = {}
        for entry in radar_log:
            key = entry.split(":")[0].strip() if ":" in entry else entry[:20]
            fail_reasons[key] = fail_reasons.get(key, 0) + 1

        text = (
            f"📊 *تقرير الرادار*\n━━━━━━━━━━━━━━━━━━━━━━\n"
            f"إجمالي الإرسال: `{camp.get('success',0) + camp.get('fail',0)}`\n"
            f"✅ نجاح: `{camp.get('success',0)}` | "
            f"❌ فشل: `{camp.get('fail',0)}` | "
            f"⏳ Flood: `{camp.get('flood',0)}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"*أسباب الفشل:*\n"
        )
        if fail_reasons:
            for reason, cnt in sorted(fail_reasons.items(), key=lambda x: -x[1])[:10]:
                text += f"  • {reason}: `{cnt}`\n"
        else:
            text += "  _لا أخطاء مسجلة_\n"

        if radar_log:
            text += f"\n*آخر أحداث:*\n"
            for entry in radar_log[-8:]:
                text += f"  • {entry}\n"

        await self._safe_edit(update.callback_query, text, back("flash_menu"))

    # ── التنظيف الذكي ────────────────────────────────────────────────
    async def flash_clean_menu(self, update, ctx):
        kb = InlineKeyboardMarkup([
            [btn("👯 تصفية المكرر",  "flash_clean_dup"),
             btn("💀 تنظيف الميت",   "flash_clean_dead")],
            [btn("🔙 رجوع",          "flash_menu")],
        ])
        await self._safe_edit(update.callback_query,
            "🧹 *التنظيف الذكي*\n━━━━━━━━━━━━━━━━━━━━━━\n"
            "• **تصفية المكرر**: حذف المجموعات المكررة في قاعدة البيانات\n"
            "• **تنظيف الميت**: حذف المجموعات التي سجّل لها أخطاء متكررة",
            kb)

    async def flash_clean_dup(self, update, ctx):
        uid = update.effective_user.id
        # إحصاء التكرارات: نفس group_id لأكثر من رقم
        dups = self.db.fetch_all(
            "SELECT group_id, COUNT(*) as c FROM groups g "
            "JOIN numbers n ON g.number_id=n.id "
            "WHERE n.user_id=? "
            "GROUP BY group_id HAVING c > 1", (uid,))
        total_dup = sum(d["c"] - 1 for d in dups)
        kb = InlineKeyboardMarkup([
            [btn(f"✅ تأكيد حذف {total_dup} تكرار", "flash_clean_dup_exec")],
            [btn("❌ إلغاء", "flash_clean_menu")],
        ])
        await self._safe_edit(update.callback_query,
            f"👯 *تصفية المكرر*\n━━━━━━━━━━━━━━━━━━━━━━\n"
            f"وجدنا `{total_dup}` تكراراً في `{len(dups)}` مجموعة.\n"
            f"هل تريد الإبقاء على نسخة واحدة لكل مجموعة؟", kb)

    async def flash_clean_dup_execute(self, update, ctx):
        uid = update.effective_user.id
        # احتفظ بأصغر id لكل group_id وأحذف الباقي
        self.db.execute(
            "DELETE FROM groups WHERE id NOT IN ("
            "  SELECT MIN(id) FROM groups g "
            "  JOIN numbers n ON g.number_id=n.id "
            "  WHERE n.user_id=? "
            "  GROUP BY g.group_id"
            ")", (uid,))
        await self._safe_ans(update.callback_query, "✅ تم تنظيف التكرارات")
        await self.flash_clean_menu(update, ctx)

    async def flash_clean_dead(self, update, ctx):
        uid  = update.effective_user.id
        camp = self.eng._campaigns.get(uid, {})
        radar_log = camp.get("radar_log", [])
        # المجموعات الميتة: تلك التي ظهرت في radar_log بأخطاء ممنوع/ChannelPrivate
        dead_titles = set()
        for entry in radar_log:
            if "ممنوع" in entry or "ChannelPrivate" in entry or "ChatWriteForbidden" in entry:
                parts = entry.split(":")
                if len(parts) > 1:
                    dead_titles.add(parts[-1].strip())
        cnt = len(dead_titles)
        kb = InlineKeyboardMarkup([
            [btn(f"✅ تأكيد حذف {cnt} مجموعة", "flash_clean_dead_exec")],
            [btn("❌ إلغاء", "flash_clean_menu")],
        ])
        preview = "\n".join(f"• {t}" for t in list(dead_titles)[:8])
        await self._safe_edit(update.callback_query,
            f"💀 *تنظيف الميت*\n━━━━━━━━━━━━━━━━━━━━━━\n"
            f"وجدنا `{cnt}` مجموعة ميتة:\n{preview}\n\n"
            f"هل تريد حذفها من قاعدة البيانات؟", kb)

    async def flash_clean_dead_execute(self, update, ctx):
        uid   = update.effective_user.id
        camp  = self.eng._campaigns.get(uid, {})
        radar = camp.get("radar_log", [])
        dead_titles = set()
        for entry in radar:
            if "ممنوع" in entry or "ChannelPrivate" in entry:
                parts = entry.split(":")
                if len(parts) > 1:
                    dead_titles.add(parts[-1].strip())
        count = 0
        for title in dead_titles:
            n = self.db.execute(
                "DELETE FROM groups WHERE group_title=? AND number_id IN "
                "(SELECT id FROM numbers WHERE user_id=?)", (title, uid))
            count += 1
        await self._safe_ans(update.callback_query, f"✅ تم حذف {count} مجموعة")
        await self.flash_clean_menu(update, ctx)

    # ── معالج الرسائل النصية (إضافة إعلان) ──────────────────────────
    async def handle_message(self, update, ctx):
        state = ctx.user_data.get("state", "")
        if state == "FLASH_ADD_AD":
            uid  = update.effective_user.id
            text = (update.message.text or "").strip()
            if "|" in text:
                parts = text.split("|", 1)
                title   = parts[0].strip()
                content = parts[1].strip()
            else:
                title   = ""
                content = text
            if not content:
                await update.message.reply_text("❌ النص فارغ."); return
            self.db.execute(
                "INSERT INTO ads(user_id, title, content) VALUES(?,?,?)",
                (uid, title, content))
            ctx.user_data.pop("state", None)
            await update.message.reply_text(
                f"✅ تمت الإضافة!\n📢 العنوان: {title or '—'}\n"
                f"📝 المحتوى: {content[:50]}...",
                parse_mode=ParseMode.MARKDOWN)
