"""Engine audio & penyiaran berkelanjutan menggunakan subproses FFmpeg."""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import threading
import time
from collections import deque
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
        self._alert_queue: deque[Path] = deque()
        self._alert_thread: Optional[threading.Thread] = None
        self._alert_running = False
        self._fifo_path = Path("/tmp/radio_alert.fifo") if os.name != "nt" else self.settings.data_dir / "radio_alert.fifo"

    def is_available(self) -> bool:
        info = resolve_binary("ffmpeg", self.settings.ffmpeg_path)
        return info.is_available

    def build_ducking_filter(self, output_hls: bool = True, output_rtmp: bool = False) -> tuple[str, str, str]:
        """Filter graph FFmpeg untuk dynamic sidechain compression (ducking).
        
        [0:a] adalah musik, [1:a] adalah suara host.
        PENTING: [1:a]apad memastikan sidechain tidak memutus stream saat suara host habis.
        Gunakan asplit HANYA jika output_hls dan output_rtmp aktif bersamaan.
        """
        level = self.settings.duck_level
        attack = self.settings.duck_attack_ms
        release = self.settings.duck_release_ms
        ratio = getattr(self.settings, "duck_ratio", 5.0)

        # Filter vokal host: buang gemuruh bass bawah dan perkuat vokal agar artikulasi jernih
        voice_prep = "[1:a]highpass=f=80,volume=1.6[v_clean]"

        # Limiter anti-clipping di ujung mix jika diaktifkan
        limiter = ",alimiter=limit=0.95:attack=5:release=50:asc=1" if getattr(self.settings, "audio_limiter_enabled", True) else ""

        # [1:a] input stream dipad untuk sidechain, [v_clean] hasil filter dimix ke output
        base = (
            f"[1:a]apad[pad_voice];"
            f"[0:a][pad_voice]sidechaincompress="
            f"threshold={level}:ratio={ratio}:attack={attack}:release={release}[ducked];"
            f"{voice_prep};"
            f"[ducked][v_clean]amix=inputs=2:duration=first:dropout_transition=0{limiter}"
        )

        if output_hls and output_rtmp:
            filter_str = f"{base},asplit=2[out_hls][out_rtmp]"
            return filter_str, "[out_hls]", "[out_rtmp]"
        elif output_rtmp:
            filter_str = f"{base}[out_rtmp]"
            return filter_str, "", "[out_rtmp]"
        else:
            filter_str = f"{base}[out_hls]"
            return filter_str, "[out_hls]", ""

    def _ensure_fifo(self) -> None:
        """Siapkan FIFO file di sistem operasi Unix untuk live stream mixing."""
        if os.name != "nt":
            try:
                if self._fifo_path.exists():
                    if not self._fifo_path.is_fifo():
                        self._fifo_path.unlink()
                        os.mkfifo(str(self._fifo_path))
                else:
                    os.mkfifo(str(self._fifo_path))
            except Exception as e:
                log.warning(f"Gagal inisialisasi FIFO {self._fifo_path}: {e}")

    def _start_alert_feeder(self) -> None:
        """Menjalankan thread pengumpan audio alert (silence generator + alert playback) ke FIFO."""
        if os.name == "nt":
            return
        self._ensure_fifo()
        self._alert_running = True
        self._alert_thread = threading.Thread(target=self._alert_feeder_worker, daemon=True)
        self._alert_thread.start()

    def _stop_alert_feeder(self) -> None:
        """Hentikan thread pengumpan alert."""
        self._alert_running = False

    def _alert_feeder_worker(self) -> None:
        """Worker thread yang terus menerus menyuapkan audio PCM 16-bit 44.1kHz Stereo ke FIFO."""
        sample_rate = self.settings.stream_sample_rate
        channels = self.settings.stream_channels
        bytes_per_sec = sample_rate * channels * 2
        chunk_size = bytes_per_sec // 10  # 100ms chunk
        silence_chunk = b"\x00" * chunk_size

        while self._alert_running:
            try:
                # Buka FIFO untuk penulisan (blocking sampai FFmpeg membuka reader)
                fifo_fd = os.open(str(self._fifo_path), os.O_WRONLY)
                with os.fdopen(fifo_fd, "wb") as fifo:
                    while self._alert_running:
                        # Cek apakah ada antrean file audio alert
                        if self._alert_queue:
                            alert_file = self._alert_queue.popleft()
                            if alert_file.is_file():
                                log.info(f"Mengalirkan file alert ke FIFO: {alert_file.name}")
                                self.state.is_host_speaking = True
                                decode_cmd = [
                                    self.bin_path, "-v", "error", "-y",
                                    "-i", str(alert_file),
                                    "-f", "s16le",
                                    "-ar", str(sample_rate),
                                    "-ac", str(channels),
                                    "-"
                                ]
                                try:
                                    dec_proc = subprocess.Popen(decode_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                                    while self._alert_running:
                                        raw_audio = dec_proc.stdout.read(chunk_size)
                                        if not raw_audio:
                                            break
                                        fifo.write(raw_audio)
                                        fifo.flush()
                                        time.sleep(0.09)
                                    dec_proc.wait(timeout=2)
                                except Exception as ex:
                                    log.warning(f"Error streaming alert file {alert_file.name}: {ex}")
                                finally:
                                    self.state.is_host_speaking = False
                                    try:
                                        alert_file.unlink(missing_ok=True)
                                    except Exception:
                                        pass
                                continue

                        # Kirim silence agar input FFmpeg tetap mengalir lancar
                        fifo.write(silence_chunk)
                        fifo.flush()
                        time.sleep(0.095)
            except (BrokenPipeError, OSError) as e:
                if self._alert_running:
                    # FFmpeg mungkin berganti track / restart, tunggu sebentar lalu reconnect ke FIFO
                    time.sleep(0.5)
            except Exception as e:
                if self._alert_running:
                    log.warning(f"Alert feeder loop terhenti: {e}")
                    time.sleep(1)

    def build_live_ducking_filter(self, output_hls: bool = True, output_rtmp: bool = False) -> tuple[str, str, str]:
        """Filter ducking interaktif untuk live alert mixing.
        
        [0:a] Musik dari file lagu.
        [1:a] Stream interaktif dari FIFO (silence biasa, bersuara saat alert masuk).
        """
        level = self.settings.duck_level
        attack = self.settings.duck_attack_ms
        release = self.settings.duck_release_ms
        ratio = getattr(self.settings, "duck_ratio", 5.0)
        limiter = ",alimiter=limit=0.95:attack=5:release=50:asc=1" if getattr(self.settings, "audio_limiter_enabled", True) else ""

        # Filter vokal alert
        voice_prep = "[1:a]highpass=f=80,volume=1.8[v_alert]"

        # Sidechain: jika ada suara di 1:a, volume 0:a otomatis tertekan
        base = (
            f"[0:a][1:a]sidechaincompress=threshold={level}:ratio={ratio}:attack={attack}:release={release}[ducked];"
            f"{voice_prep};"
            f"[ducked][v_alert]amix=inputs=2:duration=first:dropout_transition=0{limiter}"
        )

        if output_hls and output_rtmp:
            filter_str = f"{base},asplit=2[out_hls][out_rtmp]"
            return filter_str, "[out_hls]", "[out_rtmp]"
        elif output_rtmp:
            filter_str = f"{base}[out_rtmp]"
            return filter_str, "", "[out_rtmp]"
        else:
            filter_str = f"{base}[out_hls]"
            return filter_str, "[out_hls]", ""
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

        # Ducking filter: volume radio bed ditekan saat host bicara
        level = 0.05
        attack = 40
        release = 800
        ratio = getattr(self.settings, "duck_ratio", 5.0)
        limiter = ",alimiter=limit=0.95:attack=5:release=50:asc=1" if getattr(self.settings, "audio_limiter_enabled", True) else ""

        # Filter vokal pesan jernih dan hangat
        voice_prep = "[1:a]highpass=f=80,volume=1.8[v_clean]"

        # Amix duration=first pada v_clean agar panjang siaran mengikuti durasi suara pesan
        base_bed = (
            f"[0:a][1:a]sidechaincompress=threshold={level}:ratio={ratio}:attack={attack}:release={release}[ducked];"
            f"{voice_prep};"
            f"[v_clean][ducked]amix=inputs=2:duration=first:dropout_transition=0{limiter}"
        )

        filter_complex = []
        if output_hls and output_rtmp:
            filter_complex.append(f"{base_bed},asplit=2[out_hls][out_rtmp]")
            audio_map_hls = "[out_hls]"
            audio_map_rtmp = "[out_rtmp]"
        elif output_rtmp:
            filter_complex.append(f"{base_bed}[out_rtmp]")
            audio_map_hls = ""
            audio_map_rtmp = "[out_rtmp]"
        else:
            filter_complex.append(f"{base_bed}[out_hls]")
            audio_map_hls = "[out_hls]"
            audio_map_rtmp = ""

        cmd.extend(["-filter_complex", ";".join(filter_complex)])

        # Input video untuk Telegram RTMP
        res = self.settings.rtmp_video_resolution
        fps = self.settings.rtmp_video_fps
        v_bitrate = self.settings.rtmp_video_bitrate
        gop = fps * 2

        if output_rtmp and self.settings.rtmp_url:
            cmd.extend(["-f", "lavfi", "-re", "-i", f"color=c=black:s={res}:r={fps}"])

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
                "-shortest",
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
                "-b:v", v_bitrate,
                "-maxrate", v_bitrate,
                "-bufsize", "200k",
                "-pix_fmt", "yuv420p",
                "-g", str(gop),
                "-keyint_min", str(gop),
                "-sc_threshold", "0",
                "-c:a", "aac",
                "-b:a", self.settings.stream_bitrate,
                "-ar", str(self.settings.stream_sample_rate),
                "-ac", str(self.settings.stream_channels),
                "-shortest",
                "-flvflags", "no_duration_filesize",
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
            _, stderr = self._process.communicate()
            proc = self._process
            if proc and proc.returncode not in (0, -15, 255):
                err_str = stderr.decode(errors="ignore")[-250:] if stderr else ""
                log.warning(f"play_message_sync exit {proc.returncode}: {err_str}")
                # Fallback jika RTMP gagal, putar HLS saja
                if output_rtmp and "rtmp" in err_str.lower():
                    fallback_cmd = self.build_message_cmd(voice_file, bed_file if bed_file.is_file() else None, output_hls=True, output_rtmp=False)
                    self._process = subprocess.Popen(fallback_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                    self._process.communicate()
        except Exception as e:
            log.warning(f"Error pada play_message_sync: {e}")
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
        use_live_alert_fifo: bool = False,
    ) -> list[str]:
        """Menyusun argumen baris perintah FFmpeg untuk mencampur audio dan menyiarkan."""
        # Input 0: musik
        cmd = [self.bin_path, "-y", "-re", "-i", str(music_file)]

        audio_map_hls = "0:a"
        audio_map_rtmp = "0:a"
        filter_complex = []

        # Cek apakah menggunakan live alert FIFO (Opsi B: real-time in-song ducking)
        if use_live_alert_fifo and os.name != "nt" and self._fifo_path.is_fifo():
            sample_rate = self.settings.stream_sample_rate
            channels = self.settings.stream_channels
            cmd.extend([
                "-f", "s16le",
                "-ar", str(sample_rate),
                "-ac", str(channels),
                "-i", str(self._fifo_path),
            ])
            filt_str, map_hls, map_rtmp = self.build_live_ducking_filter(output_hls, output_rtmp)
            filter_complex.append(filt_str)
            audio_map_hls = map_hls
            audio_map_rtmp = map_rtmp
            video_input_idx = 2
        else:
            # Input 1: Voice host statis jika ada
            has_voice = bool(voice_file and Path(voice_file).is_file())
            if has_voice:
                cmd.extend(["-i", str(voice_file)])
                filt_str, map_hls, map_rtmp = self.build_ducking_filter(output_hls, output_rtmp)
                filter_complex.append(filt_str)
                audio_map_hls = map_hls
                audio_map_rtmp = map_rtmp
            video_input_idx = 2 if has_voice else 1
        res = self.settings.rtmp_video_resolution
        fps = self.settings.rtmp_video_fps
        v_bitrate = self.settings.rtmp_video_bitrate
        gop = fps * 2  # keyframe tepat 2 detik

        if output_rtmp and self.settings.rtmp_url:
            cmd.extend(["-f", "lavfi", "-re", "-i", f"color=c=black:s={res}:r={fps}"])

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
                "-b:v", v_bitrate,
                "-maxrate", v_bitrate,
                "-bufsize", "200k",
                "-pix_fmt", "yuv420p",
                "-g", str(gop),
                "-keyint_min", str(gop),
                "-sc_threshold", "0",
                "-c:a", "aac",
                "-b:a", self.settings.stream_bitrate,
                "-ar", str(self.settings.stream_sample_rate),
                "-ac", str(self.settings.stream_channels),
                "-flvflags", "no_duration_filesize",
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

        # Nyalakan alert feeder thread untuk live in-song mixing jika sistem operasi mendukung
        use_fifo = (os.name != "nt")
        if use_fifo:
            self._start_alert_feeder()

        cmd = self.build_ffmpeg_cmd(
            music_file,
            voice_file,
            output_hls=output_hls,
            output_rtmp=output_rtmp,
            use_live_alert_fifo=use_fifo,
        )

        self.state.is_running = True
        self.state.current_title = title
        self.state.current_artist = artist
        self.state.current_shoutout = shoutout
        self.state.duration_sec = duration_sec
        self.state.is_host_speaking = bool(voice_file and voice_file.is_file())
        self.state.started_at = time.time()

        retries = 2 if output_rtmp else 1
        for attempt in range(retries):
            try:
                self._process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )
                _, stderr = self._process.communicate()
                proc = self._process
                if proc and proc.returncode not in (0, -15, 255):
                    err_str = stderr.decode(errors="ignore")[-300:] if stderr else ""
                    log.warning(f"FFmpeg berhenti dengan exit code {proc.returncode}: {err_str}")
                    # Jika gagal instan (< 5 detik) saat mencoba RTMP, coba lagi sekali setelah jeda (tunggu socket Telegram rilis)
                    if output_rtmp and (time.time() - self.state.started_at) < 5 and attempt < retries - 1:
                        log.warning(f"Koneksi RTMP Telegram belum siap, mencoba lagi dalam 2 detik (attempt {attempt + 1}/{retries})...")
                        time.sleep(2)
                        continue
                    # Jika tetap gagal RTMP, putar HLS saja agar web tetap hidup
                    if output_rtmp and "rtmp" in err_str.lower():
                        log.warning("Koneksi RTMP Telegram ditolak/terputus, melanjutkan pemutaran di Web HLS saja...")
                        fallback_cmd = self.build_ffmpeg_cmd(
                            music_file,
                            voice_file,
                            output_hls=True,
                            output_rtmp=False,
                            use_live_alert_fifo=False,
                        )
                        self._process = subprocess.Popen(fallback_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                        self._process.communicate()
                break
            finally:
                self._stop_alert_feeder()
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
        res = self.settings.rtmp_video_resolution
        fps = self.settings.rtmp_video_fps
        v_bitrate = self.settings.rtmp_video_bitrate
        gop = fps * 2

        if output_rtmp and self.settings.rtmp_url:
            full_rtmp = self.settings.rtmp_url
            if self.settings.rtmp_key:
                full_rtmp = f"{self.settings.rtmp_url.rstrip('/')}/{self.settings.rtmp_key}"

            cmd.extend([
                "-f", "lavfi", "-t", str(duration_sec), "-i", f"color=c=black:s={res}:r={fps}",
                "-map", "1:v",
                "-map", "0:a",
                "-fps_mode", "cfr",
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-tune", "zerolatency",
                "-b:v", v_bitrate,
                "-maxrate", v_bitrate,
                "-bufsize", "200k",
                "-pix_fmt", "yuv420p",
                "-g", str(gop),
                "-keyint_min", str(gop),
                "-c:a", "aac",
                "-b:a", self.settings.stream_bitrate,
                "-flvflags", "no_duration_filesize",
                "-max_muxing_queue_size", "9999",
                "-f", "flv",
                full_rtmp,
            ])

        return cmd

    async def inject_live_alert(self, voice_file: Path) -> None:
        """Menyuntikkan file audio alert ke live stream secara asinkron."""
        log.info(f"Injeksi live alert: {voice_file.name}")
        # Tambahkan ke antrean feeder FIFO jika feeder aktif
        if self._alert_running:
            self._alert_queue.append(voice_file)
            # Tunggu durasi audio alert selesai dimainkan
            dur = 5.0
            try:
                size = voice_file.stat().st_size
                dur = max(3.0, min(30.0, size / 16000.0))
            except Exception:
                dur = 5.0
            await asyncio.sleep(dur)
        else:
            log.warning("Alert feeder tidak aktif (tidak ada lagu berjalan atau non-Unix).")

    def stop(self) -> None:
        """Hentikan siaran yang sedang berjalan secara sopan (graceful SIGTERM)."""
        proc = self._process
        if proc:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
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
            _, stderr = self._process.communicate()
            proc = self._process
            if proc and proc.returncode not in (0, -15, 255):
                err_str = stderr.decode(errors="ignore")[-200:] if stderr else ""
                log.warning(f"play_standby_sync exit {proc.returncode}: {err_str}")
                if output_rtmp and any(k in err_str.lower() for k in ("rtmp", "timed out", "connection refused", "input/output error")):
                    time.sleep(3)
        finally:
            self._process = None
            self.state.is_running = False
