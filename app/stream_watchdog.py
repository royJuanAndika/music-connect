"""Stream Watchdog: memantau kesehatan proses siaran radio dan restart otomatis."""
from __future__ import annotations

import asyncio
import logging
from typing import Callable, Coroutine, Optional

log = logging.getLogger("stream_watchdog")


class StreamWatchdog:
    def __init__(
        self,
        check_interval_sec: float = 5.0,
        restart_callback: Optional[Callable[[], Coroutine]] = None,
        notify_callback: Optional[Callable[[str], Coroutine]] = None,
    ) -> None:
        self.check_interval_sec = check_interval_sec
        self.restart_callback = restart_callback
        self.notify_callback = notify_callback
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        self._running = True
        log.info("Stream Watchdog aktif memantau siaran.")

    def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()

    async def handle_crash(self, error_message: str) -> None:
        """Dipanggil saat engine audio crash atau berhenti tak terduga."""
        log.error(f"Stream crash terdeteksi: {error_message}")
        if self.notify_callback:
            try:
                await self.notify_callback(f"[Radio Alert] Siaran terhenti tak terduga: {error_message}")
            except Exception as e:
                log.warning(f"Gagal kirim notifikasi crash: {e}")

        if self.restart_callback:
            log.info("Mencoba me-restart stream otomatis...")
            try:
                await self.restart_callback()
            except Exception as e:
                log.error(f"Gagal me-restart siaran: {e}")
