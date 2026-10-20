import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.queue_store import QueueStore


def test_latest_meta():
    tmp = tempfile.mkdtemp()
    qs = QueueStore(Path(tmp) / "q.db")
    qs.add(chat_id=1, track_uri="yt:abc", title="Judul", artist="Artis", duration_ms=1234)
    assert qs.latest_meta("abc") == ("Judul", "Artis", 1234)
    assert qs.latest_meta("tidak-ada") == ("", "", 0)
    print("OK latest_meta")


def test_auto_queue_cached_track():
    from app import main as m

    tmp = Path(tempfile.mkdtemp())
    tracks = tmp / "tracks"
    tracks.mkdir()
    (tracks / "vid123.opus").write_bytes(b"x")
    (tracks / "vid456.opus").write_bytes(b"x")

    qs = QueueStore(tmp / "q.db")
    qs.add(chat_id=1, track_uri="yt:vid123", title="Lagu Satu", artist="Artis", duration_ms=5000)

    class S:
        tracks_dir = tracks
        allowed_group_ids = (-100123,)

    assert m._auto_queue_cached_track(qs, S()) is True
    items = qs.list(status="pending")
    assert len(items) == 1, items
    it = items[0]
    assert it.local_path.endswith(".opus")
    assert it.source_url.startswith("https://www.youtube.com/watch?v=")
    assert it.requested_by == "Radio AI"
    # metadata diambil dari riwayat kalau ada
    if it.track_uri == "yt:vid123":
        assert it.title == "Lagu Satu"
    print("OK auto_queue_cached_track:", it.track_uri, "|", it.title)


if __name__ == "__main__":
    test_latest_meta()
    test_auto_queue_cached_track()
    print("ALL QUEUE AUTOPLAY TESTS PASSED!")
