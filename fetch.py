# -*- coding: utf-8 -*-
"""
FetchService v3.0 — البحث الذكي المباشر
- بحث مباشر داخل كل محادثة بدل قراءة الرسائل واحدة واحدة
- task منفصل في الخلفية — البوت لا يتجمد
- راحة كل 50 محادثة (30 ثانية) للأمان
- تأخير 1-2 ثانية عشوائي بين المحادثات
- تحديث Progress كل 10 محادثات
"""
import asyncio, logging, random, re, time
from datetime import datetime, timedelta, timezone
from telethon import TelegramClient
from telethon.errors import FloodWaitError, ChannelPrivateError, ChatAdminRequiredError
from telethon.sessions import StringSession
import utils as helpers

logger = logging.getLogger(__name__)

TG_RE = re.compile(
    r"https?://t\.me/(?:joinchat/[a-zA-Z0-9_\-]+|\+[a-zA-Z0-9_\-]+|[a-zA-Z0-9_]{5,})"
)
WA_RE = re.compile(r"https?://chat\.whatsapp\.com/[\w\d\-_]{10,}")

_FLOOD_MAX       = 300
_DELAY_MIN       = 1.0
_DELAY_MAX       = 2.5
_BIG_BREAK_EVERY = 50
_BIG_BREAK_SEC   = 30
_PROG_EVERY      = 10
_SEARCH_LIMIT    = 200


