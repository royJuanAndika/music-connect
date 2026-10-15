"""Entrypoint bot: Telegram long polling + watchdog device + healthcheck HTTP."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

from telegram import Bot, BotCommand
from telegram.ext import Application, CommandHandler

from .config import load_settings
from .device_watchdog import DeviceWatchdog
from .handlers import Handlers
from .llm import LLMClient
from .memory import MemoryStore
from .queue_store import QueueStore
from .spotify_client import SpotifyClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("main")

_state: dict = {"ready": False, "device_online": False, "device_name": ""}

# Daftar command untuk menu autocomplete "/" di Telegram.
BOT_COMMANDS = [
    BotCommand("search", "Cari lagu (5 hasil)"),
    BotCommand("queue", "Tambah lagu ke queue"),
    BotCommand("list", "Lihat isi queue"),
    BotCommand("remove", "Hapus lagu dari queue (nomor)"),
    BotCommand("now", "Lagu yang sedang diputar"),
    BotCommand("next", "Lagu berikutnya"),
    BotCommand("pause", "Jeda"),
    BotCommand("resume", "Lanjut"),
    BotCommand("device", "Status device pemutar"),
    BotCommand("status", "Ringkasan bot"),
    BotCommand("clearqueue", "Kosongkan queue"),
    BotCommand("ask", "Tanya asisten AI (bahasa natural)"),
    BotCommand("routines", "Daftar routine tersimpan"),
    BotCommand("routine", "Putar routine tersimpan"),
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
    watchdog: DeviceWatchdog = app.bot_data["watchdog"]
    spotify: SpotifyClient = app.bot_data["spotify"]
    llm: LLMClient = app.bot_data["llm"]
    task = app.bot_data.get("state_sync_task")
    if task:
        task.cancel()
    await watchdog.stop()
    spotify.close()
    await llm.close()
    _state["ready"] = False
    log.info("Bot berhenti.")


def main() -> None:
    settings = load_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    skip_spotify = os.getenv("SKIP_SPOTIFY", "").strip() in ("1", "true", "yes")
    spotify = SpotifyClient(settings)
    if skip_spotify:
        log.warning("SKIP_SPOTIFY aktif: token Spotify tidak dimuat (mode smoke test).")
    else:
        spotify.load_token()

    queue = QueueStore(settings.db_path)
    memory = MemoryStore(settings.memory_dir)

    # LLM (OpenRouter) - opsional
    llm = LLMClient(settings)
    if llm.enabled:
        log.info("LLM aktif: model=%s", settings.openrouter_model)
    else:
        log.info("LLM nonaktif (OPENROUTER_API_KEY kosong).")

    # Bot instance dipakai watchdog untuk notif (diisi ulang di post_init)
    bot = Bot(token=settings.telegram_bot_token)
    watchdog = DeviceWatchdog(settings, spotify, bot)

    start_health_server(settings.health_port)

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

    h = Handlers(settings, spotify, queue, watchdog, llm=llm, memory=memory)
    app.add_handler(CommandHandler(["start", "help"], h.cmd_start))
    app.add_handler(CommandHandler("status", h.cmd_status))
    app.add_handler(CommandHandler("device", h.cmd_device))
    app.add_handler(CommandHandler("search", h.cmd_search))
    app.add_handler(CommandHandler(["queue", "q"], h.cmd_queue))
    app.add_handler(CommandHandler("list", h.cmd_list))
    app.add_handler(CommandHandler("remove", h.cmd_remove))
    app.add_handler(CommandHandler("now", h.cmd_now))
    app.add_handler(CommandHandler("next", h.cmd_next))
    app.add_handler(CommandHandler("pause", h.cmd_pause))
    app.add_handler(CommandHandler("resume", h.cmd_resume))
    app.add_handler(CommandHandler("clearqueue", h.cmd_clearqueue))
    app.add_handler(CommandHandler("ask", h.cmd_ask))
    app.add_handler(CommandHandler("routines", h.cmd_routines))
    app.add_handler(CommandHandler("routine", h.cmd_routine))
    app.add_handler(CommandHandler("whoami", h.cmd_whoami))

    # log tiap update masuk (bantu debug, termasuk pesan grup)
    async def _log_update(update, ctx):
        chat = update.effective_chat
        user = update.effective_user
        text = update.effective_message.text if update.effective_message else None
        log.info(
            "UPDATE chat=%s(%s) user=%s text=%r",
            chat.id if chat else None,
            chat.type if chat else None,
            user.id if user else None,
            text,
        )

    from telegram.ext import MessageHandler, filters

    app.add_handler(MessageHandler(filters.ALL, _log_update), group=10)

    # pesan teks biasa (bukan command) -> LLM dengan tool calling
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, h.cmd_ask), group=11
    )

    # log kalau bot di-add/kick dari grup
    async def _log_member(update, ctx):
        m = update.my_chat_member
        if m is None:
            return
        log.info(
            "CHAT_MEMBER chat=%s(%s) status=%s oleh=%s",
            m.chat.id,
            m.chat.type,
            m.new_chat_member.status if m.new_chat_member else "?",
            m.from_user.id if m.from_user else "?",
        )

    from telegram.ext import ChatMemberHandler

    app.add_handler(ChatMemberHandler(_log_member, ChatMemberHandler.MY_CHAT_MEMBER))

    log.info("Menjalankan bot (long polling)...")
    app.run_polling(
        allowed_updates=["message", "my_chat_member", "edited_message"]
    )


if __name__ == "__main__":
    main()
