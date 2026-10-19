"""Unit tests untuk Web Server HTTP endpoints (now-playing, queue, request)."""
import json
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.audio_engine import AudioEngine
from app.config import Settings
from app.downloader import YouTubeDownloader
from app.queue_store import QueueStore
from app.web_server import RadioWebServer


def test_web_server():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_web_queue.db"
        port = 8999
        s = Settings(
            web_port=port,
            banned_words=("kasar",),
            request_cooldown_sec=0,
        )
        qs = QueueStore(db_path)
        engine = AudioEngine(s)
        dl = YouTubeDownloader(s)

        server = RadioWebServer(s, engine, qs, dl)
        server.start()
        time.sleep(0.5)

        base_url = f"http://127.0.0.1:{port}"

        try:
            # 1. Test GET /api/now-playing
            with urllib.request.urlopen(f"{base_url}/api/now-playing") as resp:
                assert resp.status == 200
                data = json.loads(resp.read().decode())
                assert "title" in data
                assert "is_host_speaking" in data

            # 2. Test POST /api/request (valid)
            req_data = json.dumps({
                "name": "Budi",
                "query": "Sheila on 7 Dan",
                "shoutout": "Salam manis",
            }).encode()
            req = urllib.request.Request(
                f"{base_url}/api/request",
                data=req_data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req) as resp:
                assert resp.status == 200
                res = json.loads(resp.read().decode())
                assert res["ok"] is True
                assert res["position"] == 1

            # 3. Test GET /api/queue
            with urllib.request.urlopen(f"{base_url}/api/queue") as resp:
                assert resp.status == 200
                items = json.loads(resp.read().decode())
                assert len(items) == 1
                assert items[0]["requested_by"] == "Budi"

            # 4. Test GET / (index html)
            with urllib.request.urlopen(f"{base_url}/") as resp:
                assert resp.status == 200
                html = resp.read().decode()
                assert "Radio Stream AI" in html

            print("ALL WEB SERVER TESTS PASSED!")
        finally:
            server.stop()
            qs.close()


if __name__ == "__main__":
    test_web_server()
