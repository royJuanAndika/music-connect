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
    duration_sec: int = 0

    @property
    def elapsed_sec(self) -> int:
        if not self.is_running or self.started_at == 0:
            return 0
        return max(0, int(time.time() - self.started_at))

    @property
    def remaining_sec(self) -> int:
        if not self.is_running or self.duration_sec <= 0:
            return 0
        rem = self.duration_sec - self.elapsed_sec
        return max(0, rem)


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
        PENTING: [1:a]apad memastikan sidechain tidak memutus stream saat suara host habis,
        sehingga lagu tetap diputar penuh sampai durasi musik selesai.
        Gunakan asplit=2 agar output stream bisa dipakai bersama oleh HLS dan RTMP.
        """
        level = self.settings.duck_level
        attack = self.settings.duck_attack_ms
        release = self.settings.duck_release_ms

        filter_str = (
            f"[1:a]apad[pad_voice];"
            f"[0:a][pad_voice]sidechaincompress="
            f"threshold={level}:ratio=16:attack={attack}:release={release}[ducked];"
            f"[1:a]volume=1.8[v_boost];"
            f"[ducked][v_boost]amix=inputs=2:duration=first:normalize=0:dropout_transition=0,asplit=2[out_hls][out_rtmp]"
        )
        return filter_str

    def build_message_cmd(
        self,
        voice_file: Path,
        bed_file: Optional[Path] = None,
        output_hls: bool = True,
        output_rtmp: bool = False,
    ) -> list[str]:
        """Menyusun argumen FFmpeg untuk memutar pesan suara host dengan musik latar (Radio Bed) melirih."""
        cmd = [self.bin_path, "-y", "-re"]

        # Input 0: Radio Bed (file atau synthesizer halus jika file tidak ada)
        if bed_file and bed_file.is_file():
            cmd.extend(["-stream_loop", "-1", "-i", str(bed_file)])
        else:
            # Nada latar ambient sintetis harmonik (A3 + E4) yang santai
            cmd.extend([
                "-f", "lavfi",
                "-i", f"sine=frequency=220:sample_rate={self.settings.stream_sample_rate},"
                      f"volume=0.15[b1];sine=frequency=330:sample_rate={self.settings.stream_sample_rate},"
                      f"volume=0.10[b2];[b1][b2]amix=inputs=2",
            ])

        # Input 1: Voice host
        cmd.extend(["-i", str(voice_file)])

        # Ducking filter: volume radio bed ditekan ke 0.15 saat host bicara
        level = 0.15
        attack = 150
        release = 600
        filter_complex = [
            f"[0:a][1:a]sidechaincompress=threshold={level}:ratio=16:attack={attack}:release={release}[ducked];"
            f"[1:a]volume=1.8[v_boost];"
            f"[ducked][v_boost]amix=inputs=2:duration=second:normalize=0:dropout_transition=0,asplit=2[out_hls][out_rtmp]"
        ]
        cmd.extend(["-filter_complex", ";".join(filter_complex)])
        audio_map_hls = "[out_hls]"
        audio_map_rtmp = "[out_rtmp]"

        # Input 2: Dummy video track untuk RTMPS Telegram
        if output_rtmp and self.settings.rtmp_url:
            cmd.extend(["-f", "lavfi", "-re", "-i", "color=c=black:s=640x360:r=15"])

        # Output HLS
        if output_hls:
            hls_dir = self.settings.hls_dir
            hls_dir.mkdir(parents=True, exist_ok=True)
            cmd.extend([
                "-map", audio_map_hls,
                "-c:a", "aac",
                "-b:a", self.settings.stream_bitrate,
                "-ar", str(self.settings.stream_sample_rate),
                "-ac", str(self.settings.stream_channels),
                "-f", "hls",
                "-hls_time", str(self.settings.hls_segment_seconds),
                "-hls_list_size", "5",
                "-hls_flags", "delete_segments+append_list",
                "-hls_segment_filename", str(hls_dir / "segment_%03d.ts"),
                str(hls_dir / "live.m3u8"),
            ])

        # Output RTMP
        if output_rtmp and self.settings.rtmp_url:
            full_rtmp = self.settings.rtmp_url
            if self.settings.rtmp_key:
                full_rtmp = f"{self.settings.rtmp_url.rstrip('/')}/{self.settings.rtmp_key}"

            cmd.extend([
                "-map", "2:v",
                "-map", audio_map_rtmp,
                "-fps_mode", "cfr",
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-tune", "zerolatency",
                "-b:v", "200k",
                "-maxrate", "250k",
                "-bufsize", "500k",
                "-pix_fmt", "yuv420p",
                "-g", "30",
                "-keyint_min", "30",
                "-sc_threshold", "0",
                "-c:a", "aac",
                "-b:a", self.settings.stream_bitrate,
                "-ar", str(self.settings.stream_sample_rate),
                "-ac", str(self.settings.stream_channels),
                "-max_muxing_queue_size", "9999",
                "-f", "flv",
                full_rtmp,
            ])

        return cmd

    def play_message_sync(
        self,
        voice_file: Path,
        shoutout_to: str = "",
        message: str = "",
    ) -> None:
        """Memutar pengumuman pesan suara khusus dengan latar musik lirih (blocking)."""
        output_hls = self.settings.stream_mode in ("hls", "both")
        output_rtmp = (
            self.settings.stream_mode in ("rtmp", "both")
            and bool(self.settings.rtmp_url)
        )

        bed_file = self.settings.data_dir / "radio_bed.mp3"
        cmd = self.build_message_cmd(
            voice_file=voice_file,
            bed_file=bed_file if bed_file.is_file() else None,
            output_hls=output_hls,
            output_rtmp=output_rtmp,
        )

        self.state.is_running = True
        self.state.current_title = "📢 Pengumuman Radio"
        self.state.current_artist = f"Untuk: {shoutout_to}" if shoutout_to else "Pesan Siaran"
        self.state.current_shoutout = message
        self.state.is_host_speaking = True
        self.state.started_at = time.time()
        self.state.duration_sec = 0

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            self._process.communicate()
        finally:
            self._process = None
            self.state.is_running = False
            self.state.is_host_speaking = False

    def build_ffmpeg_cmd(
        self,
        music_file: Path,
        voice_file: Optional[Path] = None,
        output_hls: bool = True,
        output_rtmp: bool = False,
    ) -> list[str]:
        """Menyusun argumen baris perintah FFmpeg untuk mencampur audio dan menyiarkan."""
        # Input 0: musik
        cmd = [self.bin_path, "-y", "-re", "-i", str(music_file)]

        audio_map_hls = "0:a"
        audio_map_rtmp = "0:a"
        filter_complex = []

        # Input 1: Voice host jika ada
        has_voice = bool(voice_file and Path(voice_file).is_file())
        if has_voice:
            cmd.extend(["-i", str(voice_file)])
            filter_complex.append(self.build_ducking_filter())
            audio_map_hls = "[out_hls]"
            audio_map_rtmp = "[out_rtmp]"

        # Input video untuk Telegram RTMP (Input 2 jika ada voice, Input 1 jika tanpa voice)
        video_input_idx = 2 if has_voice else 1
        if output_rtmp and self.settings.rtmp_url:
            cmd.extend(["-f", "lavfi", "-re", "-i", "color=c=black:s=640x360:r=15"])

        if filter_complex:
            cmd.extend(["-filter_complex", ";".join(filter_complex)])

        # Output HLS (audio only)
        if output_hls:
            hls_dir = self.settings.hls_dir
            hls_dir.mkdir(parents=True, exist_ok=True)
            playlist_path = hls_dir / "live.m3u8"
            segment_path = hls_dir / "segment_%03d.ts"

            cmd.extend([
                "-map", audio_map_hls,
                "-c:a", "aac",
                "-b:a", self.settings.stream_bitrate,
                "-ar", str(self.settings.stream_sample_rate),
                "-ac", str(self.settings.stream_channels),
                "-f", "hls",
                "-hls_time", str(self.settings.hls_segment_seconds),
                "-hls_list_size", "5",
                "-hls_flags", "delete_segments+append_list",
                "-hls_segment_filename", str(segment_path),
                str(playlist_path),
            ])

        # Output RTMP (video dummy + audio)
        if output_rtmp and self.settings.rtmp_url:
            full_rtmp = self.settings.rtmp_url
            if self.settings.rtmp_key:
                full_rtmp = f"{self.settings.rtmp_url.rstrip('/')}/{self.settings.rtmp_key}"

            cmd.extend([
                "-map", f"{video_input_idx}:v",
                "-map", audio_map_rtmp,
                "-fps_mode", "cfr",
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-tune", "zerolatency",
                "-b:v", "200k",
                "-maxrate", "250k",
                "-bufsize", "500k",
                "-pix_fmt", "yuv420p",
                "-g", "30",
                "-keyint_min", "30",
                "-sc_threshold", "0",
                "-c:a", "aac",
                "-b:a", self.settings.stream_bitrate,
                "-ar", str(self.settings.stream_sample_rate),
                "-ac", str(self.settings.stream_channels),
                "-max_muxing_queue_size", "9999",
                "-f", "flv",
                full_rtmp,
            ])

        return cmd

    def play_track_sync(
        self,
        music_file: Path,
        voice_file: Optional[Path] = None,
        title: str = "Unknown",
        artist: str = "Unknown",
        shoutout: str = "",
        duration_sec: int = 0,
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
        self.state.duration_sec = duration_sec
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
                err_str = stderr.decode(errors="ignore")[-300:] if stderr else ""
                log.warning(f"FFmpeg berhenti dengan exit code {self._process.returncode}: {err_str}")
                # Jika RTMP gagal (misal RTMPS Telegram putus/key kadaluarsa), coba putar ulang HLS saja agar web tetap hidup
                if output_rtmp and "rtmp" in err_str.lower():
                    log.warning("Koneksi RTMP Telegram ditolak/terputus, melanjutkan pemutaran di Web HLS saja...")
                    fallback_cmd = self.build_ffmpeg_cmd(
                        music_file,
                        voice_file,
                        output_hls=True,
                        output_rtmp=False,
                    )
                    self._process = subprocess.Popen(fallback_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                    self._process.communicate()
        finally:
            self._process = None
            self.state.is_running = False
            self.state.is_host_speaking = False

    def build_standby_cmd(
        self,
        duration_sec: int = 10,
        output_hls: bool = True,
        output_rtmp: bool = False,
    ) -> list[str]:
        """Perintah FFmpeg untuk memutar silence/standby tone agar koneksi stream tidak mati saat antrian kosong."""
        cmd = [
            self.bin_path, "-y", "-re",
            "-f", "lavfi", "-t", str(duration_sec),
            "-i", f"anullsrc=r={self.settings.stream_sample_rate}:cl=stereo",
        ]

        # Output HLS
        if output_hls:
            hls_dir = self.settings.hls_dir
            hls_dir.mkdir(parents=True, exist_ok=True)
            cmd.extend([
                "-map", "0:a",
                "-c:a", "aac",
                "-b:a", self.settings.stream_bitrate,
                "-f", "hls",
                "-hls_time", str(self.settings.hls_segment_seconds),
                "-hls_list_size", "5",
                "-hls_flags", "delete_segments+append_list",
                "-hls_segment_filename", str(hls_dir / "segment_%03d.ts"),
                str(hls_dir / "live.m3u8"),
            ])

        # Output RTMP
        if output_rtmp and self.settings.rtmp_url:
            full_rtmp = self.settings.rtmp_url
            if self.settings.rtmp_key:
                full_rtmp = f"{self.settings.rtmp_url.rstrip('/')}/{self.settings.rtmp_key}"

            cmd.extend([
                "-f", "lavfi", "-t", str(duration_sec), "-i", "color=c=black:s=640x360:r=15",
                "-map", "1:v",
                "-map", "0:a",
                "-fps_mode", "cfr",
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-tune", "zerolatency",
                "-b:v", "150k",
                "-pix_fmt", "yuv420p",
                "-g", "30",
                "-keyint_min", "30",
                "-c:a", "aac",
                "-b:a", self.settings.stream_bitrate,
                "-max_muxing_queue_size", "9999",
                "-f", "flv",
                full_rtmp,
            ])

        return cmd

    def stop(self) -> None:
        """Hentikan siaran yang sedang berjalan."""
        if self._process:
            try:
                self._process.terminate()
            except Exception:
                pass
            self._process = None
        self.state.is_running = False

    def play_standby_sync(self, duration_sec: int = 10) -> None:
        """Memutar segmen standby agar stream RTMPS tidak terputus."""
        output_hls = self.settings.stream_mode in ("hls", "both")
        output_rtmp = (
            self.settings.stream_mode in ("rtmp", "both")
            and bool(self.settings.rtmp_url)
        )
        cmd = self.build_standby_cmd(duration_sec, output_hls, output_rtmp)
        self.state.is_running = True
        self.state.current_title = "Radio Standby"
        self.state.current_artist = "Menunggu Request..."
        self.state.current_shoutout = ""
        self.state.duration_sec = duration_sec
        self.state.started_at = time.time()

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            self._process.communicate()
        finally:
            self._process = None
            self.state.is_running = False
