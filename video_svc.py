# -*- coding: utf-8 -*-
"""خدمة الفيديوهات التعليمية"""
import logging
logger = logging.getLogger(__name__)

class VideoService:
    def __init__(self, db):
        self.db = db
        self._ensure_table()

    def _ensure_table(self):
        self.db.execute("""CREATE TABLE IF NOT EXISTS tutorial_videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            url TEXT DEFAULT '',
            file_id TEXT DEFAULT '',
            is_active INTEGER DEFAULT 1,
            added_by INTEGER,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

    def add_video(self, title, url="", file_id="", added_by=None):
        self.db.execute(
            "INSERT INTO tutorial_videos(title,url,file_id,added_by) VALUES(?,?,?,?)",
            (title, url, file_id, added_by))

    def get_videos(self):
        return self.db.fetch_all(
            "SELECT * FROM tutorial_videos WHERE is_active=1 ORDER BY added_at DESC")

    def delete_video(self, vid_id):
        self.db.execute("DELETE FROM tutorial_videos WHERE id=?", (vid_id,))

    def get_video(self, vid_id):
        return self.db.fetch_one("SELECT * FROM tutorial_videos WHERE id=?", (vid_id,))
