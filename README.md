# Radio Stream AI (Live Broadcast & AI Host)

Aplikasi stasiun radio streaming live interaktif bertenaga AI. Sistem ini menyiarkan aliran audio sinkron ke browser (HLS) dan Telegram Live (RTMP), memutar lagu dari YouTube (`yt-dlp`), dan menghadirkan **AI Host** yang membacakan request serta titip salam pendengar dengan dynamic ducking.

---

## Fitur Utama

- 📻 **Live Broadcast Sinkron (HLS & RTMP):** Semua pendengar mendengar lagu yang sama di waktu yang sama via Web Player (`http://localhost:8000`) atau Telegram Channel Live.
- 🎵 **Sumber Musik Full YouTube:** Memutar audio langsung via URL YouTube atau teks pencarian bebas (misal: `"Sheila on 7 Dan"`). Berkas audio disimpan di cache lokal agar hemat kuota dan cepat.
- 🎙️ **AI Host (Penyiar Radio AI):** LLM menyusun naskah intro dan salam dalam Bahasa Indonesia santai, lalu Piper TTS merender suaranya secara lokal dan offline.
- 🎚️ **Dynamic Audio Ducking:** Musik otomatis mengecil saat Host AI berbicara dan kembali normal setelahnya (`sidechaincompress` FFmpeg).
- 💬 **Interaksi Pendengar Multi-Channel:** Pendengar bisa request lagu dan titip salam lewat form Web Player publik atau bot Telegram.
- 🛡️ **Moderasi & Kuota:** Mencegah spam dengan batas kuota antrian per pengguna, cooldown request, dan penyaring kata-kata terlarang (`BANNED_WORDS`).

---

## Panduan Pengguna (User Guide)

### 1. Cara Mendengarkan Radio
1. Buka browser dan akses alamat Web Player: `http://localhost:8000` (atau IP server Anda).
2. Tekan tombol **▶ Putar Radio**.
3. Di layar akan tampil judul lagu yang sedang diputar, artis, status penyiar AI, dan pesan salam yang sedang dibacakan.

### 2. Cara Mengirim Request & Titip Salam via Web
1. Pada halaman Web Player di bagian bawah, terdapat kartu **Request Lagu & Titip Salam**.
2. Masukkan:
   - **Nama Kamu:** Nama panggilan atau username.
   - **Judul Lagu / Link:** Bisa judul lagu biasa (mis. `Chrisye Kala Cinta Menggoda`) atau link video YouTube.
   - **Pesan Titip Salam (Opsional):** Pesan yang ingin dibacakan oleh Host AI di siaran radio.
3. Klik **Kirim Request**. Sistem akan menampilkan nomor urut antrian lagu Anda.

### 3. Cara Mengirim Request via Telegram Bot
Bila fitur Telegram aktif (`TELEGRAM_ENABLED=true`):
- `/request <judul lagu atau URL YouTube>` — Menambahkan lagu ke antrian siaran radio.
- `/salam <judul lagu> | <pesan titip salam>` — Menambahkan lagu sekaligus menitipkan salam ke Host AI. Contoh:
  ```text
  /salam Sheila on 7 Dan | Salam buat temen-temen divisi IT yang lagi lembur!
  ```
- `/now` — Melihat status siaran, lagu yang sedang diputar, dan status Host AI.
- `/list` — Melihat daftar antrian lagu berikutnya.
- `/remove <nomor>` — Menghapus lagu dari antrian (khusus admin/pengirim).
- `/ask <pesan>` — Mengobrol dengan asisten AI bot menggunakan bahasa natural (misal: `"Putar lagu Hindia dong dan titip salam buat Roy"`).

---

## Panduan Instalasi & Menjalankan (Deployment)

### Opsi 1: Menggunakan Docker Compose (Direkomendasikan)
Cara termudah karena semua dependensi sistem (`ffmpeg` dan `yt-dlp`) otomatis terpasang di container Linux:

1. Salin template environment:
   ```bash
   cp .env.example .env
   ```
2. Sesuaikan konfigurasi di `.env` (isi `OPENROUTER_API_KEY` untuk mengaktifkan AI Host, dan `TELEGRAM_BOT_TOKEN` jika memakai bot Telegram).
3. Jalankan container:
   ```bash
   docker compose up -d --build
   ```
4. Buka `http://localhost:8000` di peramban.

---

### Opsi 2: Menjalankan Langsung di Host Windows

1. Siapkan Python 3.12+ dan pasang library:
   ```powershell
   pip install -r requirements.txt yt-dlp
   ```
2. Unduh executable binary berikut dan letakkan di dalam folder `bin/`:
   - `bin/ffmpeg.exe`
   - `bin/yt-dlp.exe`
   - `bin/piper.exe` + model di `models/id_ID-news-medium.onnx`
3. Salin konfigurasi environment:
   ```powershell
   Copy-Item .env.example .env
   ```
4. Cek ketersediaan binary:
   ```powershell
   python -m app.binary_resolver
   ```
5. Jalankan aplikasi:
   ```powershell
   python -m app.main
   ```

---

## Konfigurasi Kunci (`.env`)

| Variabel | Default | Keterangan |
|---|---|---|
| `MUSIC_SOURCE` | `youtube` | Sumber audio (`youtube` untuk radio, `spotify` untuk legacy mode). |
| `STREAM_MODE` | `hls` | Format output siaran: `hls`, `rtmp`, atau `both`. |
| `WEB_PORT` | `8000` | Port HTTP untuk Web Player dan REST API. |
| `HOST_ENABLED` | `true` | Mengaktifkan/menonaktifkan AI Host. |
| `HOST_MODE` | `every_song` | Kapan host bicara: `every_song`, `interval`, atau `request_only`. |
| `DUCK_LEVEL` | `0.25` | Level volume musik saat host bicara (0.25 = 25%). |
| `OPENROUTER_API_KEY`| *(kosong)* | API key OpenRouter untuk naskah DJ radio. |
| `MAX_QUEUE_PER_USER`| `3` | Maksimal lagu aktif per pengguna dalam antrian. |
| `REQUEST_COOLDOWN_SEC`| `30` | Waktu tunggu antar-request dari user yang sama. |
| `BANNED_WORDS` | `judi,slot,porn` | Daftar kata terlarang yang ditolak sistem. |

---

## Dokumentasi Teknis Lanjutan

Untuk pengembang dan kontributor:
- [Arsitektur Sistem & Alur Audio](docs/ARCHITECTURE.md)
- [Panduan Pengembangan & Pengujian](docs/DEVELOPMENT.md)
