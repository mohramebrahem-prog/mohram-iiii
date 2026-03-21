# -*- coding: utf-8 -*-
import sqlite3, logging, threading
from datetime import datetime, timedelta
from utils import AESCipher

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path, key):
        self.db_path = db_path
        self.cipher  = AESCipher(key)
        self._lock   = threading.Lock()
        self._init_db()
        self._migrate()

    def _conn(self):
        c = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        c.execute("PRAGMA cache_size=5000")
        return c

    def _init_db(self):
        with self._lock:
            c = self._conn()
            try:
                c.executescript("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
    subscription_end DATE, referral_code TEXT UNIQUE, referred_by INTEGER,
    bonus_days INTEGER DEFAULT 0, total_posts INTEGER DEFAULT 0,
    total_joins INTEGER DEFAULT 0, total_fetches INTEGER DEFAULT 0,
    status TEXT DEFAULT 'active', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS numbers (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, phone TEXT,
    session_string TEXT, proxy TEXT DEFAULT '', is_active INTEGER DEFAULT 1,
    is_busy INTEGER DEFAULT 0, health INTEGER DEFAULT 100,
    device_model TEXT DEFAULT 'Samsung Galaxy S22',
    system_version TEXT DEFAULT 'Android 12', app_version TEXT DEFAULT '9.3.3',
    last_flood TIMESTAMP, added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(user_id)
);
CREATE TABLE IF NOT EXISTS ads (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
    content TEXT, title TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(user_id)
);
CREATE TABLE IF NOT EXISTS groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT, number_id INTEGER,
    group_id TEXT, group_title TEXT, member_count INTEGER DEFAULT 0,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(number_id, group_id), FOREIGN KEY(number_id) REFERENCES numbers(id)
);
CREATE TABLE IF NOT EXISTS folders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    filter_id INTEGER,
    folder_name TEXT,
    invite_link TEXT DEFAULT '',
    channels_count INTEGER DEFAULT 0,
    groups_count INTEGER DEFAULT 0,
    total_members INTEGER DEFAULT 0,
    chat_ids TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(number_id) REFERENCES numbers(id)
);
CREATE TABLE IF NOT EXISTS settings (
    user_id INTEGER PRIMARY KEY, min_delay INTEGER DEFAULT 30,
    max_delay INTEGER DEFAULT 60, deduplicate INTEGER DEFAULT 1,
    join_interval INTEGER DEFAULT 30, join_groups_per_cycle INTEGER DEFAULT 5,
    join_cycles INTEGER DEFAULT 3, join_cycle_break INTEGER DEFAULT 10,
    auto_reply_enabled INTEGER DEFAULT 0,
    join_delay_min INTEGER DEFAULT 60, join_delay_max INTEGER DEFAULT 120,
    big_break_duration INTEGER DEFAULT 10, groups_per_break INTEGER DEFAULT 20
);
CREATE TABLE IF NOT EXISTS subscription_codes (
    code TEXT PRIMARY KEY, days REAL, owner_name TEXT,
    permissions TEXT DEFAULT 'all', created_by INTEGER,
    used_by INTEGER, used_at TIMESTAMP, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS activity_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
    action TEXT, details TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS violations (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, number_id INTEGER,
    reason TEXT, count INTEGER DEFAULT 1, last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS proxies (
    id INTEGER PRIMARY KEY AUTOINCREMENT, proxy_string TEXT UNIQUE,
    is_active INTEGER DEFAULT 1, fail_count INTEGER DEFAULT 0, last_used TIMESTAMP
);
CREATE TABLE IF NOT EXISTS auto_replies (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
    keyword TEXT, response TEXT, is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS bot_texts (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS assistants (
    user_id INTEGER PRIMARY KEY, added_by INTEGER,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS fetch_history (
    number_id INTEGER, dialog_id INTEGER, last_message_id INTEGER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(number_id, dialog_id)
);
CREATE TABLE IF NOT EXISTS code_stats (
    id INTEGER PRIMARY KEY, total_generated INTEGER DEFAULT 0,
    total_used INTEGER DEFAULT 0, last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
INSERT OR IGNORE INTO code_stats(id,total_generated,total_used) VALUES(1,0,0);
CREATE TABLE IF NOT EXISTS fetched_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
-- ═══ جداول نظام المهندس الذكي ═══
CREATE TABLE IF NOT EXISTS monitored_bots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_username TEXT UNIQUE,
    estimated_groups INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS captured_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_name TEXT,
    content TEXT,
    target_bot TEXT DEFAULT '',
    source_group TEXT DEFAULT '',
    status TEXT DEFAULT 'pending',
    content_hash TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS engineer_settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
INSERT OR IGNORE INTO engineer_settings(key,value) VALUES('snipe_timeout','15');
""")
                c.commit()
            finally:
                c.close()

    def _migrate(self):
        cols = {
            "numbers":  [
                ("app_version",     "TEXT DEFAULT '9.3.3'"),
                ("is_busy",         "INTEGER DEFAULT 0"),
                ("device_model",    "TEXT DEFAULT 'Samsung Galaxy S22'"),
                ("system_version",  "TEXT DEFAULT 'Android 12'"),
                ("last_flood",      "TIMESTAMP"),
                ("proxy",           "TEXT DEFAULT ''"),
            ],
            "settings": [
                ("min_delay",              "INTEGER DEFAULT 30"),
                ("max_delay",              "INTEGER DEFAULT 60"),
                ("deduplicate",            "INTEGER DEFAULT 1"),
                ("join_interval",          "INTEGER DEFAULT 30"),
                ("join_groups_per_cycle",  "INTEGER DEFAULT 5"),
                ("join_cycles",            "INTEGER DEFAULT 3"),
                ("join_cycle_break",       "INTEGER DEFAULT 10"),
                ("auto_reply_enabled",     "INTEGER DEFAULT 0"),
                ("join_delay_min",         "INTEGER DEFAULT 60"),
                ("join_delay_max",         "INTEGER DEFAULT 120"),
                ("big_break_duration",     "INTEGER DEFAULT 10"),
                ("groups_per_break",       "INTEGER DEFAULT 20"),
            ],
            "ads": [("title", "TEXT DEFAULT ''")],
            "users": [
                ("bonus_days",     "INTEGER DEFAULT 0"),
                ("total_posts",    "INTEGER DEFAULT 0"),
                ("total_joins",    "INTEGER DEFAULT 0"),
                ("total_fetches",  "INTEGER DEFAULT 0"),
                ("status",         "TEXT DEFAULT 'active'"),
                ("referral_code",  "TEXT"),
                ("referred_by",    "INTEGER"),
            ],
            "subscription_codes": [
                ("permissions",  "TEXT DEFAULT 'all'"),
                ("created_by",   "INTEGER"),
                ("owner_name",   "TEXT DEFAULT ''"),
            ],
        }
        new_tables = {
            "fetch_history": """CREATE TABLE IF NOT EXISTS fetch_history (
                number_id INTEGER, dialog_id INTEGER, last_message_id INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(number_id, dialog_id))""",
            "assistants": """CREATE TABLE IF NOT EXISTS assistants (
                user_id INTEGER PRIMARY KEY, added_by INTEGER,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
            "auto_replies": """CREATE TABLE IF NOT EXISTS auto_replies (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
                keyword TEXT, response TEXT, is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
            "violations": """CREATE TABLE IF NOT EXISTS violations (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, number_id INTEGER,
                reason TEXT, count INTEGER DEFAULT 1, last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
            "proxies": """CREATE TABLE IF NOT EXISTS proxies (
                id INTEGER PRIMARY KEY AUTOINCREMENT, proxy_string TEXT UNIQUE,
                is_active INTEGER DEFAULT 1, fail_count INTEGER DEFAULT 0, last_used TIMESTAMP)""",
            "bot_texts": "CREATE TABLE IF NOT EXISTS bot_texts (key TEXT PRIMARY KEY, value TEXT)",
            "code_stats": """CREATE TABLE IF NOT EXISTS code_stats (
                id INTEGER PRIMARY KEY, total_generated INTEGER DEFAULT 0,
                total_used INTEGER DEFAULT 0, last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
            "groups": """CREATE TABLE IF NOT EXISTS groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT, number_id INTEGER,
                group_id TEXT, group_title TEXT, member_count INTEGER DEFAULT 0,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(number_id, group_id))""",
            "folders": """CREATE TABLE IF NOT EXISTS folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                number_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                filter_id INTEGER,
                folder_name TEXT,
                invite_link TEXT DEFAULT '',
                channels_count INTEGER DEFAULT 0,
                groups_count INTEGER DEFAULT 0,
                total_members INTEGER DEFAULT 0,
                chat_ids TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
            "monitored_bots": """CREATE TABLE IF NOT EXISTS monitored_bots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_username TEXT UNIQUE,
                estimated_groups INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
            "captured_templates": """CREATE TABLE IF NOT EXISTS captured_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template_name TEXT,
                content TEXT,
                target_bot TEXT DEFAULT '',
                source_group TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                content_hash TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
            "engineer_settings": """CREATE TABLE IF NOT EXISTS engineer_settings (
                key TEXT PRIMARY KEY,
                value TEXT)""",
        }
        for tbl, sql in new_tables.items():
            try:
                with self._lock:
                    c = self._conn()
                    try:
                        c.execute(sql)
                        c.commit()
                    finally:
                        c.close()
            except Exception:
                pass
        try:
            self.execute("INSERT OR IGNORE INTO code_stats(id,total_generated,total_used) VALUES(1,0,0)")
        except Exception:
            pass
        for tbl, column_list in cols.items():
            for col, defn in column_list:
                try:
                    with self._lock:
                        c = self._conn()
                        try:
                            c.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {defn}")
                            c.commit()
                        finally:
                            c.close()
                except Exception:
                    pass

    def execute(self, q, p=()):
        with self._lock:
            c = self._conn()
            try:
                result = c.execute(q, p)
                c.commit()
                return result
            finally:
                c.close()

    def execute_many(self, sql, params_list):
        with self._lock:
            c = self._conn()
            try:
                c.executemany(sql, params_list)
                c.commit()
            finally:
                c.close()

    def fetch_one(self, q, p=()):
        with self._lock:
            c = self._conn()
            try:
                r = c.execute(q, p).fetchone()
                return dict(r) if r else None
            finally:
                c.close()

    def fetch_all(self, q, p=()):
        with self._lock:
            c = self._conn()
            try:
                return [dict(r) for r in c.execute(q, p).fetchall()]
            finally:
                c.close()

    def get_or_create_user(self, uid, username, first_name):
        import random
        u = self.fetch_one("SELECT * FROM users WHERE user_id=?", (uid,))
        if not u:
            ref = f"ref{uid}{random.randint(100,999)}"
            self.execute("INSERT OR IGNORE INTO users(user_id,username,first_name,referral_code) VALUES(?,?,?,?)",
                         (uid, username, first_name, ref))
            self.execute("INSERT OR IGNORE INTO settings(user_id) VALUES(?)", (uid,))
            u = self.fetch_one("SELECT * FROM users WHERE user_id=?", (uid,))
        return u

    def is_subscribed(self, uid, admin_ids):
        if uid in admin_ids: return True
        u = self.fetch_one("SELECT subscription_end FROM users WHERE user_id=?", (uid,))
        if u and u["subscription_end"]:
            try:
                return datetime.strptime(u["subscription_end"], "%Y-%m-%d").date() >= datetime.now().date()
            except Exception:
                return False
        return False

    def get_user_stats(self, uid):
        u = self.fetch_one("SELECT * FROM users WHERE user_id=?", (uid,))
        if not u: return None
        u["numbers_count"] = (self.fetch_one("SELECT COUNT(*) as c FROM numbers WHERE user_id=?", (uid,)) or {}).get("c", 0)
        u["ads_count"]     = (self.fetch_one("SELECT COUNT(*) as c FROM ads WHERE user_id=?", (uid,)) or {}).get("c", 0)
        u["violations"]    = (self.fetch_one("SELECT SUM(count) as c FROM violations WHERE user_id=?", (uid,)) or {}).get("c") or 0
        return u

    def add_number(self, uid, phone, session_str, proxy="", device_model=None, system_version=None, app_version=None):
        from utils import random_device
        enc = self.cipher.encrypt(session_str)
        if not device_model or not system_version:
            device_model, system_version, app_version = random_device()
        self.execute(
            "INSERT INTO numbers(user_id,phone,session_string,proxy,device_model,system_version,app_version) VALUES(?,?,?,?,?,?,?)",
            (uid, phone, enc, proxy, device_model, system_version, app_version or "9.3.3"))

    def get_number(self, nid):
        r = self.fetch_one("SELECT * FROM numbers WHERE id=?", (nid,))
        if r: r["session_string"] = self.cipher.decrypt(r["session_string"])
        return r

    def get_user_numbers(self, uid):
        rows = self.fetch_all("SELECT * FROM numbers WHERE user_id=?", (uid,))
        for r in rows: r["session_string"] = self.cipher.decrypt(r["session_string"])
        return rows

    def set_number_busy(self, nid, busy):
        self.execute("UPDATE numbers SET is_busy=? WHERE id=?", (1 if busy else 0, nid))

    def decrease_health(self, nid, amount=1, reason=None):
        n = self.fetch_one("SELECT health FROM numbers WHERE id=?", (nid,))
        if not n: return 0
        nh = max(0, n["health"] - amount)
        self.execute("UPDATE numbers SET health=? WHERE id=?", (nh, nid))
        if nh == 0:
            self.execute("UPDATE numbers SET is_active=0 WHERE id=?", (nid,))
        return nh

    def add_violation(self, uid, nid, reason):
        v = self.fetch_one("SELECT id FROM violations WHERE user_id=? AND number_id=? AND reason=?", (uid, nid, reason))
        if v:
            self.execute("UPDATE violations SET count=count+1, last_seen=CURRENT_TIMESTAMP WHERE id=?", (v["id"],))
        else:
            self.execute("INSERT INTO violations(user_id,number_id,reason) VALUES(?,?,?)", (uid, nid, reason))

    # ── أكواد ─────────────────────────────────────────────────────
    def add_code(self, code, days, owner, permissions="all", created_by=None):
        self.execute("INSERT INTO subscription_codes(code,days,owner_name,permissions,created_by) VALUES(?,?,?,?,?)",
                     (code, days, owner, permissions, created_by))
        self.execute("UPDATE code_stats SET total_generated=total_generated+1,last_updated=CURRENT_TIMESTAMP WHERE id=1")

    def use_code(self, code, uid):
        r = self.fetch_one("SELECT * FROM subscription_codes WHERE code=? AND used_by IS NULL", (code,))
        if not r: return None
        days = r["days"]
        self.execute("UPDATE subscription_codes SET used_by=?,used_at=CURRENT_TIMESTAMP WHERE code=?", (uid, code))
        u    = self.fetch_one("SELECT subscription_end FROM users WHERE user_id=?", (uid,))
        try:
            base = datetime.strptime(u["subscription_end"], "%Y-%m-%d") if (u and u["subscription_end"]) else datetime.now()
        except Exception:
            base = datetime.now()
        new_end = base + timedelta(days=days)
        self.execute("UPDATE users SET subscription_end=? WHERE user_id=?", (new_end.strftime("%Y-%m-%d"), uid))
        self.execute("UPDATE code_stats SET total_used=total_used+1,last_updated=CURRENT_TIMESTAMP WHERE id=1")
        return days

    def delete_code(self, code):
        self.execute("DELETE FROM subscription_codes WHERE code=?", (code,))

    def get_code_stats(self):
        return self.fetch_one("SELECT * FROM code_stats WHERE id=1") or {}

    def add_auto_reply(self, uid, kw, resp):
        self.execute("INSERT INTO auto_replies(user_id,keyword,response) VALUES(?,?,?)", (uid, kw, resp))

    def get_auto_replies(self, uid):
        return self.fetch_all("SELECT * FROM auto_replies WHERE user_id=? AND is_active=1", (uid,))

    def delete_auto_reply(self, rid, uid):
        self.execute("DELETE FROM auto_replies WHERE id=? AND user_id=?", (rid, uid))

    def find_auto_reply(self, uid, text):
        rows = self.fetch_all("SELECT keyword,response FROM auto_replies WHERE user_id=? AND is_active=1", (uid,))
        for r in rows:
            if r["keyword"].lower() in text.lower():
                return r["response"]
        return None

    def add_proxy(self, s):
        try:
            self.execute("INSERT INTO proxies(proxy_string) VALUES(?)", (s,))
            return True
        except Exception:
            return False

    def get_active_proxies(self):
        return self.fetch_all("SELECT * FROM proxies WHERE is_active=1")

    def toggle_proxy(self, pid):
        self.execute("UPDATE proxies SET is_active=CASE WHEN is_active=1 THEN 0 ELSE 1 END WHERE id=?", (pid,))

    def get_text(self, key, default=""):
        r = self.fetch_one("SELECT value FROM bot_texts WHERE key=?", (key,))
        return r["value"] if r else default

    def set_text(self, key, value):
        self.execute("INSERT OR REPLACE INTO bot_texts(key,value) VALUES(?,?)", (key, value))

    def get_last_msg_id(self, nid, did):
        r = self.fetch_one("SELECT last_message_id FROM fetch_history WHERE number_id=? AND dialog_id=?", (nid, did))
        return r["last_message_id"] if r else 0

    def set_last_msg_id(self, nid, did, mid):
        self.execute("INSERT OR REPLACE INTO fetch_history(number_id,dialog_id,last_message_id,updated_at) VALUES(?,?,?,CURRENT_TIMESTAMP)",
                     (nid, did, mid))

    def add_assistant(self, uid, admin_id):
        self.execute("INSERT OR IGNORE INTO assistants(user_id,added_by) VALUES(?,?)", (uid, admin_id))

    def is_assistant(self, uid):
        return bool(self.fetch_one("SELECT user_id FROM assistants WHERE user_id=?", (uid,)))

    def get_assistants(self):
        return self.fetch_all("SELECT a.user_id,u.first_name,u.username,a.added_at FROM assistants a LEFT JOIN users u ON a.user_id=u.user_id")

    # ── مجلدات ────────────────────────────────────────────────────
    def save_folder(self, number_id, user_id, filter_id, folder_name, invite_link, channels_count, groups_count, total_members, chat_ids_str):
        self.execute(
            "INSERT INTO folders(number_id,user_id,filter_id,folder_name,invite_link,channels_count,groups_count,total_members,chat_ids) VALUES(?,?,?,?,?,?,?,?,?)",
            (number_id, user_id, filter_id, folder_name, invite_link, channels_count, groups_count, total_members, chat_ids_str))

    def get_number_folders(self, number_id, user_id):
        return self.fetch_all("SELECT * FROM folders WHERE number_id=? AND user_id=? ORDER BY created_at DESC", (number_id, user_id))

    def get_folder(self, folder_id, user_id):
        return self.fetch_one("SELECT * FROM folders WHERE id=? AND user_id=?", (folder_id, user_id))

    def delete_folder(self, folder_id, user_id):
        self.execute("DELETE FROM folders WHERE id=? AND user_id=?", (folder_id, user_id))
