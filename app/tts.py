"""Wrapper Text-to-Speech untuk Host Radio AI (mendukung Edge-TTS Neural dan Piper lokal)."""
from __future__ import annotations

import asyncio
import logging
import subprocess
import time
from pathlib import Path
from typing import Optional

from .binary_resolver import resolve_binary
from .config import Settings

log = logging.getLogger("tts")

try:
    import edge_tts
except ImportError:
    edge_tts = None  # type: ignore


class TTSError(Exception):
    """Kesalahan proses text-to-speech."""
    pass


class RadioTTS:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        info = resolve_binary("piper", settings.piper_path)
        self.bin_path = str(info.path) if info.is_available and info.path else "piper"
        self.model_path = Path(settings.piper_model)

    def is_available(self) -> bool:
        """Cek ketersediaan engine TTS yang dikonfigurasi."""
        if not self.settings.host_enabled:
            return False

        if self.settings.tts_engine == "edge-tts":
            return edge_tts is not None

        # Fallback Piper
        info = resolve_binary("piper", self.settings.piper_path)
        return info.is_available and self.model_path.is_file()

    async def synthesize_async(self, text: str, output_path: Optional[Path] = None) -> Path:
        """Sintesis naskah ucapan menjadi berkas audio."""
        clean_text = text.strip()
        if not clean_text:
            raise TTSError("Teks naskah TTS tidak boleh kosong.")

        if not self.settings.host_enabled:
            raise TTSError("AI Host dinonaktifkan (HOST_ENABLED=false).")

        self.settings.voice_dir.mkdir(parents=True, exist_ok=True)
        if output_path is None:
            ext = "mp3" if self.settings.tts_engine == "edge-tts" else "wav"
            output_path = self.settings.voice_dir / f"host_{int(time.time() * 1000)}.{ext}"
        else:
            output_path.parent.mkdir(parents=True, exist_ok=True)

        # 1. Gunakan Edge-TTS Neural (Default)
        if self.settings.tts_engine == "edge-tts" and edge_tts is not None:
            voice = self.settings.tts_voice or "id-ID-GadisNeural"
            try:
                # rate="-5%" dan pitch="+2Hz" untuk intonasi lebih lembut, santai, dan manja
                communicate = edge_tts.Communicate(clean_text, voice, rate="-6%", pitch="+3Hz")
                await communicate.save(str(output_path))
                if output_path.is_file() and output_path.stat().st_size > 0:
                    return output_path
            except Exception as e:
                log.warning(f"Edge-TTS gagal: {e}, mencoba fallback Piper...")

        # 2. Fallback ke Piper TTS lokal jika tersedia
        return await asyncio.to_thread(self._synthesize_piper, clean_text, output_path)

    def synthesize(self, text: str, output_path: Optional[Path] = None) -> Path:
        """Synchronous wrapper untuk synthesize_async."""
        return asyncio.run(self.synthesize_async(text, output_path))

    def _synthesize_piper(self, clean_text: str, output_path: Path) -> Path:
        info = resolve_binary("piper", self.settings.piper_path)
        if not info.is_available or not self.model_path.is_file():
            raise TTSError("Tidak ada engine TTS yang tersedia (Edge-TTS dan Piper offline).")

        # Jika target berekstensi mp3, ubah ke wav untuk Piper
        if output_path.suffix.lower() == ".mp3":
            output_path = output_path.with_suffix(".wav")

        cmd = [
            self.bin_path,
            "--model", str(self.model_path),
            "--output_file", str(output_path),
        ]

        try:
            res = subprocess.run(
                cmd,
                input=clean_text,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if res.returncode != 0:
                raise TTSError(f"Piper exit {res.returncode}: {res.stderr.strip()}")
        except Exception as e:
            raise TTSError(f"Piper execution failed: {e}")

        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise TTSError("Piper selesai namun output kosong.")

        return output_path


# Alias kompatibilitas
PiperTTS = RadioTTS
