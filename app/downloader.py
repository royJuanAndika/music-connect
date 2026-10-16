"""Downloader audio YouTube & resolver metadata berbasis yt-dlp."""
from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .binary_resolver import resolve_binary
from .config import Settings

log = logging.getLogger("downloader")

_YT_URL_REGEX = re.compile(
    r"^(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/|music\.youtube\.com/watch\?v=)([\w-]{11})"
)


@dataclass(frozen=True)
class TrackMetadata:
    video_id: str
    title: str
    uploader: str
    duration_sec: int
    is_live: bool
    thumbnail_url: str
    webpage_url: str

    @property
    def formatted_title(self) -> str:
        """Format tampilan bersih Artis - Judul bila memungkinkan."""
        if " - " in self.title:
            return self.title
        if self.uploader and self.uploader.lower() not in self.title.lower():
            return f"{self.uploader} - {self.title}"
        return self.title


class DownloaderError(Exception):
    """Kesalahan umum terkait unduhan atau resolusi YouTube."""
    pass


class YouTubeDownloader:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        info = resolve_binary("yt-dlp", settings.ytdlp_path)
        self.bin_path = str(info.path) if info.is_available and info.path else "yt-dlp"

    def is_available(self) -> bool:
        info = resolve_binary("yt-dlp", self.settings.ytdlp_path)
        return info.is_available

    def _build_base_cmd(self) -> list[str]:
        cmd = [self.bin_path, "--no-warnings", "--no-check-certificates"]
        if self.settings.yt_cookies_file:
            cmd.extend(["--cookies", self.settings.yt_cookies_file])
        if self.settings.yt_proxy:
            cmd.extend(["--proxy", self.settings.yt_proxy])
        return cmd

    def search_multitracks(self, query: str, limit: int = 5) -> list[TrackMetadata]:
        """Cari beberapa hasil lagu teratas dari YouTube (ytsearchN:)."""
        clean_query = query.strip()
        if not clean_query:
            return []

        limit = max(1, min(limit, 10))
        target = f"ytsearch{limit}:{clean_query}"

        cmd = self._build_base_cmd() + [
            "--dump-json",
            "--default-search", "ytsearch",
            "--no-playlist",
            target,
        ]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=35)
            if res.returncode != 0:
                log.warning(f"ytsearch gagal: {res.stderr[:200] if res.stderr else ''}")
                return []
        except Exception as e:
            log.warning(f"Gagal menjalankan yt-dlp search: {e}")
            return []

        results: list[TrackMetadata] = []
        for line in res.stdout.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                meta = TrackMetadata(
                    video_id=data.get("id", ""),
                    title=data.get("title", "Unknown Title"),
                    uploader=data.get("uploader", data.get("channel", "Unknown")),
                    duration_sec=int(data.get("duration") or 0),
                    is_live=bool(data.get("is_live", False)),
                    thumbnail_url=data.get("thumbnail", ""),
                    webpage_url=data.get("webpage_url", f"https://www.youtube.com/watch?v={data.get('id', '')}"),
                )
                if not (self.settings.yt_block_live and meta.is_live):
                    results.append(meta)
            except Exception:
                continue

        return results

    def resolve_query(self, query: str) -> TrackMetadata:
        """Ekstraksi metadata dari URL langsung atau pencarian teks (ytsearch1:)."""
        clean_query = query.strip()
        if not clean_query:
            raise DownloaderError("Kueri pencarian atau URL kosong.")

        target = clean_query
        # Jika bukan URL youtube langsung, gunakan ytsearch1:
        if not _YT_URL_REGEX.match(clean_query):
            if not self.settings.yt_allow_text_search:
                raise DownloaderError("Pencarian teks dimatikan. Kirimkan link YouTube langsung.")
            target = f"ytsearch1:{clean_query}"

        cmd = self._build_base_cmd() + [
            "--dump-json",
            "--default-search", "ytsearch",
            "--no-playlist",
            target,
        ]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if res.returncode != 0:
                err_msg = res.stderr.strip().splitlines()[-1] if res.stderr else "Gagal mengambil info video."
                raise DownloaderError(f"yt-dlp gagal: {err_msg}")
        except FileNotFoundError:
            raise DownloaderError(f"Binary yt-dlp tidak ditemukan di path: {self.bin_path}")
        except subprocess.TimeoutExpired:
            raise DownloaderError("Resolusi metadata YouTube timeout.")

        raw_json = res.stdout.strip()
        if not raw_json:
            raise DownloaderError(f"Video tidak ditemukan untuk: {query}")

        first_line = raw_json.splitlines()[0]
        try:
            data = json.loads(first_line)
        except json.JSONDecodeError:
            raise DownloaderError("Gagal membaca metadata JSON dari yt-dlp.")

        meta = TrackMetadata(
            video_id=data.get("id", ""),
            title=data.get("title", "Unknown Title"),
            uploader=data.get("uploader", data.get("channel", "Unknown")),
            duration_sec=int(data.get("duration") or 0),
            is_live=bool(data.get("is_live", False)),
            thumbnail_url=data.get("thumbnail", ""),
            webpage_url=data.get("webpage_url", f"https://www.youtube.com/watch?v={data.get('id', '')}"),
        )

        self._validate_metadata(meta)
        return meta

    def _validate_metadata(self, meta: TrackMetadata) -> None:
        """Validasi batas durasi dan proteksi live stream."""
        if self.settings.yt_block_live and meta.is_live:
            raise DownloaderError("Siaran langsung (live stream) tidak diizinkan di radio.")

        if meta.duration_sec > self.settings.yt_max_duration_sec:
            max_m = self.settings.yt_max_duration_sec // 60
            dur_m = meta.duration_sec // 60
            raise DownloaderError(
                f"Durasi lagu terlalu panjang ({dur_m} menit). Maksimal adalah {max_m} menit."
            )

        if meta.duration_sec < self.settings.yt_min_duration_sec and meta.duration_sec > 0:
            raise DownloaderError(
                f"Durasi terlalu pendek ({meta.duration_sec} detik). Minimal adalah {self.settings.yt_min_duration_sec} detik."
            )

    def get_cached_file(self, video_id: str) -> Optional[Path]:
        """Cek apakah file audio untuk video_id sudah ada di cache lokal."""
        tracks_dir = self.settings.tracks_dir
        if not tracks_dir.is_dir():
            return None
        # Cari file dengan nama video_id.*
        for ext in ("opus", "m4a", "mp3", "webm", "ogg"):
            candidate = tracks_dir / f"{video_id}.{ext}"
            if candidate.is_file() and candidate.stat().st_size > 0:
                return candidate
        return None

    def download_audio(self, meta: TrackMetadata) -> Path:
        """Unduh audio track ke cache lokal jika belum ada."""
        cached = self.get_cached_file(meta.video_id)
        if cached:
            log.info(f"Menggunakan cache lokal untuk video {meta.video_id}: {cached}")
            return cached

        self.settings.tracks_dir.mkdir(parents=True, exist_ok=True)
        fmt = self.settings.yt_audio_format
        output_template = str(self.settings.tracks_dir / f"{meta.video_id}.%(ext)s")

        cmd = self._build_base_cmd() + [
            "-x",  # extract audio
            "--audio-format", fmt,
            "--audio-quality", str(self.settings.yt_audio_bitrate),
            "--no-playlist",
            "-o", output_template,
            meta.webpage_url,
        ]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            if res.returncode != 0:
                err_msg = res.stderr.strip().splitlines()[-1] if res.stderr else "Gagal mengunduh audio."
                raise DownloaderError(f"yt-dlp download gagal: {err_msg}")
        except FileNotFoundError:
            raise DownloaderError(f"Binary yt-dlp tidak ditemukan: {self.bin_path}")
        except subprocess.TimeoutExpired:
            raise DownloaderError("Pengunduhan audio YouTube timeout.")

        saved = self.get_cached_file(meta.video_id)
        if not saved:
            raise DownloaderError("Unduhan selesai namun berkas audio tidak ditemukan di direktori cache.")
        return saved
