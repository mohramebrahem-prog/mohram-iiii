# -*- coding: utf-8 -*-
import asyncio, logging, random, time, itertools
from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError, ChatWriteForbiddenError, UserBannedInChannelError,
    ChatAdminRequiredError, SlowModeWaitError, PeerFloodError,
    UserDeactivatedBanError, AuthKeyUnregisteredError, ChannelPrivateError,
)
from telethon.tl.functions.messages import SetTypingRequest
from telethon.tl.types import SendMessageTypingAction
from telethon.sessions import StringSession
import helpers

logger = logging.getLogger(__name__)

class PublishService:
    def __init__(self, db, api_id, api_hash, bot=None):
        self.db          = db
        self.api_id      = api_id
        self.api_hash    = api_hash
        self.bot         = bot
        self._campaigns  = {}
        self._active_cnt = 0

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
            logger.error(f"connect #{nid}: {e}")
            try: await c.disconnect()
            except Exception: pass
            return None

    async def _notify(self, uid, msg):
        try: await self.bot.send_message(uid, msg, parse_mode="Markdown")
        except Exception: pass

    def _log(self, stats, entry):
        stats["log"].append(entry)
        if len(stats["log"]) > 60: stats["log"] = stats["log"][-60:]

    def _rec_fail(self, stats, reason, title=""):
        stats["fail"] += 1
        stats["fail_reasons"][reason] = stats["fail_reasons"].get(reason, 0) + 1
        self._log(stats, f"❌ {reason}: {title[:18]}")

    async def _groups_for_number(self, num, seen, deduplicate):
        groups = []
        c = await self._get_client(num["id"])
        if not c: return groups
        try:
            async for dlg in c.iter_dialogs(limit=1000):
                if not dlg.is_group: continue
                gid = dlg.entity.id
                if deduplicate and gid in seen: continue
                seen.add(gid)
                groups.append({"entity": dlg.entity, "title": dlg.name})
        except Exception as e:
            logger.error(f"collect #{num['id']}: {e}")
        finally:
            try: await c.disconnect()
            except Exception: pass
        return groups

    async def _worker(self, uid, num, ad_cycle, groups, settings, stats):
        c = await self._get_client(num["id"])
        if not c:
            stats["num_status"][str(num["id"])] = "❌ فشل الاتصال"
            self._active_cnt = max(0, self._active_cnt - 1)
            return

        self.db.set_number_busy(num["id"], True)
        nkey = str(num["id"])
        stats["num_status"][nkey] = "🟢 يعمل"
        tail = num.get("phone", "")[-4:]

        group_cycle = itertools.cycle(groups)
        fatal = False

        try:
            while True:
                camp = self._campaigns.get(uid)
                if not camp or not camp.get("running"): break
                while camp.get("paused"):
                    await asyncio.sleep(1)
                    camp = self._campaigns.get(uid)
                    if not camp: break

                ad_text = next(ad_cycle)
                group   = next(group_cycle)
                entity  = group["entity"]
                title   = group["title"]

                mn = settings.get("min_delay", 30)
                mx = settings.get("max_delay", 60)

                try:
                    if settings.get("typing"):
                        try: await c(SetTypingRequest(entity, SendMessageTypingAction()))
                        except Exception: pass
                        await asyncio.sleep(random.uniform(1, 3))

                    await asyncio.wait_for(
                        c.send_message(entity, ad_text), timeout=20)
                    stats["success"] += 1
                    stats["num_success"][nkey] = stats["num_success"].get(nkey, 0) + 1
                    self._log(stats, f"✅ ...{tail}: {title[:20]}")

                except FloodWaitError as e:
                    wait = min(e.seconds, 300)
                    stats["flood"] += 1
                    self.db.add_violation(uid, num["id"], f"FloodWait {e.seconds}")
                    self.db.decrease_health(num["id"], 5, "FloodWait")
                    self._log(stats, f"⏳ FloodWait {e.seconds}ث")
                    await self._notify(uid, f"⏳ رقم ...{tail}: FloodWait {e.seconds}ث")
                    await asyncio.sleep(wait)
                    continue

                except PeerFloodError:
                    stats["flood"] += 1
                    self.db.add_violation(uid, num["id"], "PeerFlood")
                    self.db.decrease_health(num["id"], 10, "PeerFlood")
                    self._log(stats, "⚠️ PeerFlood")
                    await asyncio.sleep(60)
                    continue

                except (UserDeactivatedBanError, AuthKeyUnregisteredError):
                    stats["num_status"][nkey] = "❌ حساب موقوف"
                    self._log(stats, f"🚨 ...{tail}: حساب موقوف")
                    await self._notify(uid, f"🚨 رقم ...{tail} موقوف!")
                    fatal = True
                    break

                except (ChatWriteForbiddenError, UserBannedInChannelError,
                        ChatAdminRequiredError, ChannelPrivateError):
                    self._rec_fail(stats, "ممنوع", title)

                except SlowModeWaitError as e:
                    self._log(stats, f"🐢 SlowMode {e.seconds}ث: {title[:15]}")
                    await asyncio.sleep(min(e.seconds, 120))
                    continue

                except asyncio.TimeoutError:
                    self._rec_fail(stats, "Timeout", title)

                except Exception as ex:
                    self._rec_fail(stats, type(ex).__name__, title)

                if not fatal:
                    delay = random.uniform(mn, mx)
                    await asyncio.sleep(delay)

        except asyncio.CancelledError:
            pass
        finally:
            stats["num_status"][nkey] = "⏹️ انتهى" if not fatal else "❌ موقوف"
            self._active_cnt = max(0, self._active_cnt - 1)
            self.db.set_number_busy(num["id"], False)
            try: await c.disconnect()
            except Exception: pass

    async def _campaign_manager(self, uid, settings):
        camp  = self._campaigns[uid]
        s     = self.db.fetch_one("SELECT deduplicate FROM settings WHERE user_id=?", (uid,))
        dedup = bool((s or {}).get("deduplicate", 1))
        sel_nids  = camp.get("selected_numbers", [])
        sel_adids = camp.get("selected_ads", [])

        all_nums = [n for n in self.db.get_user_numbers(uid) if n["is_active"]]
        nums     = [n for n in all_nums if not sel_nids or n["id"] in sel_nids]
        all_ads  = self.db.fetch_all("SELECT id,content FROM ads WHERE user_id=?", (uid,))
        ads      = [a for a in all_ads if not sel_adids or a["id"] in sel_adids]

        if not nums or not ads:
            camp["running"] = False
            await self._notify(uid, "❌ لا توجد أرقام أو إعلانات.")
            return

        seen   = set()
        groups = []
        for num in nums:
            groups += await self._groups_for_number(num, seen, dedup)

        if not groups:
            camp["running"] = False
            await self._notify(uid, "❌ لا توجد مجموعات.")
            return

        camp["groups_count"]   = len(groups)
        camp["numbers_count"]  = len(nums)
        camp["active_workers"] = 0

        ad_texts  = [a["content"] for a in ads]
        ad_cycle  = itertools.cycle(ad_texts)

        workers = [asyncio.create_task(
            self._worker(uid, num, ad_cycle, groups, settings, camp))
            for num in nums]
        self._active_cnt += len(workers)
        camp["active_workers"] = len(workers)

        start = time.time()
        while camp.get("running"):
            await asyncio.sleep(10)
            camp["elapsed"] = int(time.time() - start)
            total = camp["success"] + camp["fail"]
            camp["rate"] = round(total / max(camp["elapsed"]/60, 0.01), 1)
            if all(w.done() for w in workers):
                break

        camp["running"] = False
        for w in workers:
            if not w.done(): w.cancel()
        for w in workers:
            try: await w
            except asyncio.CancelledError: pass

        try:
            self.db.execute("UPDATE users SET total_posts=total_posts+? WHERE user_id=?",
                            (camp["success"], uid))
        except Exception: pass

    async def start_publish(self, uid, settings, selected_numbers=None, selected_ads=None):
        if uid in self._campaigns and self._campaigns[uid].get("running"):
            return False, "⚠️ النشر جارٍ بالفعل"
        self._campaigns[uid] = {
            "running": True, "paused": False,
            "success": 0, "fail": 0, "flood": 0,
            "elapsed": 0, "rate": 0,
            "groups_count": 0, "numbers_count": 0, "active_workers": 0,
            "fail_reasons": {}, "num_status": {}, "num_success": {},
            "log": [],
            "selected_numbers": selected_numbers or [],
            "selected_ads": selected_ads or [],
        }
        asyncio.create_task(self._campaign_manager(uid, settings))
        return True, "🚀 بدأ النشر!"

    async def stop_publish(self, uid):
        if uid in self._campaigns:
            self._campaigns[uid]["running"] = False
            self._campaigns[uid]["paused"]  = False
            return True
        return False

    async def pause_publish(self, uid):
        if uid in self._campaigns and self._campaigns[uid].get("running"):
            self._campaigns[uid]["paused"] = True
            return True
        return False

    async def resume_publish(self, uid):
        if uid in self._campaigns:
            self._campaigns[uid]["paused"] = False
            return True
        return False

    async def get_progress(self, uid):
        camp = self._campaigns.get(uid)
        if not camp: return None
        return camp
