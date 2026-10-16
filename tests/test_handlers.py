"""Unit tests untuk integrasi handlers, tool calling, dan bot setup."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Settings
from app.queue_store import QueueStore
from app.tools import ToolContext, run_queue


def test_handlers_and_tools():
    s = Settings(
        music_source="youtube",
        max_queue_per_user=5,
        max_queue_total=20,
        request_cooldown_sec=0,
    )
    db_path = Path("data/test_handlers_queue.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    qs = QueueStore(db_path)

    ctx = ToolContext(
        settings=s,
        spotify=None,  # type: ignore
        queue=qs,
        watchdog=None,  # type: ignore
        chat_id=123,
        requested_by="Alice",
    )

    # 1. Test run_queue in youtube radio mode with shoutout
    res = run_queue(ctx, query="Dewa 19 Kangen", shoutout="Salam buat keluarga di Surabaya")
    assert "error" not in res, f"Expected no error, got: {res}"
    assert res.get("radio_mode") is True
    assert res.get("shoutout") == "Salam buat keluarga di Surabaya"
    assert res.get("queue_position") == 1

    # 2. Check stored item in SQLite
    items = qs.list(chat_id=123)
    assert len(items) == 1
    assert items[0].title == "Dewa 19 Kangen"
    assert items[0].shoutout_message == "Salam buat keluarga di Surabaya"
    assert items[0].source_type == "youtube"

    # 3. Test source_type='message' addition
    msg_id = qs.add(
        chat_id=123,
        track_uri="msg:test",
        title="📢 Pengumuman Radio",
        artist="Admin",
        duration_ms=0,
        requested_by="AdminRoy",
        source_type="message",
        shoutout_to="Semua Pegawai",
        shoutout_message="Jangan lupa meeting jam 2",
    )
    assert msg_id > 0
    msg_item = qs.list(chat_id=123)[-1]
    assert msg_item.source_type == "message"
    assert msg_item.shoutout_to == "Semua Pegawai"

    qs.close()
    if db_path.exists():
        db_path.unlink()

    print("ALL HANDLER & TOOL TESTS PASSED!")


if __name__ == "__main__":
    test_handlers_and_tools()
