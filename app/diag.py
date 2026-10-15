"""Diagnostik: cek token, akun, dan device Spotify Connect yang terlihat.

Jalankan setelah login:
  docker compose run --rm bot python -m app.diag
"""
from __future__ import annotations

import json
import logging

from .config import load_settings
from .spotify_client import SpotifyClient, SpotifyError

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("diag")


def main() -> None:
    settings = load_settings()
    sp = SpotifyClient(settings)
    try:
        sp.load_token()
    except SpotifyError as e:
        raise SystemExit(f"Token belum ada / rusak: {e}\nJalankan login dulu.")

    log.info("=== AKUN ===")
    try:
        me = sp._json_or_error(sp._request("GET", "/me"))
        log.info("Nama    : %s", me.get("display_name"))
        log.info("ID      : %s", me.get("id"))
        log.info("Produk  : %s  (WAJIB 'premium' untuk kontrol playback)", me.get("product"))
        log.info("Negara  : %s", me.get("country"))
        if not me.get("product"):
            log.warning(
                "Field 'product' KOSONG. Ini biasanya karena token lama belum "
                "punya scope user-read-private. Login ULANG:\n"
                "    docker compose run --rm bot python -m app.auth --manual"
            )
        elif me.get("product") != "premium":
            log.warning(
                "Akun ini BUKAN Premium (product=%r). Kontrol playback Spotify "
                "akan gagal 403. Queue lokal tetap jalan.",
                me.get("product"),
            )
        log.info("RAW /me : %s", json.dumps(me)[:500])
    except SpotifyError as e:
        log.warning("Gagal ambil /me: %s", e)

    log.info("\n=== DEVICE SPOTIFY CONNECT ===")
    try:
        devices = sp.get_devices()
    except SpotifyError as e:
        raise SystemExit(f"Gagal ambil devices: {e}")

    if not devices:
        log.warning("TIDAK ADA device terlihat.")
        log.warning(
            "Buka app Spotify di HP Android & logout-login kalau perlu, "
            "lalu jalankan ulang diagnostik ini."
        )
    else:
        for d in devices:
            log.info(
                "  - %-25s id=%s aktif=%s tipe=%s volume=%s%%",
                d.get("name"),
                d.get("id"),
                d.get("is_active"),
                d.get("type"),
                d.get("volume_percent"),
            )

    log.info("\n=== TARGET DARI .env ===")
    log.info("DEVICE_NAME = %r", settings.device_name)
    found = sp.find_device_by_name(settings.device_name)
    if found:
        log.info("COCOK! Device '%s' ketemu (id=%s).", found.get("name"), found.get("id"))
    else:
        log.warning(
            "Tidak ada device yang cocok dengan %r. Sesuaikan DEVICE_NAME "
            "dengan nama persis di app Spotify HP, atau buka Spotify di HP.",
            settings.device_name,
        )


if __name__ == "__main__":
    main()
