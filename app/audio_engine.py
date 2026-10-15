"""Engine audio & penyiaran berkelanjutan menggunakan subproses FFmpeg."""
from __future__ import annotations

import asyncio
import logging
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .binary_resolver import resolve_binary
from .config import Settings

log = logging.getLogger("audio_engine")


@dataclass
class BroadcastState:
    is_running: bool = False
    current_title: str = "Stasiun Radio AI"
    current_artist: str = "Live Stream"
    is_host_speaking: bool = False
    current_shoutout: str = ""
    started_at: float = 0.0


class AudioEngineError(Exception):
    """Kesalahan pada broadcast engine FFmpeg."""
    pass


class AudioEngine:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        info = resolve_binary("ffmpeg", settings.ffmpeg_path)
        self.bin_path = str(info.path) if info.is_available and info.path else "ffmpeg"
        self.state = BroadcastState()
        self._process: Optional[subprocess.Popen] = None

    def is_available(self) -> bool:
        info = resolve_binary("ffmpeg", self.settings.ffmpeg_path)
        return info.is_available

    def build_ducking_filter(self) -> str:
        """Filter graph FFmpeg untuk dynamic sidechain compression (ducking).
        
        [0:a] adalah musik, [1:a] adalah suara host.
        Ketika suara host masuk, musik ditekan otomatis ke level ducking.
        """
        level = self.settings.duck_level
        attack = self.settings.duck_attack_ms
        release = self.settings.duck_release_ms

        # sidechaincompress: threshold=0.125, ratio=4, attack, release
        filter_str = (
            f"[0:a][1:a]sidechaincompress="
            f"threshold={level}:ratio=6:attack={attack}:release={release}[ducked];"
            f"[ducked][1:a]amix=inputs=2:duration=first:dropout_transition=2[out]"
        )
        return filter_str

    def build_ffmpeg_cmd(
        self,
        music_file: Path,
        voice_file: Optional[Path] = None,
        output_hls: bool = True,
        output_rtmp: bool = False,
    ) -> list[str]:
        """Menyusun argumen baris perintah FFmpeg untuk mencampur audio dan menyiarkan."""
        cmd = [self.bin_path, "-y", "-re"]

        # Input 0: Musik
        cmd.extend(["-i", str(music_file)])

        if voice_file and voice_file.is_file():
            # Input 1: Voice host
            cmd.extend(["-i", str(voice_file)])
            cmd.extend(["-filter_complex", self.build_ducking_filter(), "-map", "[out]"])
        else:
            # Tanpa host: map langsung musik input 0
            cmd.extend(["-map", "0:a"])

        # Audio encoder settings
        cmd.extend([
            "-c:a", "aac",
            "-b:a", self.settings.stream_bitrate,
            "-ar", str(self.settings.stream_sample_rate),
            "-ac", str(self.settings.stream_channels),
        ])

        # Output HLS
        if output_hls:
            hls_dir = self.settings.hls_dir
            hls_dir.mkdir(parents=True, exist_ok=True)
            playlist_path = hls_dir / "live.m3u8"
            segment_path = hls_dir / "segment_%03d.ts"

            cmd.extend([
                "-f", "hls",
                "-hls_time", str(self.settings.hls_segment_seconds),
                "-hls_list_size", "5",
                "-hls_flags", "delete_segments+append_list",
                "-hls_segment_filename", str(segment_path),
                str(playlist_path),
            ])

        # Output RTMP opsional (Telegram Live)
        if output_rtmp and self.settings.rtmp_url:
            full_rtmp = self.settings.rtmp_url
            if self.settings.rtmp_key:
                full_rtmp = f"{self.settings.rtmp_url.rstrip('/')}/{self.settings.rtmp_key}"
            cmd.extend(["-f", "flv", full_rtmp])

        return cmd

    def play_track_sync(
        self,
        music_file: Path,
        voice_file: Optional[Path] = None,
        title: str = "Unknown",
        artist: str = "Unknown",
        shoutout: str = "",
    ) -> None:
        """Memutar satu segmen lagu (blocking subproses sampai lagu selesai)."""
        output_hls = self.settings.stream_mode in ("hls", "both")
        output_rtmp = (
            self.settings.stream_mode in ("rtmp", "both")
            and bool(self.settings.rtmp_url)
        )

        cmd = self.build_ffmpeg_cmd(
            music_file,
            voice_file,
            output_hls=output_hls,
            output_rtmp=output_rtmp,
        )

        self.state.is_running = True
        self.state.current_title = title
        self.state.current_artist = artist
        self.state.current_shoutout = shoutout
        self.state.is_host_speaking = bool(voice_file and voice_file.is_file())
        self.state.started_at = time.time()

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            _, stderr = self._process.communicate()
            if self._process.returncode != 0 and self._process.returncode != -15:
                err_str = stderr.decode(errors="ignore")[-200:] if stderr else ""
                log.warning(f"FFmpeg berhenti dengan exit code {self._process.returncode}: {err_str}")
        finally:
            self._process = None
            self.state.is_running = False
            self.state.is_host_speaking = False

    def stop(self) -> None:
        """Hentikan siaran yang sedang berjalan."""
        if self._process:
            try:
                self._process.terminate()
            except Exception:
                pass
            self._process = None
        self.state.is_running = False
