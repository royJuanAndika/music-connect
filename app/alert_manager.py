from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .audio_engine import AudioEngine
    from .llm import LLMClient
    from .tts import PiperTTS
    from .config import Settings

log = logging.getLogger(__name__)


@dataclass
class AlertItem:
    requested_by: str
    shoutout_to: str
    message: str
    created_at: float


class AlertManager:
    """Mengelola antrean alert (pesan/salam) real-time dan menyuntikkannya ke siaran aktif."""

    def __init__(
        self,
        settings: Settings,
        audio_engine: AudioEngine,
        llm: LLMClient,
        tts: PiperTTS,
    ) -> None:
        self.settings = settings
        self.audio_engine = audio_engine
        self.llm = llm
        self.tts = tts
        self._queue: asyncio.Queue[AlertItem] = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None
        self._is_running = False

    def start(self) -> None:
        if not self._worker_task or self._worker_task.done():
            self._is_running = True
            self._worker_task = asyncio.create_task(self._process_alerts())
            log.info("AlertManager worker started.")

    async def stop(self) -> None:
        self._is_running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None

    async def enqueue_alert(self, requested_by: str, shoutout_to: str, message: str) -> None:
        """Memasukkan alert baru ke antrean live alert in-memory."""
        import time
        item = AlertItem(
            requested_by=requested_by,
            shoutout_to=shoutout_to,
            message=message,
            created_at=time.time(),
        )
        await self._queue.put(item)
        log.info(f"Alert diterima dari {requested_by} untuk {shoutout_to}: '{message[:30]}...'")

    async def _process_alerts(self) -> None:
        """Background loop pemroses alert secara FIFO real-time."""
        while self._is_running:
            try:
                alert = await self._queue.get()
                log.info(f"Memproses live alert dari {alert.requested_by}...")

                # 1. Generate naskah pesan singkat via LLM
                script = ""
                try:
                    script = await self.llm.generate_announcement_script(
                        requested_by=alert.requested_by,
                        shoutout_to=alert.shoutout_to,
                        message=alert.message,
                    )
                except Exception as e:
                    log.warning(f"Gagal generate naskah LLM: {e}, menggunakan teks dasar.")

                if not script:
                    to_part = f" untuk {alert.shoutout_to}" if alert.shoutout_to else ""
                    script = f"Perhatian para pendengar. Ada titipan pesan dari {alert.requested_by}{to_part}. Pesannya berbunyi: {alert.message}."

                # 2. Render suara via PiperTTS
                voice_path = None
                try:
                    voice_path = await self.tts.synthesize(script, prefix="live_alert")
                except Exception as e:
                    log.error(f"Gagal sintesis suara alert TTS: {e}")

                # 3. Suntikkan audio alert ke audio engine aktif
                if voice_path and voice_path.is_file():
                    try:
                        await self.audio_engine.inject_live_alert(voice_path)
                    except Exception as e:
                        log.error(f"Gagal menyuntikkan audio alert ke AudioEngine: {e}")
                else:
                    log.warning("File suara alert tidak valid / gagal digenerate.")

                self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Error pada loop AlertManager: {e}", exc_info=True)
                await asyncio.sleep(1)
