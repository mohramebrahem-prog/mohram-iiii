# -*- coding: utf-8 -*-
import logging, asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (SessionPasswordNeededError, PhoneCodeInvalidError,
                              FloodWaitError, PhoneNumberInvalidError, PasswordHashInvalidError)
from helpers import random_device

logger = logging.getLogger(__name__)

class AuthService:
    def __init__(self, db, api_id, api_hash):
        self.db       = db
        self.api_id   = api_id
        self.api_hash = api_hash
        self._pending = {}

    def _make_client(self, session=None, proxy=None, dm=None, sv=None, av=None):
        if not dm:
            dm, sv, av = random_device()
        sess = StringSession(session) if session else StringSession()
        return TelegramClient(sess, self.api_id, self.api_hash,
                              proxy=proxy, device_model=dm,
                              system_version=sv, app_version=av or "9.3.3")

    async def start_login(self, uid, phone, number_id=None):
        dm = sv = av = None
        if number_id:
            n = self.db.get_number(number_id)
            if n:
                dm, sv, av = n.get("device_model"), n.get("system_version"), n.get("app_version")
        client = self._make_client(dm=dm, sv=sv, av=av)
        try:
            await asyncio.wait_for(client.connect(), timeout=20)
            r = await asyncio.wait_for(client.send_code_request(phone), timeout=15)
            self._pending[uid] = {"client": client, "phone": phone,
                                  "hash": r.phone_code_hash, "dm": dm, "sv": sv, "av": av}
            return True, None
        except PhoneNumberInvalidError:
            await client.disconnect()
            return False, "❌ رقم الهاتف غير صالح"
        except FloodWaitError as e:
            await client.disconnect()
            return False, f"⏳ انتظر {e.seconds} ثانية"
        except asyncio.TimeoutError:
            await client.disconnect()
            return False, "⌛ انتهت المهلة، حاول مجدداً"
        except Exception as e:
            await client.disconnect()
            return False, str(e)

    async def submit_code(self, uid, code):
        d = self._pending.get(uid)
        if not d: return False, "انتهت الجلسة، ابدأ من جديد"
        try:
            await d["client"].sign_in(phone=d["phone"], code=code, phone_code_hash=d["hash"])
            me = await d["client"].get_me()
            ss = d["client"].session.save()
            self.db.add_number(uid, d["phone"], ss,
                               device_model=d.get("dm"), system_version=d.get("sv"), app_version=d.get("av"))
            del self._pending[uid]
            return True, me
        except SessionPasswordNeededError:
            return "2fa", None
        except PhoneCodeInvalidError:
            return False, "❌ الكود غير صحيح"
        except FloodWaitError as e:
            return False, f"⏳ انتظر {e.seconds} ثانية"
        except Exception as e:
            return False, str(e)

    async def submit_password(self, uid, pwd):
        d = self._pending.get(uid)
        if not d: return False, "انتهت الجلسة"
        try:
            await d["client"].sign_in(password=pwd)
            me = await d["client"].get_me()
            ss = d["client"].session.save()
            self.db.add_number(uid, d["phone"], ss,
                               device_model=d.get("dm"), system_version=d.get("sv"), app_version=d.get("av"))
            del self._pending[uid]
            return True, me
        except PasswordHashInvalidError:
            return False, "❌ كلمة المرور خاطئة"
        except Exception as e:
            return False, str(e)

    async def cancel_login(self, uid):
        if uid in self._pending:
            try: await self._pending[uid]["client"].disconnect()
            except Exception: pass
            del self._pending[uid]
