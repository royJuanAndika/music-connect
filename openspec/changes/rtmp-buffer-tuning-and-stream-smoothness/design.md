# Design: RTMP Buffer Tuning & Telegram Stream Smoothness

## Context

Lihat `proposal.md` untuk motivasi. Di aplikasi Telegram klien (HP Android/iOS), decoder video menuntut clock frame yang konsisten minimal 15 fps untuk mempertahankan sinkronisasi audio-video. Framerate 5 fps yang digunakan sebelumnya menyebabkan decoder di HP melakukan buffering berulang untuk menunggu frame berikutnya.

## Goals / Non-Goals

**Goals:**
- Mengatur framerate video kanvas hitam ke 15 fps dengan keyframe tepat 2 detik (`-g 30 -keyint_min 30`).
- Mengunci bitrate video ke 100 kbps dengan `-maxrate 100k -bufsize 200k` agar transmisi stabil tanpa burst.
- Menjaga CPU VPS tetap sangat rendah (< 10%).

**Non-Goals:**
- Tidak mengubah resolusi dari 320x240 (resolusi ini sudah ideal untuk menghemat CPU dan bandwidth).

## Decisions

### 1. Framerate 15 FPS & GOP 30
- Pada 5 fps, jeda antar frame adalah 200 ms. Telegram menganggap ini sebagai kondisi lag/frame drop.
- Pada 15 fps, jeda antar frame adalah ~66 ms, memenuhi batas clock minimum decoder video Telegram.
- Karena frame berupa kanvas hitam polos (`color=c=black`), encoding 15 fps di CPU hanya memakan sedikit siklus CPU ekstra (~1-2% di VPS).

### 2. Pemasangan Buffer Ceiling
- Menambahkan `-maxrate 100k -bufsize 200k` berdampingan dengan `-b:v 100k`.
- Mencegah encoder x264 mengirimkan paket burst yang bisa menyebabkan *packet drop* di server ingest Telegram.

## Risks / Trade-offs

- **Bandwidth:** Konsumsi bandwidth video naik dari ~4 KB/s menjadi ~12 KB/s (tetap sangat kecil dibandingkan bandwidth upload 1 Gbps VPS).
