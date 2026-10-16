"""Unit tests untuk skema, migrasi, kuota, cooldown, dan filter kata terlarang QueueStore."""
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.queue_store import QueueStore, QueueValidationError


def test_queue_store():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_queue.db"
        qs = QueueStore(db_path)

        # 1. Test schema inspection
        cur = qs._conn.execute("PRAGMA table_info(queue)")
        cols = {r["name"] for r in cur.fetchall()}
        required_cols = {
            "id", "chat_id", "track_uri", "title", "artist", "duration_ms",
            "requested_by", "added_at", "source_type", "source_url",
            "local_path", "shoutout_to", "shoutout_message", "shoutout_audio_path", "status"
        }
        assert required_cols.issubset(cols), f"Missing columns in schema: {required_cols - cols}"

        # 2. Test Banned Words
        banned = ("judi", "slot")
        try:
            qs.check_moderation_and_quota("user1", "Mau request lagu judul slot online", banned)
            assert False, "Should fail banned word check"
        except QueueValidationError as e:
            assert "slot" in str(e)

        # 3. Test Add & Count
        item_id1 = qs.add(
            chat_id=100,
            track_uri="yt:vid1",
            title="Lagu Satu",
            artist="Artis Satu",
            duration_ms=180000,
            requested_by="user1",
            source_type="youtube",
            source_url="https://youtube.com/watch?v=vid1",
            shoutout_to="Anak Kantor",
            shoutout_message="Salam buat kawan-kawan",
        )
        assert item_id1 > 0
        assert qs.count(status="pending") == 1
        items = qs.list(status="pending")
        assert items[0].shoutout_to == "Anak Kantor"

        # 4. Test Cooldown
        try:
            qs.check_moderation_and_quota("user1", "Lagu Kedua", banned, cooldown_sec=10)
            assert False, "Should fail cooldown check"
        except QueueValidationError as e:
            assert "tunggu" in str(e).lower()

        # 5. Test User Quota (simulate multiple items for user2)
        qs.add(100, "yt:vid2", "Lagu Dua", "Artis", 180000, "user2")
        qs.add(100, "yt:vid3", "Lagu Tiga", "Artis", 180000, "user2")
        try:
            qs.check_moderation_and_quota("user2", "Lagu Empat", banned, max_user_quota=2, cooldown_sec=0)
            assert False, "Should fail user quota check"
        except QueueValidationError as e:
            assert "kuota aktif" in str(e).lower()

        # 6. Test Pop Next & Update
        popped = qs.pop_next()
        assert popped is not None
        assert popped.id == item_id1
        assert popped.status == "playing"
        assert popped.shoutout_message == "Salam buat kawan-kawan"

        # Update local_path and status
        qs.update_item(popped.id, local_path="/path/to/audio.opus", status="played")
        items = qs.list(status="played")
        assert len(items) == 1
        assert items[0].local_path == "/path/to/audio.opus"

        qs.close()
        print("ALL QUEUE STORE TESTS PASSED!")


if __name__ == "__main__":
    test_queue_store()
