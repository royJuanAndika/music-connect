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
        self._queue: Optional[asyncio.Queue[AlertItem]] = None
        self._worker_task: Optional[asyncio.Task] = None
        self._is_running = False

    def _get_queue(self) -> asyncio.Queue[AlertItem]:
        """Lazy inisialisasi queue pada event loop yang sedang aktif."""
        if self._queue is None:
            self._queue = asyncio.Queue()
        return self._queue

    def start(self) -> None:
        """Menandai manager aktif. Worker task akan di-start saat event loop aktif."""
        self._is_running = True
        try:
            loop = asyncio.get_running_loop()
            if not self._worker_task or self._worker_task.done():
                self._worker_task = loop.create_task(self._process_alerts())
                log.info("AlertManager worker started.")
        except RuntimeError:
            pass

    def ensure_worker(self) -> None:
        """Memastikan worker running jika event loop sudah tersedia."""
        if self._is_running and (not self._worker_task or self._worker_task.done()):
            try:
                loop = asyncio.get_running_loop()
                self._worker_task = loop.create_task(self._process_alerts())
                log.info("AlertManager worker started lazily.")
            except RuntimeError:
                pass

    async def stop(self) -> None:
        self._is_running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except (asyncio.CancelledError, RuntimeError):
                pass
            self._worker_task = None
        self._queue = None

    async def enqueue_alert(self, requested_by: str, shoutout_to: str, message: str) -> None:
        """Memasukkan alert baru ke antrean live alert in-memory."""
        self.ensure_worker()
        import time
        item = AlertItem(
            requested_by=requested_by,
            shoutout_to=shoutout_to,
            message=message,
            created_at=time.time(),
        )
        q = self._get_queue()
        await q.put(item)
        log.info(f"Alert diterima dari {requested_by} untuk {shoutout_to}: '{message[:30]}...'")

    async def _process_alerts(self) -> None:
        """Background loop pemroses alert secara FIFO real-time."""
        q = self._get_queue()
        while self._is_running:
            try:
                alert = await q.get()
                log.info(f"Memproses live alert dari {alert.requested_by}...")

                # 1. Generate naskah pesan singkat via LLM
                script = ""
                try:
                    script = await self.llm.generate_announcement_script(
                        requested_by=alert.requested_by,
                        shoutout_to=alert.shoutout_to,
                        shoutout_message=alert.message,
                    )
                except Exception as e:
                    log.warning(f"Gagal generate naskah LLM: {e}, menggunakan teks dasar.")

                if not script:
                    to_part = f" untuk {alert.shoutout_to}" if alert.shoutout_to else ""
                    script = f"Perhatian para pendengar. Ada titipan pesan dari {alert.requested_by}{to_part}. Pesannya berbunyi: {alert.message}."

                # 2. Render suara via TTS
                voice_path = None
                try:
                    voice_path = await self.tts.synthesize_async(script)
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

                q.task_done()
            except (asyncio.CancelledError, GeneratorExit):
                break
            except Exception as e:
                if not self._is_running:
                    break
                log.error(f"Error pada loop AlertManager: {e}", exc_info=True)
                try:
                    await asyncio.sleep(1)
                except (asyncio.CancelledError, RuntimeError):
                    break