class FetchService:
    def __init__(self, db, api_id, api_hash):
        self.db          = db
        self.api_id      = api_id
        self.api_hash    = api_hash
        self._running    = {}
        self._break_flag = {}
        self._temp_links = []

    def _make_client(self, n):
        proxy = helpers.parse_proxy(n.get("proxy")) if n.get("proxy") else None
        return TelegramClient(
            StringSession(n["session_string"]), self.api_id, self.api_hash,
            proxy=proxy,
            device_model=n.get("device_model", "Samsung Galaxy S22"),
            system_version=n.get("system_version", "Android 12"),
            app_version=n.get("app_version", "9.3.3"))

    def _get_existing_links(self):
        try:
            rows = self.db.fetch_all("SELECT url FROM fetched_links") or []
            return {r["url"] for r in rows}
        except Exception:
            return set()

    def _save_links_batch(self, links_list):
        if not links_list:
            return
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.db.execute_many(
                "INSERT OR IGNORE INTO fetched_links (url, fetched_at) VALUES (?, ?)",
                [(url, now) for url in links_list])
        except Exception as e:
            logger.warning(f"save_links_batch: {e}")

    async def _search_dialog(self, client, dialog, link_type, cutoff_aware):
        """بحث مباشر داخل محادثة واحدة عن الكلمة المفتاحية."""
        found_tg = set()
        found_wa = set()

        keywords = []
        if link_type in ("telegram", "both"):
            keywords.append(("tg", "t.me/"))
        if link_type in ("whatsapp", "both"):
            keywords.append(("wa", "chat.whatsapp.com/"))

        for ktype, kword in keywords:
            try:
                async for msg in client.iter_messages(
                        dialog, search=kword, limit=_SEARCH_LIMIT):
                    if not msg or not msg.date:
                        continue
                    msg_date = msg.date
                    if msg_date.tzinfo is None:
                        msg_date = msg_date.replace(tzinfo=timezone.utc)
                    if msg_date < cutoff_aware:
                        break
                    text = msg.text or ""
                    if not text:
                        continue
                    if ktype == "tg":
                        for lnk in TG_RE.findall(text):
                            found_tg.add(lnk)
                    else:
                        for lnk in WA_RE.findall(text):
                            found_wa.add(lnk)
            except (ChannelPrivateError, ChatAdminRequiredError):
                pass
            except FloodWaitError as e:
                wait = min(e.seconds + 5, _FLOOD_MAX)
                logger.warning(f"FloodWait {wait}s")
                await asyncio.sleep(wait)
            except Exception as ex:
                logger.debug(f"search_dialog: {ex}")

        return found_tg, found_wa

    async def fetch_links(self, uid, nid, link_type="both", days=7,
                          progress_cb=None, break_cb=None, done_cb=None):
        """
        يشتغل في asyncio.create_task — لا يجمد البوت.
        progress_cb(done, total, tg_count, wa_count, dup_count)
        break_cb(remaining_seconds)
        done_cb(tg_list, wa_list, stats)
        """
        self._running[uid]    = True
        self._break_flag[uid] = False
        stats = {"dialogs": 0, "new": 0, "dup": 0, "error": "", "start": time.time()}

        n = self.db.get_number(nid)
        if not n:
            if done_cb:
                await done_cb([], [], {**stats, "error": "رقم غير موجود"})
            self._running.pop(uid, None)
            return

        client = self._make_client(n)
        try:
            await asyncio.wait_for(client.connect(), timeout=20)
            if not await asyncio.wait_for(client.is_user_authorized(), timeout=5):
                if done_cb:
                    await done_cb([], [], {**stats, "error": "جلسة منتهية"})
                self._running.pop(uid, None)
                try: await client.disconnect()
                except Exception: pass
                return
        except Exception as e:
            try: await client.disconnect()
            except Exception: pass
            if done_cb:
                await done_cb([], [], {**stats, "error": str(e)})
            self._running.pop(uid, None)
            return

        existing  = self._get_existing_links()
        tg_new    = set()
        wa_new    = set()
        dup_count = 0
        cutoff_aware = datetime.now(timezone.utc) - timedelta(days=days)

        try:
            # جلب قائمة المحادثات مرة واحدة فقط
            dialogs = [d async for d in client.iter_dialogs(limit=3000)
                       if d.is_group or d.is_channel]
            stats["dialogs"] = len(dialogs)

            for i, dialog in enumerate(dialogs):
                if not self._running.get(uid):
                    break

                # راحة كبيرة كل 50 محادثة
                if i > 0 and i % _BIG_BREAK_EVERY == 0:
                    self._break_flag[uid] = True
                    for sec in range(_BIG_BREAK_SEC, 0, -1):
                        if not self._running.get(uid):
                            break
                        if break_cb:
                            try: await break_cb(sec)
                            except Exception: pass
                        await asyncio.sleep(1)
                    self._break_flag[uid] = False

                if not self._running.get(uid):
                    break

                # بحث ذكي داخل المحادثة
                dlg_tg, dlg_wa = await self._search_dialog(
                    client, dialog, link_type, cutoff_aware)

                for lnk in dlg_tg:
                    if lnk in existing or lnk in tg_new:
                        dup_count += 1
                    else:
                        tg_new.add(lnk)

                for lnk in dlg_wa:
                    if lnk in existing or lnk in wa_new:
                        dup_count += 1
                    else:
                        wa_new.add(lnk)

                # تأخير عشوائي بين المحادثات
                await asyncio.sleep(random.uniform(_DELAY_MIN, _DELAY_MAX))

                # تحديث progress كل 10 محادثات
                if progress_cb and (i + 1) % _PROG_EVERY == 0:
                    try:
                        await progress_cb(
                            i + 1, len(dialogs),
                            len(tg_new), len(wa_new), dup_count)
                    except Exception:
                        pass

        finally:
            self._running.pop(uid, None)
            self._break_flag.pop(uid, None)
            try: await client.disconnect()
            except Exception: pass

        all_new      = list(tg_new) + list(wa_new)
        stats["new"] = len(all_new)
        stats["dup"] = dup_count

        self._save_links_batch(all_new)
        self._temp_links.extend(all_new)

        if all_new:
            try:
                self.db.execute(
                    "UPDATE users SET total_fetches=total_fetches+1 WHERE user_id=?",
                    (uid,))
            except Exception:
                pass

        if done_cb:
            try: await done_cb(list(tg_new), list(wa_new), stats)
            except Exception as e: logger.error(f"done_cb error: {e}")

    def stop_fetch(self, uid):
        self._running[uid] = False

    def is_running(self, uid):
        return bool(self._running.get(uid))

    def is_on_break(self, uid):
        return bool(self._break_flag.get(uid))

    def clear_memory(self):
        count = len(self._temp_links)
        self._temp_links = []
        return count

    @property
    def temp_count(self):
        return len(self._temp_links)
