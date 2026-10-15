"""Pemeriksaan ketersediaan binary portable dan sistem (ffmpeg, yt-dlp, piper)."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import NamedTuple


class BinaryInfo(NamedTuple):
    name: str
    path: Path | None
    is_available: bool
    source: str  # "configured", "bin_dir", "path", atau "missing"
    version_info: str = ""


def resolve_binary(binary_name: str, configured_path: str | Path | None = None) -> BinaryInfo:
    """Cari binary berdasarkan path konfigurasi, folder bin/ lokal, lalu PATH sistem."""
    name_no_ext = Path(binary_name).stem.lower()

    # 1. Cek path yang dikonfigurasi langsung
    if configured_path:
        p = Path(configured_path)
        if p.is_file():
            ver = _get_version(p)
            return BinaryInfo(name=name_no_ext, path=p, is_available=True, source="configured", version_info=ver)

    # 2. Cek di folder bin/ lokal proyek
    candidate_names = [f"{name_no_ext}.exe", name_no_ext] if os.name == "nt" else [name_no_ext]
    bin_dir = Path("bin")
    for c in candidate_names:
        p = bin_dir / c
        if p.is_file():
            ver = _get_version(p)
            return BinaryInfo(name=name_no_ext, path=p, is_available=True, source="bin_dir", version_info=ver)

    # 3. Cek di PATH sistem
    system_path = shutil.which(name_no_ext)
    if system_path:
        p = Path(system_path)
        ver = _get_version(p)
        return BinaryInfo(name=name_no_ext, path=p, is_available=True, source="path", version_info=ver)

    return BinaryInfo(name=name_no_ext, path=None, is_available=False, source="missing", version_info="")


def _get_version(exe_path: Path) -> str:
    """Ambil ringkasan versi satu baris dari binary."""
    try:
        res = subprocess.run(
            [str(exe_path), "--version"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if res.returncode == 0 and res.stdout:
            return res.stdout.strip().splitlines()[0]
    except Exception:
        pass
    return ""


def check_runtime_binaries(
    ffmpeg_path: str = "bin/ffmpeg.exe",
    ytdlp_path: str = "bin/yt-dlp.exe",
    piper_path: str = "bin/piper.exe",
) -> dict[str, BinaryInfo]:
    """Diagnosa semua binary yang dibutuhkan untuk siaran radio."""
    return {
        "ffmpeg": resolve_binary("ffmpeg", ffmpeg_path),
        "yt-dlp": resolve_binary("yt-dlp", ytdlp_path),
        "piper": resolve_binary("piper", piper_path),
    }


if __name__ == "__main__":
    diag = check_runtime_binaries()
    print("=== Diagnostic Binary Runtime ===")
    for k, v in diag.items():
        status = f"FOUND ({v.source}) -> {v.path}" if v.is_available else "MISSING"
        ver = f" [{v.version_info}]" if v.version_info else ""
        print(f"- {k:8}: {status}{ver}")
