"""Queue lokal pakai SQLite (satu file, tanpa server DB)."""
from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS queue (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id       INTEGER NOT NULL,
    track_uri     TEXT    NOT NULL,
    title         TEXT    NOT NULL,
    artist        TEXT    NOT NULL,
    duration_ms   INTEGER NOT NULL DEFAULT 0,
    requested_by  TEXT    NOT NULL,
    added_at      REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_queue_chat ON queue(chat_id, id);
"""


@dataclass
class QueueItem:
    id: int
    track_uri: str
    title: str
    artist: str
    duration_ms: int
    requested_by: str


class QueueStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def add(
        self,
        chat_id: int,
        track_uri: str,
        title: str,
        artist: str,
        duration_ms: int,
        requested_by: str,
    ) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO queue (chat_id, track_uri, title, artist, duration_ms, "
                "requested_by, added_at) VALUES (?,?,?,?,?,?,?)",
                (chat_id, track_uri, title, artist, duration_ms, requested_by, time.time()),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def list(self, chat_id: int) -> list[QueueItem]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, track_uri, title, artist, duration_ms, requested_by "
                "FROM queue WHERE chat_id=? ORDER BY id ASC",
                (chat_id,),
            ).fetchall()
        return [
            QueueItem(
                id=r["id"],
                track_uri=r["track_uri"],
                title=r["title"],
                artist=r["artist"],
                duration_ms=r["duration_ms"],
                requested_by=r["requested_by"],
            )
            for r in rows
        ]

    def pop_next(self, chat_id: int) -> QueueItem | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT id, track_uri, title, artist, duration_ms, requested_by "
                "FROM queue WHERE chat_id=? ORDER BY id ASC LIMIT 1",
                (chat_id,),
            ).fetchone()
            if row is None:
                return None
            self._conn.execute("DELETE FROM queue WHERE id=?", (row["id"],))
            self._conn.commit()
        return QueueItem(
            id=row["id"],
            track_uri=row["track_uri"],
            title=row["title"],
            artist=row["artist"],
            duration_ms=row["duration_ms"],
            requested_by=row["requested_by"],
        )

    def remove(self, item_id: int) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM queue WHERE id=?", (item_id,))
            self._conn.commit()
            return cur.rowcount > 0

    def clear(self, chat_id: int) -> int:
        with self._lock:
            cur = self._conn.execute("DELETE FROM queue WHERE chat_id=?", (chat_id,))
            self._conn.commit()
            return cur.rowcount

    def count(self, chat_id: int) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS c FROM queue WHERE chat_id=?", (chat_id,)
            ).fetchone()
        return int(row["c"])

    def close(self) -> None:
        self._conn.close()
