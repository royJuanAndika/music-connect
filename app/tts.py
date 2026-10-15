"""Wrapper Piper TTS lokal untuk merender teks naskah menjadi file WAV."""
from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path
from typing import Optional

from .binary_resolver import resolve_binary
from .config import Settings

log = logging.getLogger("tts")


class TTSError(Exception):
    """Kesalahan proses text-to-speech."""
    pass


class PiperTTS:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        info = resolve_binary("piper", settings.piper_path)
        self.bin_path = str(info.path) if info.is_available and info.path else "piper"
        self.model_path = Path(settings.piper_model)

    def is_available(self) -> bool:
        """Cek ketersediaan binary piper dan berkas model onnx."""
        info = resolve_binary("piper", self.settings.piper_path)
        return info.is_available and self.model_path.is_file()

    def synthesize(self, text: str, output_path: Optional[Path] = None) -> Path:
        """Render teks ucapan menjadi file audio WAV."""
        clean_text = text.strip()
        if not clean_text:
            raise TTSError("Teks naskah TTS tidak boleh kosong.")

        if not self.settings.host_enabled:
            raise TTSError("AI Host dinonaktifkan (HOST_ENABLED=false).")

        if output_path is None:
            self.settings.voice_dir.mkdir(parents=True, exist_ok=True)
            output_path = self.settings.voice_dir / f"host_{int(time.time() * 1000)}.wav"
        else:
            output_path.parent.mkdir(parents=True, exist_ok=True)

        info = resolve_binary("piper", self.settings.piper_path)
        if not info.is_available:
            raise TTSError(f"Binary Piper tidak ditemukan di path: {self.bin_path}")

        if not self.model_path.is_file():
            raise TTSError(f"Model suara Piper tidak ditemukan di: {self.model_path}")

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
                err_msg = res.stderr.strip() or "Piper TTS gagal tanpa pesan error."
                raise TTSError(f"Piper exit {res.returncode}: {err_msg}")
        except FileNotFoundError:
            raise TTSError(f"Binary Piper tidak dapat dieksekusi: {self.bin_path}")
        except subprocess.TimeoutExpired:
            raise TTSError("Sintesis suara Piper timeout.")

        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise TTSError("Piper selesai namun file output audio kosong.")

        return output_path
