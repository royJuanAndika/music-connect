# Tasks: Radio Stream AI

## 1. Scaffolding, Config & Binary Environment

- [x] 1.1 Buat direktori runtime `bin/`, `data/tracks/`, `data/voice/`, `data/hls/` dan update `.gitignore` agar folder data tidak ter-commit. Verifikasi dengan `git status`.
- [x] 1.2 Perbarui `app/config.py` dan `.env.example` dengan semua variabel konfigurasi baru (sumber musik default full-YouTube, output siaran, host AI, moderasi). Verifikasi dengan script impor `python -c "from app.config import load_settings; s = load_settings(); print(s.music_source)"`.
- [x] 1.3 Siapkan utilitas pengecekan binary portable (`bin/ffmpeg.exe`, `bin/yt-dlp.exe`, `bin/piper.exe`) atau fallback ke PATH sistem. Verifikasi dengan menjalankan fungsi diagnostik binary.

## 2. Music Source & Downloader Module (`app/downloader.py`)

- [x] 2.1 Implementasi `app/downloader.py`: ekstraksi metadata YouTube, penegakan batas durasi (`YT_MAX_DURATION_SEC`) dan penolakan live stream (`YT_BLOCK_LIVE`). Verifikasi dengan unit test/smoke test URL YouTube pendek.
- [x] 2.2 Tambahkan fungsi download audio ke cache lokal (`data/tracks/<id>.<ext>`) dan normalisasi judul lagu. Verifikasi file audio tersimpan dan tidak ter-download ulang saat dipanggil kedua kali.
- [x] 2.3 Tambahkan dukungan pencarian teks bebas (mis. `"Sheila on 7 Dan"`) via `ytsearch1:`. Verifikasi dengan memanggil pencarian dan mencetak metadata yang didapat.

## 3. Database & Queue Store Update (`app/queue_store.py`)

- [x] 3.1 Perbarui skema SQLite di `app/queue_store.py` untuk mendukung kolom `source_type`, `source_url`, `local_path`, `shoutout_message`, `shoutout_audio_path`, dan `status`. Verifikasi migrasi schema dengan membuka database dan mengecek `PRAGMA table_info(queue)`.
- [x] 3.2 Implementasikan kuota per pengguna (`MAX_QUEUE_PER_USER`), cooldown per user (`REQUEST_COOLDOWN_SEC`), dan total kapasitas antrian (`MAX_QUEUE_TOTAL`). Verifikasi dengan test case yang memicu penolakan kuota.
- [x] 3.3 Tambahkan filter kata terlarang (`BANNED_WORDS`) untuk judul dan pesan salam. Verifikasi penolakan input yang mengandung kata terlarang.

## 4. AI Host & TTS Pipeline (`app/tts.py` & `app/llm.py`)

- [x] 4.1 Implementasi `app/tts.py`: wrapper Piper TTS lokal untuk merender teks naskah menjadi file WAV di `data/voice/`. Verifikasi dengan menghasilkan satu file WAV uji coba dari teks sederhana dan pastikan berkas audio terbuat.
- [x] 4.2 Perbarui `app/llm.py`: tambahkan fungsi generator naskah DJ radio FM (bahasa Indonesia, pembacaan salam, time check, batasan panjang naskah). Verifikasi dengan menjalankan generator naskah menggunakan mock atau live OpenRouter API.
- [x] 4.3 Tambahkan fallback mode: jika LLM atau TTS gagal, track tetap dapat diputar tanpa suara host. Verifikasi dengan simulasi error TTS.

## 5. Broadcast Engine & Audio Mixing (`app/audio_engine.py`)

- [x] 5.1 Implementasi `app/audio_engine.py`: peracikan filter graph FFmpeg untuk dynamic ducking (`sidechaincompress` musik + suara host). Verifikasi dengan menggabungkan 1 lagu uji coba dan 1 suara host uji coba, lalu periksa apakah output WAV/AAC mengecil saat host bicara.
- [x] 5.2 Implementasikan output HLS kontinu (penulisan berkas `.m3u8` dan potongan segmen 2 detik ke `data/hls/`). Verifikasi berkas `live.m3u8` terbuat dan segmen `.ts` bertambah saat siaran berjalan.
- [x] 5.3 Implementasikan output RTMP opsional (jika `STREAM_MODE=both` atau `rtmp` dan kredensial terisi). Verifikasi bahwa proses tidak crash jika kredensial RTMP kosong.
- [x] 5.4 Buat `app/stream_watchdog.py`: memantau status subproses FFmpeg dan merestart otomatis bila terputus tak terduga. Verifikasi dengan simulasi terminate subproses FFmpeg.

## 6. Web Player & REST API (`app/web_server.py` & `web/index.html`)

- [x] 6.1 Implementasikan endpoint REST API: `/api/now-playing`, `/api/queue`, dan POST `/api/request`. Verifikasi dengan memanggil endpoint via HTTP request.
- [x] 6.2 Buat antarmuka web player modern di `web/index.html` menggunakan `hls.js`: audio player sinkron, tampilan lagu/cover, kotak salam aktif, dan form request. Verifikasi pemutaran stream HLS dari browser lokal.
- [x] 6.3 Sajikan file statis HLS dan web player melalui server async di port `WEB_PORT` (default 8000). Verifikasi akses URL `http://localhost:8000`.

## 7. Telegram Bot Integration & Refactor (`app/handlers.py` & `app/main.py`)

- [x] 7.1 Perbarui `app/handlers.py`: integrasikan perintah `/request` (URL/teks + salam) dan `/salam` ke dalam antrian baru, serta sesuaikan `/now`, `/list`, dan `/status`. Verifikasi respons bot terhadap perintah-perintah tersebut.
- [x] 7.2 Hubungkan pesan bahasa natural LLM (`cmd_ask`) dengan fungsi queue lagu YouTube baru. Verifikasi teks chat bahasa natural berhasil memasukkan lagu ke antrian.
- [x] 7.3 Perbarui `app/main.py`: jalankan secara bersamaan Telegram bot long polling, background audio engine loop, dan web server HTTP dalam satu event loop asyncio. Verifikasi ketiga komponen menyala bersama saat startup.

## 8. Integrasi Akhir & Uji Coba End-to-End

- [x] 8.1 Uji skenario lengkap: kirim request lagu via web form/Telegram $\rightarrow$ yt-dlp mengunduh $\rightarrow$ LLM menyusun naskah DJ $\rightarrow$ Piper merender suara $\rightarrow$ FFmpeg menyiarkan dengan ducking $\rightarrow$ web player memutar audio sinkron.
- [x] 8.2 Perbarui dokumentasi `README.md` dan `docker-compose.yml` agar mencakup binary dan port baru. Verifikasi build container jika Docker tersedia.
