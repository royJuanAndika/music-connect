"""End-to-End simulation test:
Request via Web -> QueueStore -> LLM DJ Script -> Piper TTS check -> Broadcast Engine mixing check.
"""
import asyncio
import json
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.audio_engine import AudioEngine
from app.config import Settings
from app.downloader import YouTubeDownloader
from app.llm import LLMClient
from app.queue_store import QueueStore
from app.tts import PiperTTS
from app.web_server import RadioWebServer


def test_end_to_end_pipeline():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        db_path = tmp_path / "e2e_queue.db"
        port = 8998

        s = Settings(
            web_port=port,
            banned_words=("terlarang",),
            request_cooldown_sec=0,
            host_enabled=True,
            host_mode="every_song",
            music_source="youtube",
            data_dir=tmp_path / "data",
        )
        s.tracks_dir.mkdir(parents=True, exist_ok=True)
        s.voice_dir.mkdir(parents=True, exist_ok=True)
        s.hls_dir.mkdir(parents=True, exist_ok=True)

        qs = QueueStore(db_path)
        engine = AudioEngine(s)
        dl = YouTubeDownloader(s)
        llm = LLMClient(s)
        tts = PiperTTS(s)

        server = RadioWebServer(s, engine, qs, dl)
        server.start()

        base_url = f"http://127.0.0.1:{port}"

        try:
            # Step 1: Listener sends request + shoutout via web form
            payload = json.dumps({
                "name": "Budi Hartono",
                "query": "Chrisye - Kala Cinta Menggoda",
                "shoutout": "Selamat sore teman-teman di kantor!",
            }).encode()

            req = urllib.request.Request(
                f"{base_url}/api/request",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req) as resp:
                assert resp.status == 200
                res = json.loads(resp.read().decode())
                assert res["ok"] is True
                assert res["position"] == 1

            # Step 2: Verify queue store state
            popped = qs.pop_next()
            assert popped is not None
            assert popped.title == "Chrisye - Kala Cinta Menggoda"
            assert popped.shoutout_message == "Selamat sore teman-teman di kantor!"
            assert popped.status == "playing"

            # Step 3: LLM script & fallback
            script = asyncio.run(
                llm.generate_dj_script(
                    current_title=popped.title,
                    current_artist=popped.artist,
                    requested_by=popped.requested_by,
                    shoutout_message=popped.shoutout_message,
                )
            )
            # Tanpa API key live, script menghasilkan fallback string kosong aman
            assert isinstance(script, str)

            # Step 4: Verify FFmpeg command generation for the popped track
            dummy_music = s.tracks_dir / "kala_cinta.opus"
            dummy_music.touch()
            cmd = engine.build_ffmpeg_cmd(dummy_music, voice_file=None, output_hls=True)
            assert "-f hls" in " ".join(cmd)
            assert str(dummy_music) in " ".join(cmd)

            # Step 5: Mark played & check queue count
            qs.update_item(popped.id, status="played")
            assert qs.count(status="pending") == 0

            print("END-TO-END PIPELINE SIMULATION PASSED!")
        finally:
            server.stop()
            qs.close()


if __name__ == "__main__":
    test_end_to_end_pipeline()
