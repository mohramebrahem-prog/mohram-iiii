#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, os, asyncio, time, warnings

# ── تأكيد أن Python يبحث في نفس المجلد ──────────────────────────
_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from telegram.warnings import PTBUserWarning
warnings.filterwarnings("ignore", category=PTBUserWarning)

from utils      import (BOT_TOKEN, API_ID, API_HASH, ADMIN_IDS,
                        DATABASE_PATH, ENCRYPTION_KEY, LOG_FILE, TEMP_DIR)
from utils      import setup_logger
from db_handler import Database
from auth       import AuthService
from publish    import PublishService
from folder     import FolderService
from fetch      import FetchService
from engineer_svc import EngineerService
from video      import VideoService
from user_handler import UserHandlers
from admin      import AdminHandlers
from engineer_hdl import EngineerHandler
from video      import VideoHandler
from control    import ControlHandler
from session    import SessionManager
from flash      import FlashTurboEngine, FlashHandler
from router     import CallbackHandlers

logger = setup_logger("Muharram", LOG_FILE)

# ── بناء الخدمات ──────────────────────────────────────────────────
db         = Database(DATABASE_PATH, ENCRYPTION_KEY)
auth_svc   = AuthService(db, API_ID, API_HASH)
pub_svc    = PublishService(db, API_ID, API_HASH)
folder_svc = FolderService(db, API_ID, API_HASH)
fetch_svc  = FetchService(db, API_ID, API_HASH)
eng_svc    = EngineerService(db, API_ID, API_HASH)
vid_svc    = VideoService(db)

# ── بناء المعالجات ────────────────────────────────────────────────
admin_hdl = AdminHandlers(db, ADMIN_IDS, pub_svc, folder_svc)
user_hdl  = UserHandlers(db, auth_svc, pub_svc, folder_svc, fetch_svc, ADMIN_IDS, admin_hdl)
eng_hdl   = EngineerHandler(db, eng_svc, ADMIN_IDS)
vid_hdl   = VideoHandler(db, vid_svc, ADMIN_IDS)
ctrl_hdl  = ControlHandler(db, ADMIN_IDS)
sm_hdl    = SessionManager(db, ADMIN_IDS)
flash_eng = FlashTurboEngine(db, API_ID, API_HASH)
flash_hdl = FlashHandler(db, flash_eng, ADMIN_IDS)

cb_hdl = CallbackHandlers(
    user_handlers  = user_hdl,
    admin_handlers = admin_hdl,
    eng_handler    = eng_hdl,
    vid_handler    = vid_hdl,
    ctrl_handler   = ctrl_hdl,
    sm_handler     = sm_hdl,
    flash_handler  = flash_hdl,
)

# ── التطبيق ───────────────────────────────────────────────────────
app = Application.builder().token(BOT_TOKEN).build()

pub_svc.bot    = app.bot
flash_eng.bot  = app.bot
folder_svc.bot = app.bot
admin_hdl.bot  = app.bot
eng_svc.bot    = app.bot

app.bot_data["eng_hdl"]   = eng_hdl
app.bot_data["vid_hdl"]   = vid_hdl
app.bot_data["flash_hdl"] = flash_hdl
app.bot_data["sm_hdl"]    = sm_hdl

app.add_handler(CommandHandler("start", user_hdl.start))
app.add_handler(CallbackQueryHandler(cb_hdl.handle))
app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, user_hdl.handle_message))

async def cleanup_task(app):
    while True:
        await asyncio.sleep(3600)
        if os.path.exists(TEMP_DIR):
            now = time.time()
            for f in os.listdir(TEMP_DIR):
                fp = os.path.join(TEMP_DIR, f)
                try:
                    if os.path.isfile(fp) and now - os.path.getmtime(fp) > 3600:
                        os.remove(fp)
                except Exception:
                    pass

async def post_init(application):
    asyncio.create_task(cleanup_task(application))
    logger.info("✅ Muharram Bot — بدأ بنجاح!")

app.post_init = post_init
logger.info("🚀 جاري تشغيل البوت...")
app.run_polling(drop_pending_updates=True, allowed_updates=["message", "callback_query"])
