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
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_handlers_queue.db"
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
        from unittest.mock import patch, MagicMock
        with patch("app.downloader.YouTubeDownloader") as mock_dl_cls:
            mock_dl = mock_dl_cls.return_value
            mock_dl.is_available.return_value = True
            mock_meta = MagicMock()
            mock_meta.video_id = "mock123"
            mock_meta.title = "Dewa 19 Kangen"
            mock_meta.uploader = "Dewa 19"
            mock_meta.webpage_url = "https://youtube.com/watch?v=mock123"
            mock_meta.duration_sec = 240
            mock_dl.resolve_query.return_value = mock_meta

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

        # 3. Test source_type='message' addition and bump
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
        ok = qs.bump_to_front(msg_id)
        assert ok is True
        popped = qs.pop_next(chat_id=123)
        assert popped.id == msg_id
        assert popped.source_type == "message"
        assert popped.shoutout_to == "Semua Pegawai"

        qs.close()

    # 4. Test cooldown logic on handlers
    import asyncio
    from unittest.mock import AsyncMock, MagicMock
    from app.handlers import Handlers

    handlers = Handlers(
        settings=Settings(
            allowed_telegram_ids=(999,),
            message_cooldown_sec=300,
        ),
        spotify=None,  # type: ignore
        queue=MagicMock(),
        watchdog=None,  # type: ignore
    )

    update = MagicMock()
    update.effective_chat.type = "group"
    update.effective_chat.id = -100123
    update.effective_user.id = 111
    update.effective_user.username = "listener"
    update.message.reply_text = AsyncMock()

    ctx = MagicMock()
    ctx.args = ["Halo", "semua"]

    # First call: succeeds
    asyncio.run(handlers.cmd_pesan(update, ctx))
    assert handlers.queue.add.called
    assert update.message.reply_text.called
    first_reply = update.message.reply_text.call_args[0][0]
    assert "Pengumuman Disiarkan" in first_reply

    # Second call immediately: rejected by 5 min cooldown
    update.message.reply_text.reset_mock()
    handlers.queue.add.reset_mock()
    asyncio.run(handlers.cmd_pesan(update, ctx))
    assert not handlers.queue.add.called
    second_reply = update.message.reply_text.call_args[0][0]
    assert "Harap tunggu" in second_reply
    assert "menit" in second_reply

    print("ALL HANDLER & TOOL TESTS PASSED!")


if __name__ == "__main__":
    test_handlers_and_tools()
