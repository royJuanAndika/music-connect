"""Entrypoint bot: Telegram long polling + watchdog device + healthcheck HTTP."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread

from telegram import Bot, BotCommand
from telegram.ext import Application, CommandHandler

from .audio_engine import AudioEngine
from .config import load_settings
from .device_watchdog import DeviceWatchdog
from .downloader import YouTubeDownloader
from .handlers import Handlers
from .llm import LLMClient
from .memory import MemoryStore
from .queue_store import QueueStore
from .spotify_client import SpotifyClient
from .stream_watchdog import StreamWatchdog
from .tts import PiperTTS
from .web_server import RadioWebServer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("main")

_state: dict = {"ready": False, "device_online": False, "device_name": ""}

BOT_COMMANDS = [
    BotCommand("search", "Cari lagu YouTube & pilih tombol"),
    BotCommand("request", "Request lagu (judul atau URL YouTube)"),
    BotCommand("salam", "Request + titip salam (judul | salam)"),
    BotCommand("pesan", "Siarkan pesan pengumuman suara"),
    BotCommand("skip", "Lewati lagu yang sedang diputar"),
    BotCommand("bump", "Dahulukan lagu ke urutan depan (nomor)"),
    BotCommand("now", "Lagu & sisa durasi siaran saat ini"),
    BotCommand("list", "Lihat antrian lagu"),
    BotCommand("remove", "Hapus lagu dari antrian"),
    BotCommand("ask", "Ngobrol atau request lewat AI"),
    BotCommand("status", "Status siaran radio"),
    BotCommand("help", "Bantuan"),
]


class _Health(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/healthz":
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps(_state).encode()
        self.send_response(200 if _state["ready"] else 503)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:
        pass


def start_health_server(port: int) -> None:
    def _serve() -> None:
        HTTPServer(("0.0.0.0", port), _Health).serve_forever()

    Thread(target=_serve, daemon=True).start()
    log.info("Healthcheck di http://0.0.0.0:%d/healthz", port)


async def _watchdog_state_sync(app: Application) -> None:
    """Update _state untuk healthcheck secara berkala."""
    watchdog: DeviceWatchdog = app.bot_data["watchdog"]
    while True:
        _state["device_online"] = watchdog.online
        await asyncio.sleep(5)


async def _post_init(app: Application) -> None:
    settings = app.bot_data["settings"]
    watchdog: DeviceWatchdog = app.bot_data["watchdog"]

    # daftarkan command supaya muncul di menu "/" Telegram
    try:
        await app.bot.set_my_commands(BOT_COMMANDS)
        log.info("Command terdaftar (%d) untuk menu Telegram.", len(BOT_COMMANDS))
    except Exception as exc:
        log.warning("Gagal daftar command Telegram: %s", exc)

    # watchdog butuh Bot untuk notif
    watchdog.bot = app.bot
    watchdog.start()
    app.bot_data["state_sync_task"] = asyncio.create_task(_watchdog_state_sync(app))
    _state["device_name"] = settings.device_name
    _state["ready"] = True
    log.info("Bot siap. Long polling mulai.")


async def _post_shutdown(app: Application) -> None:
    watchdog = app.bot_data.get("watchdog")
    spotify = app.bot_data.get("spotify")
    llm = app.bot_data.get("llm")
    task = app.bot_data.get("broadcast_task")
    if task:
        task.cancel()
    if watchdog:
        await watchdog.stop()
    if spotify:
        spotify.close()
    if llm and hasattr(llm, "close"):
        await llm.close()
    _state["ready"] = False
    log.info("Bot berhenti.")


async def _broadcast_loop(
    settings,
    audio_engine: AudioEngine,
    queue_store: QueueStore,
    downloader: YouTubeDownloader,
    llm: LLMClient,
    tts: PiperTTS,
) -> None:
    """Loop penyiaran background berkelanjutan."""
    log.info("Memulai background loop siaran radio...")
    song_counter = 0

    while True:
        try:
            item = queue_store.pop_next()
            if not item:
                # Antrian kosong: jika streaming RTMP aktif, putar standby loop agar stream tetap hidup
                if settings.stream_mode in ("rtmp", "both") and settings.rtmp_url and audio_engine.is_available():
                    await asyncio.to_thread(audio_engine.play_standby_sync, 15)
                else:
                    await asyncio.sleep(2)
                continue

            song_counter += 1
            log.info(f"Memproses lagu #{item.id}: {item.title} - {item.artist}")

            # Penanganan Item Tipe 'message' (Pengumuman Pesan Suara Mandiri Khusus Admin)
            if item.source_type == "message":
                log.info(f"Memproses pengumuman suara #{item.id} dari {item.requested_by}")
                try:
                    script = await llm.generate_announcement_script(
                        requested_by=item.requested_by,
                        shoutout_to=item.shoutout_to,
                        shoutout_message=item.shoutout_message,
                    )
                    voice_file = await tts.synthesize_async(script)
                    queue_store.update_item(item.id, shoutout_audio_path=str(voice_file))

                    if audio_engine.is_available():
                        await asyncio.to_thread(
                            audio_engine.play_message_sync,
                            voice_file=voice_file,
                            shoutout_to=item.shoutout_to,
                            message=item.shoutout_message,
                        )
                except Exception as e:
                    log.error(f"Gagal menyiarkan pesan #{item.id}: {e}", exc_info=True)
                finally:
                    queue_store.update_item(item.id, status="played")
                continue

            # 1. Download & pastikan audio track tersedia
            music_file = Path(item.local_path) if item.local_path else None
            if not music_file or not music_file.is_file():
                if item.source_type == "youtube" and downloader.is_available():
                    try:
                        meta = downloader.resolve_query(item.source_url or item.title)
                        music_file = downloader.download_audio(meta)
                        queue_store.update_item(
                            item.id,
                            local_path=str(music_file),
                        )
                        if item.duration_ms == 0 and meta.duration_sec > 0:
                            duration_sec = meta.duration_sec
                            item.duration_ms = meta.duration_sec * 1000
                    except Exception as e:
                        log.error(f"Gagal mengunduh audio #{item.id}: {e}")
                        queue_store.update_item(item.id, status="error")
                        continue

            if not music_file or not music_file.is_file():
                log.warning(f"File audio tidak tersedia untuk item #{item.id}, melewati...")
                queue_store.update_item(item.id, status="error")
                continue

            # 2. AI Host: Naskah + TTS (jika aktif)
            voice_file = None
            should_host_speak = False

            if settings.host_enabled:
                if settings.host_mode == "every_song":
                    should_host_speak = True
                elif settings.host_mode == "interval":
                    should_host_speak = (song_counter % max(1, settings.host_interval_songs) == 0)
                elif settings.host_mode == "request_only":
                    should_host_speak = bool(item.shoutout_message)

            if should_host_speak:
                try:
                    script = await llm.generate_dj_script(
                        current_title=item.title,
                        current_artist=item.artist,
                        requested_by=item.requested_by,
                        shoutout_to=item.shoutout_to,
                        shoutout_message=item.shoutout_message,
                    )
                    if script and tts.is_available():
                        voice_file = await tts.synthesize_async(script)
                        queue_store.update_item(item.id, shoutout_audio_path=str(voice_file))
                except Exception as e:
                    log.warning(f"AI Host pipeline fallback (play musik saja): {e}")

            # 3. Putar di AudioEngine (blocking di worker thread)
            duration_sec = item.duration_ms // 1000 if item.duration_ms > 0 else 0
            if audio_engine.is_available():
                await asyncio.to_thread(
                    audio_engine.play_track_sync,
                    music_file=music_file,
                    voice_file=voice_file,
                    title=item.title,
                    artist=item.artist,
                    shoutout=item.shoutout_message,
                    duration_sec=duration_sec,
                )
            else:
                log.warning("FFmpeg tidak tersedia; simulasi jeda pemutaran.")
                await asyncio.sleep(5)

            queue_store.update_item(item.id, status="played")

        except asyncio.CancelledError:
            log.info("Broadcast loop dihentikan.")
            break
        except Exception as e:
            log.error(f"Error pada broadcast loop: {e}", exc_info=True)
            await asyncio.sleep(3)


def main() -> None:
    settings = load_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.tracks_dir.mkdir(parents=True, exist_ok=True)
    settings.voice_dir.mkdir(parents=True, exist_ok=True)
    settings.hls_dir.mkdir(parents=True, exist_ok=True)

    # Inisialisasi komponen inti radio
    queue = QueueStore(settings.db_path)
    memory = MemoryStore(settings.memory_dir)
    downloader = YouTubeDownloader(settings)
    audio_engine = AudioEngine(settings)
    llm = LLMClient(settings)
    tts = PiperTTS(settings)

    # Inisialisasi & jalankan Web Server
    web_server = RadioWebServer(settings, audio_engine, queue, downloader)
    web_server.start()

    # Jalankan Health check HTTP lama
    start_health_server(settings.health_port)

    # Spotify (mode kompatibilitas)
    spotify = SpotifyClient(settings)
    watchdog = None
    if settings.music_source == "spotify":
        spotify.load_token()
        watchdog = DeviceWatchdog(settings, spotify)

    # Setup handlers
    h = Handlers(settings, spotify, queue, watchdog, llm=llm, memory=memory)
    h.set_radio_components(audio_engine, downloader)

    if not settings.telegram_enabled or not settings.telegram_bot_token:
        log.info("Telegram bot dinonaktifkan / token kosong. Menjalankan broadcast & web player saja...")
        asyncio.run(
            _broadcast_loop(settings, audio_engine, queue, downloader, llm, tts)
        )
        return

    # Inisialisasi Telegram Bot Application
    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )
    app.bot_data["settings"] = settings
    app.bot_data["spotify"] = spotify
    app.bot_data["queue"] = queue
    app.bot_data["watchdog"] = watchdog
    app.bot_data["llm"] = llm
    app.bot_data["audio_engine"] = audio_engine

    # Register command handlers
    app.add_handler(CommandHandler(["start", "help"], h.cmd_start))
    app.add_handler(CommandHandler("status", h.cmd_status))
    app.add_handler(CommandHandler("search", h.cmd_search))
    app.add_handler(CommandHandler(["request", "queue", "q"], h.cmd_queue))
    app.add_handler(CommandHandler("salam", h.cmd_salam))
    app.add_handler(CommandHandler("pesan", h.cmd_pesan))
    app.add_handler(CommandHandler(["next", "skip"], h.cmd_next))
    app.add_handler(CommandHandler(["bump", "top"], h.cmd_bump))
    app.add_handler(CommandHandler("list", h.cmd_list))
    app.add_handler(CommandHandler("remove", h.cmd_remove))
    app.add_handler(CommandHandler("now", h.cmd_now))
    app.add_handler(CommandHandler("ask", h.cmd_ask))
    app.add_handler(CommandHandler("whoami", h.cmd_whoami))

    # Callback Query Handler (Inline Keyboard Button clicks)
    from telegram.ext import CallbackQueryHandler
    app.add_handler(CallbackQueryHandler(h.handle_callback))

    # Natural language message handler
    from telegram.ext import MessageHandler, filters
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, h.cmd_ask), group=11
    )

    # Mulai broadcast background task saat startup bot
    async def _start_broadcast_task(application: Application):
        application.bot_data["broadcast_task"] = asyncio.create_task(
            _broadcast_loop(settings, audio_engine, queue, downloader, llm, tts)
        )
        try:
            await application.bot.set_my_commands(BOT_COMMANDS)
            log.info("Command terdaftar (%d) untuk menu Telegram.", len(BOT_COMMANDS))
        except Exception as exc:
            log.warning("Gagal daftar command Telegram: %s", exc)
        _state["ready"] = True
        log.info("Bot siap. Long polling mulai.")

    app.post_init = _start_broadcast_task

    log.info("Menjalankan Radio Stream AI bot + broadcast engine...")
    app.run_polling(allowed_updates=["message", "my_chat_member", "edited_message"])


if __name__ == "__main__":
    main()
