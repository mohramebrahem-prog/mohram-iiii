# -*- coding: utf-8 -*-
"""
FolderService v2.0
الإصلاحات:
- إزالة _classify_link (كانت تُنضم مرتين!)
- الانضمام مباشرة وحفظ الـ entity من نتيجة الانضمام
- get_input_entity من الـ entity مباشرة بعد الانضمام
- معالجة FloodWait ذكية
"""
import asyncio, logging, time, json, random
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    FloodWaitError, UserAlreadyParticipantError, ChannelPrivateError,
    InviteHashExpiredError, UserBannedInChannelError, ChatAdminRequiredError,
    UserDeactivatedBanError, PeerFloodError, InviteHashInvalidError,
)
from telethon.tl.functions.messages import (
    GetDialogFiltersRequest, UpdateDialogFilterRequest,
)
from telethon.tl.functions.channels import (
    JoinChannelRequest, LeaveChannelRequest,
)
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.types import (
    DialogFilter, DialogFilterDefault, Channel, Chat,
)
import utils as helpers

logger = logging.getLogger(__name__)

_JOIN_DELAY  = 8     # ثواني بين كل انضمام (آمن)
_CHUNK_SIZE  = 100   # روابط لكل مجلد


class FolderService:
    def __init__(self, db, api_id, api_hash, bot=None):
        self.db          = db
        self.api_id      = api_id
        self.api_hash    = api_hash
        self.bot         = bot
        self._tasks      = {}
        self._progress   = {}
        self._stop_flags = {}

    def _make_client(self, n):
        proxy = helpers.parse_proxy(n.get("proxy")) if n.get("proxy") else None
        return TelegramClient(
            StringSession(n["session_string"]), self.api_id, self.api_hash,
            proxy=proxy,
            device_model=n.get("device_model", "Samsung Galaxy S22"),
            system_version=n.get("system_version", "Android 12"),
            app_version=n.get("app_version", "9.3.3"),
            connection_retries=3, retry_delay=5)

    async def _get_client(self, nid):
        n = self.db.get_number(nid)
        if not n: return None
        c = self._make_client(n)
        try:
            await asyncio.wait_for(c.connect(), timeout=20)
            if not await asyncio.wait_for(c.is_user_authorized(), timeout=5):
                await c.disconnect()
                return None
            return c
        except Exception as e:
            logger.error(f"FolderService connect #{nid}: {e}")
            try: await c.disconnect()
            except Exception: pass
            return None

    async def _notify(self, uid, msg):
        try:
            await self.bot.send_message(uid, msg, parse_mode="Markdown")
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────────
    async def get_folder_count(self, nid):
        n = self.db.get_number(nid)
        if not n: return 0
        c = self._make_client(n)
        try:
            await asyncio.wait_for(c.connect(), timeout=15)
            if not await asyncio.wait_for(c.is_user_authorized(), timeout=5):
                return 0
            result = await c(GetDialogFiltersRequest())
            real = [f for f in result.filters
                    if not isinstance(f, DialogFilterDefault)
                    and hasattr(f, "id") and f.id >= 2]
            return len(real)
        except Exception as e:
            logger.warning(f"get_folder_count #{nid}: {e}")
            return 0
        finally:
            try: await c.disconnect()
            except Exception: pass

    async def fetch_tg_folders(self, nid):
        n = self.db.get_number(nid)
        if not n: return []
        c = self._make_client(n)
        try:
            await asyncio.wait_for(c.connect(), timeout=15)
            if not await asyncio.wait_for(c.is_user_authorized(), timeout=5):
                return []
            result = await c(GetDialogFiltersRequest())
            folders = []
            for f in result.filters:
                if isinstance(f, DialogFilterDefault): continue
                if hasattr(f, "id") and f.id >= 2 and hasattr(f, "title"):
                    folders.append({
                        "filter_id": f.id,
                        "title": f.title,
                        "chat_count": len(getattr(f, "include_peers", [])),
                    })
            return folders
        except Exception as e:
            logger.warning(f"fetch_tg_folders #{nid}: {e}")
            return []
        finally:
            try: await c.disconnect()
            except Exception: pass

    # ─────────────────────────────────────────────────────────────
    # الانضمام المباشر — يُعيد (ok, entity_أو_None, reason)
    # entity = الكائن الفعلي للمجموعة/القناة للاستخدام في المجلد
    # ─────────────────────────────────────────────────────────────
    async def _join_and_get(self, client, link):
        raw = link.split("t.me/")[-1].split("?")[0].strip("/")
        is_invite = (
            "joinchat" in link or
            raw.startswith("+") or
            raw.startswith("joinchat/")
        )
        try:
            if is_invite:
                hash_part = raw.lstrip("+").replace("joinchat/", "")
                result  = await asyncio.wait_for(
                    client(ImportChatInviteRequest(hash_part)), timeout=20)
                chats   = getattr(result, "chats", [])
                entity  = chats[0] if chats else None
                return True, entity, "joined_invite"
            else:
                entity = await asyncio.wait_for(client.get_entity(raw), timeout=10)
                await asyncio.wait_for(client(JoinChannelRequest(entity)), timeout=20)
                return True, entity, "joined"

        except UserAlreadyParticipantError:
            # عضو مسبقاً — نجلب الـ entity
            try:
                entity = await asyncio.wait_for(client.get_entity(raw), timeout=10)
                return True, entity, "already"
            except Exception:
                return True, None, "already_no_entity"

        except (ChannelPrivateError, InviteHashExpiredError, InviteHashInvalidError):
            return False, None, "private_expired"
        except (UserBannedInChannelError, ChatAdminRequiredError):
            return False, None, "banned"
        except UserDeactivatedBanError:
            return False, None, "fatal"
        except PeerFloodError:
            return False, None, "peer_flood"
        except FloodWaitError as e:
            return False, None, f"flood:{e.seconds}"
        except Exception as e:
            return False, None, f"err:{type(e).__name__}"

    @staticmethod
    def _entity_type(entity):
        if isinstance(entity, Channel):
            return "group" if entity.megagroup else "channel"
        if isinstance(entity, Chat):
            return "group"
        return "unknown"

    # ─────────────────────────────────────────────────────────────
    # إنشاء مجلد تيليجرام من قائمة entities
    # ─────────────────────────────────────────────────────────────
    async def _create_tg_folder(self, client, name, entities):
        try:
            existing = await client(GetDialogFiltersRequest())
            used_ids = {f.id for f in existing.filters if hasattr(f, "id")}
            new_id   = 2
            while new_id in used_ids:
                new_id += 1

            input_peers = []
            for ent in entities:
                try:
                    ip = await asyncio.wait_for(
                        client.get_input_entity(ent), timeout=5)
                    input_peers.append(ip)
                except Exception as e:
                    logger.debug(f"get_input_entity failed: {e}")

            if not input_peers:
                logger.warning(f"create_tg_folder '{name}': no input_peers from {len(entities)} entities")
                return None

            df = DialogFilter(
                id=new_id,
                title=name,
                pinned_peers=[],
                include_peers=input_peers[:99],
                exclude_peers=[],
                contacts=False,
                non_contacts=False,
                groups=False,
                broadcasts=False,
                bots=False,
                exclude_muted=False,
                exclude_read=False,
                exclude_archived=False,
            )
            await client(UpdateDialogFilterRequest(id=new_id, filter=df))
            logger.info(f"Folder '{name}' id={new_id} peers={len(input_peers)}")
            return new_id

        except Exception as e:
            logger.error(f"create_tg_folder error: {e}", exc_info=True)
            return None

    # ─────────────────────────────────────────────────────────────
    # المحرك الرئيسي
    # ─────────────────────────────────────────────────────────────
    async def _create_folders_worker(self, uid, nid, links, filter_type,
                                     progress_msg_id, progress_chat_id):
        stats = self._progress[uid]

        # جلب إعدادات الأمان الديناميكية
        s = self.db.fetch_one(
            "SELECT join_delay_min, join_delay_max, big_break_duration, groups_per_break "
            "FROM settings WHERE user_id=?", (uid,)) or {}
        join_delay_min   = s.get("join_delay_min",   60)
        join_delay_max   = s.get("join_delay_max",   120)
        big_break_dur    = s.get("big_break_duration", 10) * 60  # تحويل للثواني
        groups_per_break = s.get("groups_per_break",  20)

        client = await self._get_client(nid)
        if not client:
            stats["status"]    = "error"
            stats["error_msg"] = "❌ فشل الاتصال بالرقم"
            await self._notify(uid, "❌ فشل الاتصال بالرقم")
            return

        self.db.set_number_busy(nid, True)

        try:
            # حد السعة
            current_folders  = await self.get_folder_count(nid)
            available_slots  = max(0, 10 - current_folders)
            if available_slots == 0:
                stats["status"]    = "done"
                stats["error_msg"] = "❌ الرقم ممتلئ (10/10 مجلدات)"
                await self._notify(uid, "❌ الرقم ممتلئ. احذف مجلداً أولاً.")
                return

            max_links = available_slots * _CHUNK_SIZE
            if len(links) > max_links:
                links = links[:max_links]
                stats["warning"] = f"⚠️ الحد: {max_links} رابط ({available_slots} مجلد)"

            stats["total"]  = len(links)
            stats["phase"]  = "joining"
            stats["status"] = "running"

            # ── حاوية المجلد الحالي ──────────────────────────────
            chunk_entities = []  # entities للمجلد الحالي
            chunk_ctypes   = []
            chunk_ids      = []  # IDs للحفظ
            chunk_num      = 0

            for i, link in enumerate(links):
                if self._stop_flags.get(uid): break

                stats["checked"] = i + 1

                # ── انضمام مباشر ──────────────────────────────────
                ok, entity, reason = await self._join_and_get(client, link)

                # FloodWait
                if reason.startswith("flood:"):
                    wait_sec = int(reason.split(":")[1])
                    capped   = min(wait_sec, 300)
                    stats["flood_wait"] = wait_sec
                    stats["current_status"] = f"⏱️ FloodWait {wait_sec}ث"
                    await self._notify(uid,
                        f"⏳ FloodWait {wait_sec}ث — سأنتظر {capped}ث...")
                    await asyncio.sleep(capped)
                    ok, entity, reason = await self._join_and_get(client, link)

                # PeerFlood
                if reason == "peer_flood":
                    stats["current_status"] = "⚠️ PeerFlood — انتظار 2 دقيقة"
                    await asyncio.sleep(120)
                    ok, entity, reason = await self._join_and_get(client, link)

                # حساب موقوف نهائياً
                if reason == "fatal":
                    stats["status"] = "fatal"
                    await self._notify(uid, "🚨 الرقم موقوف — توقف العملية")
                    return

                if ok and entity is not None:
                    ctype = self._entity_type(entity)

                    # تطبيق الفلتر
                    skip = False
                    if filter_type == "groups"   and ctype != "group":   skip = True
                    if filter_type == "channels" and ctype != "channel": skip = True

                    if not skip:
                        chunk_entities.append(entity)
                        chunk_ctypes.append(ctype)
                        chunk_ids.append(getattr(entity, "id", None))
                        stats["joined"] += 1
                        stats["valid_count"] = stats["joined"]
                    else:
                        stats["skipped_filter"] = stats.get("skipped_filter", 0) + 1
                else:
                    if not ok:
                        stats["join_failed"] = stats.get("join_failed", 0) + 1

                # ── إنشاء مجلد كل CHUNK_SIZE ────────────────────────
                if len(chunk_entities) >= _CHUNK_SIZE:
                    chunk_num += 1
                    stats["current_chunk"] = chunk_num
                    await self._flush_chunk(
                        client, nid, uid, chunk_num,
                        chunk_entities, chunk_ctypes, chunk_ids, stats)
                    chunk_entities = []
                    chunk_ctypes   = []
                    chunk_ids      = []

                # ── استراحة كبرى كل groups_per_break مجموعة ────────
                if (i + 1) % max(1, groups_per_break) == 0 and i < len(links) - 1:
                    break_mins = big_break_dur // 60
                    stats["current_status"] = f"😴 استراحة {break_mins} دقيقة..."
                    await self._notify(uid, f"😴 استراحة أمان: {break_mins} دقيقة...")
                    # تحديث رسالة التقدم قبل الاستراحة
                    await self._update_progress_msg(uid, progress_msg_id, progress_chat_id)
                    await asyncio.sleep(big_break_dur)
                    stats["current_status"] = "🔗 جارٍ الانضمام..."

                # تحديث التقدم كل 3 روابط
                if (i + 1) % 3 == 0:
                    await self._update_progress_msg(uid, progress_msg_id, progress_chat_id)

                # فاصل عشوائي ذكي
                join_delay = random.randint(join_delay_min, join_delay_max)
                stats["current_delay"] = join_delay
                await asyncio.sleep(join_delay)

            # ── مجلد المتبقيات ────────────────────────────────────
            if chunk_entities and not self._stop_flags.get(uid):
                chunk_num += 1
                stats["current_chunk"] = chunk_num
                await self._flush_chunk(
                    client, nid, uid, chunk_num,
                    chunk_entities, chunk_ctypes, chunk_ids, stats)

            stats["total_chunks"] = chunk_num
            stats["status"] = "done" if not self._stop_flags.get(uid) else "stopped"

        except asyncio.CancelledError:
            stats["status"] = "stopped"
        except Exception as e:
            logger.error(f"folder_worker uid={uid}: {e}", exc_info=True)
            stats["status"]    = "error"
            stats["error_msg"] = str(e)
        finally:
            self.db.set_number_busy(nid, False)
            self._stop_flags.pop(uid, None)
            self._tasks.pop(uid, None)
            try: await client.disconnect()
            except Exception: pass
            await self._update_progress_msg(uid, progress_msg_id, progress_chat_id)
            fc = stats.get("folders_created", 0)
            jn = stats.get("joined", 0)
            fl = stats.get("join_failed", 0)
            await self._notify(
                uid,
                f"✅ *اكتمل إنشاء المجلدات!*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📂 مجلدات مُنشأة: *{fc}*\n"
                f"✅ انضمام ناجح: *{jn}*\n"
                f"❌ فشل: *{fl}*"
            )

    async def _flush_chunk(self, client, nid, uid, chunk_num,
                           entities, ctypes, ids, stats):
        """ينشئ مجلداً من entities ويحفظه"""
        folder_name = f"مجلد {chunk_num} — محرم"
        ch_count    = ctypes.count("channel")
        gr_count    = ctypes.count("group")
        members     = sum(getattr(e, "participants_count", 0) or 0 for e in entities)
        ids_json    = json.dumps([str(x) for x in ids if x])

        filter_id = await self._create_tg_folder(client, folder_name, entities)
        if filter_id:
            self.db.save_folder(
                nid, uid, filter_id, folder_name, "",
                ch_count, gr_count, members, ids_json)
            stats["folders_created"] = stats.get("folders_created", 0) + 1
            stats.setdefault("log", []).append(
                f"✅ {folder_name}: {ch_count}📢+{gr_count}👥")
            logger.info(f"Saved folder '{folder_name}' filter_id={filter_id}")
        else:
            logger.warning(f"Failed to create folder chunk {chunk_num}")
            stats.setdefault("log", []).append(f"❌ فشل إنشاء {folder_name}")

    async def _update_progress_msg(self, uid, msg_id, chat_id):
        if not msg_id or not self.bot: return
        stats = self._progress.get(uid, {})
        # تقليل وتيرة التحديث لتجنب Rate Limit — لا نُحدّث إن مرّ أقل من 4 ثواني
        now = time.time()
        last_edit = stats.get("_last_edit_ts", 0)
        if now - last_edit < 4 and stats.get("status") == "running":
            return
        stats["_last_edit_ts"] = now
        try:
            phase_map = {
                "joining": "🔗 انضمام وإنشاء مجلدات",
                "done":    "✅ اكتمل",
                "stopped": "⏹️ أُوقف",
                "error":   "❌ خطأ",
                "fatal":   "🚨 حساب موقوف",
            }
            phase_txt = phase_map.get(stats.get("phase", ""), "جارٍ...")
            total    = stats.get("total",   0)
            checked  = stats.get("checked", 0)
            joined   = stats.get("joined",  0)
            folders  = stats.get("folders_created", 0)
            failed   = stats.get("join_failed", 0)
            flood    = stats.get("flood_wait", 0)
            cur_stat = stats.get("current_status", "🔗 جارٍ الانضمام...")
            bar      = helpers.progress_bar(checked, total) if total else "▱" * 12
            pct_txt  = helpers.pct(checked, total)

            # حساب ETA مع احتساب الاستراحات
            start_ts = stats.get("start_ts", now)
            eta_txt  = helpers.calc_eta(checked, total, start_ts)
            remaining = total - checked
            # تقدير وقت الاستراحات القادمة (نقريبي)
            s_db = self.db.fetch_one(
                "SELECT join_delay_min, join_delay_max, big_break_duration, groups_per_break "
                "FROM settings WHERE user_id=?", (uid,)) or {}
            jd_min   = s_db.get("join_delay_min", 60)
            jd_max   = s_db.get("join_delay_max", 120)
            gbk_dur  = s_db.get("big_break_duration", 10) * 60
            gpb      = max(1, s_db.get("groups_per_break", 20))
            avg_delay = (jd_min + jd_max) / 2
            breaks_ahead = remaining // gpb
            eta_extra_secs = remaining * avg_delay + breaks_ahead * gbk_dur
            if eta_extra_secs >= 3600:
                eta_full = f"{int(eta_extra_secs//3600)}س {int((eta_extra_secs%3600)//60)}د"
            elif eta_extra_secs >= 60:
                eta_full = f"{int(eta_extra_secs//60)}د"
            else:
                eta_full = f"{int(eta_extra_secs)}ث"

            text = (
                f"⏳ *جاري العمل في الخلفية...*\n"
                f"_(يمكنك استخدام البوت بحرية)_\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🔄 المرحلة: *{phase_txt}*\n"
                f"📌 الحالة: *{cur_stat}*\n"
                f"{bar} {pct_txt}\n"
                f"🔢 {checked}/{total} | ⏰ ETA: ~{eta_full}\n\n"
                f"🔗 انضمام: *{joined}* | ❌ فشل: *{failed}*\n"
                f"📂 مجلدات جاهزة: *{folders}*"
                + (f"\n⚠️ {stats['warning']}" if stats.get("warning") else "")
                + (f"\n⏱️ FloodWait: {flood}ث" if flood > 0 else "")
            )
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            kb = None
            if stats.get("status") == "running":
                kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton("⏹️ إيقاف", callback_data="folder_stop_task")]])
            await self.bot.edit_message_text(
                text, chat_id=chat_id, message_id=msg_id,
                parse_mode="Markdown", reply_markup=kb)
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────────
    async def start_create_folders(self, uid, nid, links, filter_type,
                                   progress_msg_id, progress_chat_id):
        if uid in self._tasks and not self._tasks[uid].done():
            return False, "⚠️ هناك عملية جارية. أوقفها أولاً."

        current = await self.get_folder_count(nid)
        if current >= 10:
            return False, "❌ الرقم وصل للحد الأقصى (10/10). احذف مجلداً أولاً."

        self._progress[uid] = {
            "total": len(links), "checked": 0, "valid_count": 0,
            "skipped_filter": 0, "joined": 0, "join_failed": 0,
            "folders_created": 0, "current_chunk": 0, "total_chunks": 0,
            "flood_wait": 0, "phase": "joining", "status": "running",
            "warning": "", "error_msg": "", "log": [],
            "start_ts": time.time(),
            "current_status": "🔗 جارٍ الانضمام...",
            "current_delay": 0,
        }
        self._stop_flags[uid] = False
        task = asyncio.create_task(
            self._create_folders_worker(uid, nid, links, filter_type,
                                        progress_msg_id, progress_chat_id))
        self._tasks[uid] = task
        return True, "🚀 بدأت العملية في الخلفية!"

    def stop_task(self, uid):
        self._stop_flags[uid] = True
        t = self._tasks.get(uid)
        if t and not t.done():
            t.cancel()
            return True
        return False

    def get_progress(self, uid):
        return self._progress.get(uid)

    # ─────────────────────────────────────────────────────────────
    async def delete_folder_only(self, uid, nid, folder_db_id):
        folder = self.db.get_folder(folder_db_id, uid)
        if not folder: return False, "❌ المجلد غير موجود"
        filter_id = folder.get("filter_id")
        if filter_id:
            client = await self._get_client(nid)
            if client:
                try:
                    await client(UpdateDialogFilterRequest(id=filter_id))
                except Exception as e:
                    logger.warning(f"delete filter {filter_id}: {e}")
                finally:
                    try: await client.disconnect()
                    except Exception: pass
        self.db.delete_folder(folder_db_id, uid)
        return True, "✅ تم حذف المجلد بنجاح"

    async def delete_folder_and_leave(self, uid, nid, folder_db_id, progress_chat_id):
        folder = self.db.get_folder(folder_db_id, uid)
        if not folder: return False, "❌ المجلد غير موجود"
        client = await self._get_client(nid)
        if not client: return False, "❌ فشل الاتصال بالرقم"
        try:
            filter_id = folder.get("filter_id")
            if filter_id:
                try:
                    await client(UpdateDialogFilterRequest(id=filter_id))
                except Exception: pass
            try:
                chat_ids = json.loads(folder.get("chat_ids", "[]"))
            except Exception:
                chat_ids = []
            pm = await self.bot.send_message(
                progress_chat_id,
                f"🧹 جاري مغادرة {len(chat_ids)} محادثة...",
                parse_mode="Markdown")
            left = 0; failed = 0
            for i, cid_str in enumerate(chat_ids):
                try:
                    ent = await client.get_entity(int(cid_str))
                    await client(LeaveChannelRequest(ent))
                    left += 1
                except Exception:
                    failed += 1
                await asyncio.sleep(2)
                if (i + 1) % 10 == 0:
                    try:
                        await pm.edit_text(
                            f"🧹 {i+1}/{len(chat_ids)} | ✅{left} | ❌{failed}")
                    except Exception: pass
            self.db.delete_folder(folder_db_id, uid)
            try:
                await pm.edit_text(f"✅ غادر: {left} | ❌ فشل: {failed}")
            except Exception: pass
            return True, f"✅ تم حذف المجلد ومغادرة {left} محادثة"
        except Exception as e:
            return False, f"❌ خطأ: {e}"
        finally:
            try: await client.disconnect()
            except Exception: pass

    async def clean_dead_groups(self, uid, nid, progress_chat_id):
        client = await self._get_client(nid)
        if not client:
            await self._notify(uid, "❌ فشل الاتصال")
            return
        try:
            msg = await self.bot.send_message(
                progress_chat_id,
                "🧹 *منظف الحساب الذكي*\n━━━━━━━━━━━━━━━━━━━━\n🔍 جاري جلب المحادثات...",
                parse_mode="Markdown")
            dialogs = []
            async for d in client.iter_dialogs(limit=2000):
                if d.is_group or d.is_channel:
                    dialogs.append(d)
            left = 0; checked = 0
            for dialog in dialogs:
                checked += 1
                ent    = dialog.entity
                banned = getattr(ent, "banned_rights", None)
                leave  = False
                if banned and getattr(banned, "view_messages", False): leave = True
                if getattr(ent, "deactivated", False): leave = True
                if getattr(ent, "restricted",   False): leave = True
                if leave:
                    try:
                        await client(LeaveChannelRequest(ent))
                        left += 1
                        await asyncio.sleep(2)
                    except Exception: pass
                if checked % 30 == 0:
                    try:
                        await msg.edit_text(
                            f"🧹 فُحص: {checked}/{len(dialogs)} | 🚪 غادر: {left}")
                    except Exception: pass
                await asyncio.sleep(0.3)
            try:
                await msg.edit_text(
                    f"✅ *اكتمل التنظيف!*\n🔍 فُحص: {checked}\n🚪 غادر: {left}",
                    parse_mode="Markdown")
            except Exception: pass
        except Exception as e:
            await self._notify(uid, f"❌ خطأ: {e}")
        finally:
            try: await client.disconnect()
            except Exception: pass
