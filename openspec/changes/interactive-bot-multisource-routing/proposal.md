# Proposal: Interactive Telegram Bot & Flexible Multi-Source Routing

## Why

Saat ini command Telegram `/search` dan `/queue` masih hardcoded memanggil client Spotify lama tanpa mengecek `MUSIC_SOURCE` di `.env`. Akibatnya, saat `MUSIC_SOURCE=youtube`, user mendapati pesan error `"Gagal search: Tidak ada refresh token. Login ulang dengan app.auth"`. Selain itu, antarmuka Telegram bot saat ini masih berbasis teks perintah konvensional dan belum memanfaatkan fitur interaktif Telegram (Inline Keyboard Buttons) untuk memilih lagu, mengontrol siaran secara instan (skip/refresh), maupun mengelola prioritas antrian secara visual.

Perubahan ini diperlukan agar sistem fleksibel dan taat konfigurasi (`MUSIC_SOURCE=youtube` atau `MUSIC_SOURCE=spotify`), serta menghadirkan pengalaman pengguna bot Telegram yang interaktif, modern, dan mudah digunakan langsung lewat tombol.

## What Changes

- **Pencarian Dinamis Sesuai `MUSIC_SOURCE`:**
  - Bila `MUSIC_SOURCE=youtube`: pencarian `/search` dan `/queue` diarahkan ke `YouTubeDownloader` (`yt-dlp`).
  - Bila `MUSIC_SOURCE=spotify`: pencarian tetap diarahkan ke Spotify Web API client lama.
- **Pencarian Multi-Track YouTube:** Menambah kemampuan `YouTubeDownloader` untuk mengekstrak beberapa hasil teratas sekaligus (`ytsearch5:`).
- **Interaksi Tombol Inline Telegram (`InlineKeyboardMarkup`):**
  - **Hasil Search:** Menampilkan pilihan lagu dalam bentuk tombol klik `[1. Judul]`, `[2. Judul]`. Klik tombol langsung memasukkan lagu ke antrian.
  - **Status `/now`:** Menambahkan tombol cepat `[ ⏭ Skip ]`, `[ 📜 Antrian ]`, `[ ⚡ Dahulukan ]`, dan `[ 🔄 Refresh ]` yang memperbarui pesan tanpa spam baris baru.
  - **Daftar Antrian `/list`:** Menampilkan tombol pintas untuk mendahulukan lagu (`bump`) atau menghapus lagu.
- **Callback Query Handler Telegram:** Menangani event tombol inline (`queue:<id>`, `skip`, `bump:<id>`, `refresh_now`).

### Yang Dipertahankan (re-use)
- Seluruh pipeline streaming `audio_engine.py` (FFmpeg, ducking, HLS/RTMP).
- Model data `queue_store.py` (kuota, moderasi kata terlarang, bump priority).
- Pengaturan konfigurasi `.env` dan `config.py`.

### Yang Diubah (refactor)
- `app/handlers.py`: Perbaikan routing `cmd_search` & `cmd_queue` agar fleksibel sesuai `MUSIC_SOURCE`, penambahan handler inline callback.
- `app/downloader.py`: Penambahan fungsi pencarian multi-track YouTube.
- `app/main.py`: Registrasi `CallbackQueryHandler`.

## Capabilities

### New Capabilities
- `interactive-telegram-bot`: Antarmuka bot Telegram interaktif berbasis Inline Keyboard Buttons untuk pencarian, kontrol pemutaran cepat, dan manajemen antrian.
- `flexible-source-routing`: Resolusi dan pencarian lagu dinamis (YouTube vs Spotify) yang sepenuhnya dikendalikan oleh konfigurasi `MUSIC_SOURCE`.

### Modified Capabilities
- (Tidak ada) — Belum ada spesifikasi tersimpan di `openspec/specs/`.

## Impact

- **Kode yang terpengaruh:** `app/downloader.py`, `app/handlers.py`, `app/main.py`.
- **Dependensi eksternal:** Tidak ada dependensi baru (menggunakan fitur bawaan `python-telegram-bot` yang sudah terpasang).
- **Pengguna:** Interaksi lebih nyaman dan tidak ada lagi error ketergantungan token Spotify saat menggunakan mode siaran YouTube.

## Non-goals

- **Bukan** perombakan arsitektur audio atau format HLS/RTMP.
- **Bukan** pemaksaan login Spotify jika user hanya ingin mode YouTube.
- **Bukan** integrasi source musik baru di luar YouTube dan Spotify.
