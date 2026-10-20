"""Queue lokal pakai SQLite (satu file, tanpa server DB)."""
from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS queue (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id             INTEGER NOT NULL,
    track_uri           TEXT    NOT NULL,
    title               TEXT    NOT NULL,
    artist              TEXT    NOT NULL,
    duration_ms         INTEGER NOT NULL DEFAULT 0,
    requested_by        TEXT    NOT NULL,
    added_at            REAL    NOT NULL,
    source_type         TEXT    NOT NULL DEFAULT 'youtube',
    source_url          TEXT    NOT NULL DEFAULT '',
    local_path          TEXT    NOT NULL DEFAULT '',
    shoutout_to         TEXT    NOT NULL DEFAULT '',
    shoutout_message    TEXT    NOT NULL DEFAULT '',
    shoutout_audio_path TEXT    NOT NULL DEFAULT '',
    status              TEXT    NOT NULL DEFAULT 'pending'
);
CREATE INDEX IF NOT EXISTS idx_queue_chat ON queue(chat_id, id);
CREATE INDEX IF NOT EXISTS idx_queue_status ON queue(status, id);

CREATE TABLE IF NOT EXISTS app_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


@dataclass
class QueueItem:
    id: int
    chat_id: int
    track_uri: str
    title: str
    artist: str
    duration_ms: int
    requested_by: str
    added_at: float
    source_type: str = "youtube"
    source_url: str = ""
    local_path: str = ""
    shoutout_to: str = ""
    shoutout_message: str = ""
    shoutout_audio_path: str = ""
    status: str = "pending"  # pending | playing | played | error


class QueueValidationError(Exception):
    """Kesalahan validasi moderasi, cooldown, atau kuota antrian."""
    pass


class QueueStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._migrate_schema()

    def _migrate_schema(self) -> None:
        """Jalankan pembuatan tabel awal dan migrasi kolom bila tabel sudah ada."""
        with self._lock:
            self._conn.executescript(SCHEMA)
            # Cek kolom yang mungkin belum ada dari versi lama
            cur = self._conn.execute("PRAGMA table_info(queue)")
            existing_cols = {row["name"] for row in cur.fetchall()}

            new_columns = {
                "source_type": "TEXT NOT NULL DEFAULT 'youtube'",
                "source_url": "TEXT NOT NULL DEFAULT ''",
                "local_path": "TEXT NOT NULL DEFAULT ''",
                "shoutout_to": "TEXT NOT NULL DEFAULT ''",
                "shoutout_message": "TEXT NOT NULL DEFAULT ''",
                "shoutout_audio_path": "TEXT NOT NULL DEFAULT ''",
                "status": "TEXT NOT NULL DEFAULT 'pending'",
            }

            for col, col_def in new_columns.items():
                if col not in existing_cols:
                    self._conn.execute(f"ALTER TABLE queue ADD COLUMN {col} {col_def}")
            # Auto-recover antrian saat startup: kembalikan item yang menggantung saat crash/restart ke pending
            self._conn.execute("UPDATE queue SET status='pending' WHERE status='playing'")
            self._conn.commit()

    def check_moderation_and_quota(
        self,
        requested_by: str,
        text_to_check: str,
        banned_words: tuple[str, ...],
        max_user_quota: int = 3,
        max_total_quota: int = 20,
        cooldown_sec: int = 30,
    ) -> None:
        """Validasi filter kata terlarang, cooldown user, dan kapasitas antrian."""
        # 1. Banned words check
        lower_text = text_to_check.lower()
        for word in banned_words:
            if word and word.lower() in lower_text:
                raise QueueValidationError(f"Permintaan mengandung kata yang dilarang: '{word}'")

        now = time.time()
        with self._lock:
            # 2. Total active queue check
            total_active = self._conn.execute(
                "SELECT COUNT(*) AS c FROM queue WHERE status IN ('pending', 'playing')"
            ).fetchone()["c"]
            if total_active >= max_total_quota:
                raise QueueValidationError(
                    f"Antrian siaran sedang penuh ({total_active}/{max_total_quota}). Coba lagi nanti."
                )

            # 3. User quota check
            user_active = self._conn.execute(
                "SELECT COUNT(*) AS c FROM queue WHERE requested_by=? AND status IN ('pending', 'playing')",
                (requested_by,),
            ).fetchone()["c"]
            if user_active >= max_user_quota:
                raise QueueValidationError(
                    f"Anda sudah mencapai batas kuota aktif ({user_active}/{max_user_quota} lagu)."
                )

            # 4. User cooldown check
            last_req = self._conn.execute(
                "SELECT added_at FROM queue WHERE requested_by=? ORDER BY id DESC LIMIT 1",
                (requested_by,),
            ).fetchone()
            if last_req:
                elapsed = now - float(last_req["added_at"])
                if elapsed < cooldown_sec:
                    wait_sec = int(cooldown_sec - elapsed)
                    raise QueueValidationError(
                        f"Harap tunggu {wait_sec} detik sebelum mengirim request berikutnya."
                    )

    def add(
        self,
        chat_id: int,
        track_uri: str,
        title: str,
        artist: str,
        duration_ms: int,
        requested_by: str,
        source_type: str = "youtube",
        source_url: str = "",
        local_path: str = "",
        shoutout_to: str = "",
        shoutout_message: str = "",
        shoutout_audio_path: str = "",
        status: str = "pending",
    ) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO queue ("
                "  chat_id, track_uri, title, artist, duration_ms, requested_by, added_at, "
                "  source_type, source_url, local_path, shoutout_to, shoutout_message, shoutout_audio_path, status"
                ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    chat_id,
                    track_uri,
                    title,
                    artist,
                    duration_ms,
                    requested_by,
                    time.time(),
                    source_type,
                    source_url,
                    local_path,
                    shoutout_to,
                    shoutout_message,
                    shoutout_audio_path,
                    status,
                ),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def _row_to_item(self, r: sqlite3.Row) -> QueueItem:
        return QueueItem(
            id=r["id"],
            chat_id=r["chat_id"],
            track_uri=r["track_uri"],
            title=r["title"],
            artist=r["artist"],
            duration_ms=r["duration_ms"],
            requested_by=r["requested_by"],
            added_at=r["added_at"],
            source_type=r["source_type"] if "source_type" in r.keys() else "youtube",
            source_url=r["source_url"] if "source_url" in r.keys() else "",
            local_path=r["local_path"] if "local_path" in r.keys() else "",
            shoutout_to=r["shoutout_to"] if "shoutout_to" in r.keys() else "",
            shoutout_message=r["shoutout_message"] if "shoutout_message" in r.keys() else "",
            shoutout_audio_path=r["shoutout_audio_path"] if "shoutout_audio_path" in r.keys() else "",
            status=r["status"] if "status" in r.keys() else "pending",
        )

    def list(self, chat_id: Optional[int] = None, status: Optional[str] = None) -> list[QueueItem]:
        query = "SELECT * FROM queue WHERE 1=1"
        params: list[object] = []
        if chat_id is not None:
            query += " AND chat_id=?"
            params.append(chat_id)
        if status is not None:
            query += " AND status=?"
            params.append(status)
        query += " ORDER BY added_at ASC, id ASC"

        with self._lock:
            rows = self._conn.execute(query, tuple(params)).fetchall()
        return [self._row_to_item(r) for r in rows]

    def bump_to_front(self, item_id: int) -> bool:
        """Dahulukan lagu pending ke urutan teratas antrian berikutnya."""
        with self._lock:
            # Cari waktu minimum dari item pending
            row = self._conn.execute(
                "SELECT MIN(added_at) AS min_time FROM queue WHERE status='pending'"
            ).fetchone()
            if not row or row["min_time"] is None:
                return False
            min_time = float(row["min_time"])
            # Set added_at lebih awal 10 detik dari yang paling depan
            cur = self._conn.execute(
                "UPDATE queue SET added_at=? WHERE id=? AND status='pending'",
                (min_time - 10.0, item_id),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def set_setting(self, key: str, value: str) -> None:
        """Simpan konfigurasi runtime (mis. stream key RTMP) tanpa restart container."""
        with self._lock:
            self._conn.execute(
                "INSERT INTO app_settings (key, value) VALUES (?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
            self._conn.commit()

    def get_setting(self, key: str, default: str = "") -> str:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM app_settings WHERE key=?", (key,)
            ).fetchone()
        return row["value"] if row else default

    def latest_meta(self, video_id: str) -> tuple[str, str, int]:
        """Ambil judul/artis/durasi terakhir dari riwayat untuk video_id (cache lookup)."""
        with self._lock:
            row = self._conn.execute(
                "SELECT title, artist, duration_ms FROM queue WHERE track_uri=? "
                "ORDER BY id DESC LIMIT 1",
                (f"yt:{video_id}",),
            ).fetchone()
        if row is None:
            return ("", "", 0)
        return (row["title"], row["artist"], int(row["duration_ms"] or 0))

    def pop_next(self, chat_id: Optional[int] = None) -> QueueItem | None:
        """Ambil lagu pending teratas dan tandai sebagai playing."""
        query = "SELECT * FROM queue WHERE status='pending'"
        params: list[object] = []
        if chat_id is not None:
            query += " AND chat_id=?"
            params.append(chat_id)
        query += " ORDER BY added_at ASC, id ASC LIMIT 1"

        with self._lock:
            row = self._conn.execute(query, tuple(params)).fetchone()
            if row is None:
                return None
            item_id = row["id"]
            self._conn.execute("UPDATE queue SET status='playing' WHERE id=?", (item_id,))
            self._conn.commit()
            updated = self._conn.execute("SELECT * FROM queue WHERE id=?", (item_id,)).fetchone()
        return self._row_to_item(updated)

    def update_item(
        self,
        item_id: int,
        local_path: Optional[str] = None,
        shoutout_audio_path: Optional[str] = None,
        status: Optional[str] = None,
    ) -> bool:
        sets = []
        params = []
        if local_path is not None:
            sets.append("local_path=?")
            params.append(local_path)
        if shoutout_audio_path is not None:
            sets.append("shoutout_audio_path=?")
            params.append(shoutout_audio_path)
        if status is not None:
            sets.append("status=?")
            params.append(status)

        if not sets:
            return False

        query = f"UPDATE queue SET {', '.join(sets)} WHERE id=?"
        params.append(item_id)

        with self._lock:
            cur = self._conn.execute(query, tuple(params))
            self._conn.commit()
            return cur.rowcount > 0

    def remove(self, item_id: int) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM queue WHERE id=?", (item_id,))
            self._conn.commit()
            return cur.rowcount > 0

    def clear(self, chat_id: Optional[int] = None) -> int:
        with self._lock:
            if chat_id is not None:
                cur = self._conn.execute("DELETE FROM queue WHERE chat_id=?", (chat_id,))
            else:
                cur = self._conn.execute("DELETE FROM queue")
            self._conn.commit()
            return cur.rowcount

    def count(self, chat_id: Optional[int] = None, status: Optional[str] = "pending") -> int:
        query = "SELECT COUNT(*) AS c FROM queue WHERE 1=1"
        params: list[object] = []
        if chat_id is not None:
            query += " AND chat_id=?"
            params.append(chat_id)
        if status is not None:
            query += " AND status=?"
            params.append(status)
        with self._lock:
            row = self._conn.execute(query, tuple(params)).fetchone()
        return int(row["c"])

    def close(self) -> None:
        self._conn.close()

