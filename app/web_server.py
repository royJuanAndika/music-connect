"""Web server async berbasis stdlib http.server untuk HLS stream & REST API."""
from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Optional

from .audio_engine import AudioEngine
from .config import Settings
from .downloader import DownloaderError, YouTubeDownloader
from .queue_store import QueueStore, QueueValidationError

log = logging.getLogger("web_server")


class RadioHTTPRequestHandler(SimpleHTTPRequestHandler):
    # Didefinisikan per instance server
    settings: Settings
    audio_engine: AudioEngine
    queue_store: QueueStore
    downloader: YouTubeDownloader

    def log_message(self, format: str, *args: object) -> None:
        # Kurangi log berisik untuk segmen HLS
        if "GET /hls/" in str(args):
            return
        log.info("%s - - [%s] %s" % (self.address_string(), self.log_date_time_string(), format % args))

    def _send_json(self, status: int, data: dict | list) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        clean_path = self.path.split("?", 1)[0]

        # 1. API: Now Playing
        if clean_path == "/api/now-playing":
            st = self.audio_engine.state
            return self._send_json(200, {
                "is_running": st.is_running,
                "title": st.current_title,
                "artist": st.current_artist,
                "is_host_speaking": st.is_host_speaking,
                "shoutout": st.current_shoutout,
            })

        # 2. API: Queue
        if clean_path == "/api/queue":
            items = self.queue_store.list(status="pending")
            return self._send_json(200, [
                {
                    "id": it.id,
                    "title": it.title,
                    "artist": it.artist,
                    "requested_by": it.requested_by,
                }
                for it in items
            ])

        # 3. Static HLS files (.m3u8 & .ts)
        if clean_path.startswith("/hls/"):
            filename = clean_path[len("/hls/"):]
            file_path = self.settings.hls_dir / filename
            if not file_path.is_file():
                self.send_error(HTTPStatus.NOT_FOUND, "HLS Segment Not Found")
                return

            ctype, _ = mimetypes.guess_type(str(file_path))
            if filename.endswith(".m3u8"):
                ctype = "application/vnd.apple.mpegurl"
            elif filename.endswith(".ts"):
                ctype = "video/mp2t"

            try:
                data = file_path.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", ctype or "application/octet-stream")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-cache, no-store")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)
                return
            except Exception as e:
                log.warning(f"Error serving HLS file: {e}")
                self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR)
                return

        # 4. Web index & assets
        if clean_path in ("/", "/index.html"):
            index_path = Path("web/index.html")
            if not index_path.is_file():
                self.send_error(HTTPStatus.NOT_FOUND, "Web player not found")
                return
            data = index_path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def do_POST(self) -> None:
        clean_path = self.path.split("?", 1)[0]
        if clean_path != "/api/request":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        if not self.settings.web_requests_open:
            return self._send_json(403, {"ok": False, "error": "Request lagu dari web sedang ditutup."})

        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body_bytes = self.rfile.read(content_length)
            payload = json.loads(body_bytes.decode("utf-8"))
        except Exception:
            return self._send_json(400, {"ok": False, "error": "Payload JSON tidak valid."})

        name = str(payload.get("name", "Pendengar Web")).strip()
        query = str(payload.get("query", "")).strip()
        shoutout = str(payload.get("shoutout", "")).strip()

        if not query:
            return self._send_json(400, {"ok": False, "error": "Kueri lagu tidak boleh kosong."})

        # Cek batas karakter salam
        if len(shoutout) > self.settings.shoutout_max_chars:
            return self._send_json(
                400,
                {"ok": False, "error": f"Pesan salam maksimal {self.settings.shoutout_max_chars} karakter."}
            )

        # Cek moderasi & kuota
        text_check = f"{query} {shoutout}"
        try:
            self.queue_store.check_moderation_and_quota(
                requested_by=name,
                text_to_check=text_check,
                banned_words=self.settings.banned_words,
                max_user_quota=self.settings.max_queue_per_user,
                max_total_quota=self.settings.max_queue_total,
                cooldown_sec=self.settings.request_cooldown_sec,
            )
        except QueueValidationError as e:
            return self._send_json(429, {"ok": False, "error": str(e)})

        # Resolusi metadata YouTube (jika downloader siap)
        title = query
        artist = "YouTube"
        track_uri = f"query:{query}"
        source_url = ""

        if self.downloader.is_available():
            try:
                meta = self.downloader.resolve_query(query)
                title = meta.title
                artist = meta.uploader
                track_uri = f"yt:{meta.video_id}"
                source_url = meta.webpage_url
            except DownloaderError as e:
                return self._send_json(400, {"ok": False, "error": str(e)})

        item_id = self.queue_store.add(
            chat_id=0,  # 0 untuk web
            track_uri=track_uri,
            title=title,
            artist=artist,
            duration_ms=0,
            requested_by=name,
            source_type="youtube",
            source_url=source_url,
            shoutout_message=shoutout,
        )

        total_pos = self.queue_store.count(status="pending")
        return self._send_json(200, {
            "ok": True,
            "id": item_id,
            "title": title,
            "artist": artist,
            "position": total_pos,
        })


class RadioWebServer:
    def __init__(
        self,
        settings: Settings,
        audio_engine: AudioEngine,
        queue_store: QueueStore,
        downloader: YouTubeDownloader,
    ) -> None:
        self.settings = settings
        self.audio_engine = audio_engine
        self.queue_store = queue_store
        self.downloader = downloader
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[Thread] = None

    def start(self) -> None:
        handler = RadioHTTPRequestHandler
        handler.settings = self.settings
        handler.audio_engine = self.audio_engine
        handler.queue_store = self.queue_store
        handler.downloader = self.downloader

        addr = ("0.0.0.0", self.settings.web_port)
        self._server = ThreadingHTTPServer(addr, handler)
        self._thread = Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        log.info(f"Web Player & REST API berjalan di http://0.0.0.0:{self.settings.web_port}")

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
