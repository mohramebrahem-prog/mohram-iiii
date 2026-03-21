# -*- coding: utf-8 -*-
"""
FetchService v2.0
الإصلاحات:
- إصلاح مقارنة التاريخ (aware vs naive timezone)
- iter_messages بدون offset_date لضمان جلب الرسائل الصحيحة
- دعم صحيح لـ mode=all, my_groups, messages
- نظام dup صحيح
"""
import asyncio, logging, re, time
from datetime import datetime, timedelta, timezone
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.sessions import StringSession
import utils as helpers

logger = logging.getLogger(__name__)

TG_RE = re.compile(
    r"https?://t\.me/(?:joinchat/[a-zA-Z0-9_\-]+|\+[a-zA-Z0-9_\-]+|[a-zA-Z0-9_]{5,})"
)
WA_RE = re.compile(r"https?://chat\.whatsapp\.com/[\w\d\-_]{10,}")

_FLOOD_MAX   = 300
_PROG_EVERY  = 5
_BATCH_SLEEP = 0.3


class FetchService:
    def __init__(self, db, api_id, api_hash):
        self.db       = db
        self.api_id   = api_id
        self.api_hash = api_hash
        self._running = {}
        self._temp_links = []  # ذاكرة مؤقتة للروابط في الرام

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
        if not links_list: return
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.db.execute_many(
                "INSERT OR IGNORE INTO fetched_links (url, fetched_at) VALUES (?, ?)",
                [(url, now) for url in links_list])
        except Exception as e:
            logger.warning(f"save_links_batch: {e}")

    async def fetch_links(self, uid, nid, link_type="telegram", days=1,
                          mode="messages", progress_cb=None):
        self._running[uid] = True
        empty = {"error": "", "dialogs": 0, "new": 0, "dup": 0, "messages": 0}

        n = self.db.get_number(nid)
        if not n:
            return [], [], {**empty, "error": "رقم غير موجود"}

        client = self._make_client(n)
        try:
            await asyncio.wait_for(client.connect(), timeout=20)
            if not await asyncio.wait_for(client.is_user_authorized(), timeout=5):
                return [], [], {**empty, "error": "جلسة منتهية"}
        except Exception as e:
            try: await client.disconnect()
            except Exception: pass
            return [], [], {**empty, "error": str(e)}

        existing = self._get_existing_links()
        tg_new   = set()
        wa_new   = set()
        tg_dup   = 0
        wa_dup   = 0
        stats    = {**empty, "start": time.time()}

        # حد التاريخ — aware للمقارنة الصحيحة مع تيليجرام
        cutoff_aware = datetime.now(timezone.utc) - timedelta(days=days)

        try:
            # ══ وضع مجموعاتي ════════════════════════════════════
            if mode in ("my_groups", "all"):
                try:
                    dialogs = [d async for d in client.iter_dialogs(limit=3000)
                               if d.is_group or d.is_channel]
                    stats["dialogs"] = len(dialogs)
                    for dlg in dialogs:
                        if not self._running.get(uid): break
                        uname = getattr(dlg.entity, "username", None)
                        if uname:
                            lnk = f"https://t.me/{uname}"
                            if lnk in existing or lnk in tg_new:
                                tg_dup += 1
                            else:
                                tg_new.add(lnk)
                except Exception as e:
                    logger.warning(f"my_groups scan: {e}")

            # ══ وضع الرسائل ════════════════════════════════════
            if mode in ("messages", "all"):
                try:
                    dialogs = [d async for d in client.iter_dialogs(limit=3000)
                               if d.is_group or d.is_channel]
                    if mode == "messages":
                        stats["dialogs"] = len(dialogs)
                    else:
                        stats["dialogs"] = max(stats["dialogs"], len(dialogs))

                    for i, dialog in enumerate(dialogs):
                        if not self._running.get(uid): break
                        dlg_tg = set()
                        dlg_wa = set()
                        try:
                            # iter_messages من الأحدث للأقدم
                            # نوقف يدوياً عند تجاوز الحد الزمني
                            async for msg in client.iter_messages(dialog, limit=None):
                                if not self._running.get(uid): break
                                if not msg.date: continue

                                # مقارنة التاريخ — تيليجرام يُعيد aware datetime
                                msg_date = msg.date
                                if msg_date.tzinfo is None:
                                    # naive — أضف UTC
                                    msg_date = msg_date.replace(tzinfo=timezone.utc)
                                if msg_date < cutoff_aware:
                                    break  # وصلنا لما قبل النطاق الزمني

                                text = msg.text or ""
                                if not text: continue

                                if link_type in ("telegram", "both"):
                                    for lnk in TG_RE.findall(text):
                                        if lnk in existing or lnk in tg_new:
                                            tg_dup += 1
                                        else:
                                            dlg_tg.add(lnk)

                                if link_type in ("whatsapp", "both"):
                                    for lnk in WA_RE.findall(text):
                                        if lnk in existing or lnk in wa_new:
                                            wa_dup += 1
                                        else:
                                            dlg_wa.add(lnk)

                                stats["messages"] += 1

                        except FloodWaitError as e:
                            wait = min(e.seconds + 5, _FLOOD_MAX)
                            logger.warning(f"FloodWait {wait}s in fetch")
                            await asyncio.sleep(wait)
                        except Exception as ex:
                            logger.debug(f"dialog fetch error: {ex}")

                        tg_new.update(dlg_tg)
                        wa_new.update(dlg_wa)
                        await asyncio.sleep(_BATCH_SLEEP)

                        if progress_cb and i % _PROG_EVERY == 0:
                            try:
                                await progress_cb(
                                    i + 1, len(dialogs),
                                    len(tg_new) + len(wa_new),
                                    tg_dup + wa_dup)
                            except Exception: pass

                except Exception as e:
                    logger.warning(f"messages scan: {e}")

        finally:
            self._running.pop(uid, None)
            try: await client.disconnect()
            except Exception: pass

        all_new      = list(tg_new) + list(wa_new)
        stats["new"] = len(all_new)
        stats["dup"] = tg_dup + wa_dup

        self._save_links_batch(all_new)
        # حفظ في ذاكرة الرام المؤقتة أيضاً
        self._temp_links.extend(all_new)

        if all_new:
            try:
                self.db.execute(
                    "UPDATE users SET total_fetches=total_fetches+1 WHERE user_id=?",
                    (uid,))
            except Exception: pass

        return list(tg_new), list(wa_new), stats

    def stop_fetch(self, uid):
        self._running[uid] = False

    def clear_memory(self):
        """مسح مصفوفات الروابط المخزنة مؤقتاً في الرام"""
        count = len(self._temp_links)
        self._temp_links = []
        return count
