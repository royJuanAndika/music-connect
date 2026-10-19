# Proposal: RTMP Buffer Tuning & Telegram Stream Smoothness

## Why

Siaran Telegram Live saat ini terkadang terdengar tersendat-sendat (micro-buffering/patah-patah) di aplikasi Telegram klien. Hal ini disebabkan oleh framerate video sintetis yang terlalu rendah (5 fps) yang membingungkan decoder video Telegram di HP (dianggap frame drop), serta ketiadaan parameter buffer ceiling konstan (`-maxrate` dan `-bufsize`) pada output RTMP.

Perubahan ini merancang optimalisasi parameter transmisi video dan audio FFmpeg agar sesuai dengan toleransi decoder klien Telegram: menaikkan framerate ke 15 fps dengan bitrate konstan (CBR) dan buffer limiter ketat, sehingga aliran audio berjalan mulus tanpa lag di perangkat pendengar.

## What Changes

- **Peningkatan Framerate Video Sintetis ke 15 FPS:**
  - Mengubah default `RTMP_VIDEO_FPS` dari 5 ke 15 fps (resolusi tetap 320x240 agar CPU VPS tetap sangat ringan <10%).
  - Mengatur interval keyframe `-g` dan `-keyint_min` ke `30` (tepat 2 detik pada 15 fps) sesuai rekomendasi ingest Telegram.
- **Penerapan Constant Bitrate (CBR) & Buffer Limiter:**
  - Mengunci parameter `-b:v 100k -maxrate 100k -bufsize 200k` untuk transmisi data yang konsisten dan stabil tiap milidetik.
- **Pembersihan Metadata FLV:**
  - Memastikan `-flvflags no_duration_filesize` aktif pada seluruh keluaran live RTMP guna mencegah lagging penulisan metadata stream tak terhingga.

### Yang Dipertahankan (re-use)
- Seluruh pipeline audio ducking, suara Gadis (`edge-tts`), dan integrasi bot Telegram.
- Jalur proxy Cloudflare WARP untuk pengunduhan YouTube.
- Otorisasi Admin dan antrian SQLite.

### Yang Diubah
- Default konfigurasi di `app/config.py` dan `.env.example`.
- Parameter builder FFmpeg di `app/audio_engine.py`.

## Capabilities

### New Capabilities
- `stream-smoothness`: Parameter transmisi RTMP yang dituning khusus untuk mencegah audio stuttering dan micro-buffering pada klien Telegram Live.

### Modified Capabilities
- (Tidak ada)

## Impact

- **Kode yang terpengaruh:** `app/audio_engine.py`, `app/config.py`, `.env.example`.
- **Pengguna:** Pendengar di Telegram Live mendengar lagu dan suara penyiar secara halus tanpa tersendat-sendat.

## Non-goals

- Tidak meningkatkan resolusi video ke HD (karena tujuan utama adalah siaran audio radio hemat kuota).
