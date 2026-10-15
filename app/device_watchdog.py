"""Watchdog device Spotify Connect.

Tugasnya:
- polling /me/player/devices tiap POLL_INTERVAL_SECONDS
- cari device by NAMA (id ganti tiap reconnect)
- simpan device_id terbaru yang bisa dipakai bot
- transisi online<->offline: kirim notif Telegram sekali saat berubah
- terus retry selama offline, auto-retarget begitu device balik
"""
from __future__ import annotations

import asyncio
import logging

from telegram import Bot

from .config import Settings
from .spotify_client import SpotifyClient, SpotifyError

log = logging.getLogger(__name__)


class DeviceWatchdog:
    def __init__(self, settings: Settings, spotify: SpotifyClient, bot: Bot) -> None:
        self.settings = settings
        self.spotify = spotify
        self.bot = bot
        self.device_id: str | None = None
        self.online: bool = False
        self._last_state: bool | None = None  # None = belum pernah dicek
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    # ---- public ----
    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="device-watchdog")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def current_device_id(self) -> str | None:
        """device_id terbaru; None kalau sedang offline."""
        return self.device_id if self.online else None

    # ---- internal ----
    async def _run(self) -> None:
        log.info("Watchdog mulai. Nama device target: %r", self.settings.device_name)
        while not self._stop.is_set():
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # jangan biarkan watchdog mati
                log.warning("Polling device error: %s", exc)
            try:
                await asyncio.wait_for(
                    self._stop.wait(), timeout=self.settings.poll_interval_seconds
                )
            except asyncio.TimeoutError:
                pass

    async def _poll_once(self) -> None:
        # panggilan API blocking -> jalankan di thread biar tidak blok event loop
        device = await asyncio.to_thread(
            self.spotify.find_device_by_name, self.settings.device_name
        )

        if device is None:
            self._set_state(False)
            return

        # device ada: kalau baru online atau id berubah -> update + transfer kalau perlu
        new_id = device.get("id")
        was_offline = not self.online
        self.device_id = new_id
        self._set_state(True)

        if was_offline:
            log.info("Device online lagi: %r id=%s", device.get("name"), new_id)

    def _set_state(self, online: bool) -> None:
        self.online = online
        if self._last_state is None:
            # state pertama kali: kirim notif hanya kalau offline (biar kamu tahu pas startup)
            self._last_state = online
            if not online:
                self._notify_offline()
            else:
                log.info("Device terdeteksi online saat startup (id=%s).", self.device_id)
            return

        if online == self._last_state:
            return  # tidak berubah, tidak spam

        self._last_state = online
        if online:
            self._notify_online()
        else:
            self._notify_offline()

    # ---- notif (fire and forget) ----
    def _notify_offline(self) -> None:
        asyncio.create_task(
            self._send(
                f"\u26a0\ufe0f Device pemutar *{self.settings.device_name or '?'}* "
                "sedang OFFLINE.\nCek HP Android-nya (Spotify masih jalan? layar nyala?).\n"
                "Bot akan otomatis nyambung lagi begitu device balik."
            )
        )

    def _notify_online(self) -> None:
        asyncio.create_task(
            self._send(
                f"\u2705 Device pemutar *{self.settings.device_name or '?'}* sudah ONLINE lagi. "
                "Siap menerima lagu."
            )
        )

    async def _send(self, text: str) -> None:
        for chat_id in self.settings.notify_targets:
            try:
                await self.bot.send_message(
                    chat_id=chat_id, text=text, parse_mode="Markdown"
                )
            except Exception as exc:
                log.warning("Gagal kirim notif device ke %s: %s", chat_id, exc)
