# Panduan Pengembangan (Development Guide)

Dokumen ini ditujukan untuk developer yang ingin menjalankan, menguji, dan mengembangkan kode `music-connect` / Radio Stream AI.

---

## 1. Persiapan Lingkungan Lokal

### Kebutuhan Sistem:
- Python 3.12+ (disarankan)
- Git
- Docker Desktop (opsional, jika ingin menjalankan via container)
- Binary eksternal (jika berjalan langsung tanpa Docker):
  - `ffmpeg`
  - `yt-dlp`
  - `piper` (plus model voice `.onnx` dan `.json`)

---

## 2. Struktur Proyek

```text
music-connect/
├── app/
│   ├── audio_engine.py      # FFmpeg mixing, ducking, HLS/RTMP packaging
│   ├── binary_resolver.py   # Utilitas pendeteksi binary (bin/ vs system PATH)
│   ├── config.py            # Settings dataclass & parser .env
│   ├── device_watchdog.py   # Watchdog device pemutar Spotify (legacy)
│   ├── downloader.py        # yt-dlp wrapper & audio cache manager
│   ├── handlers.py          # Command handlers Telegram bot
│   ├── llm.py               # OpenRouter LLM client & DJ script generator
│   ├── main.py              # Main entrypoint: broadcast loop + bot + web server
│   ├── memory.py            # Memory store markdown (routines & notes)
│   ├── queue_store.py       # SQLite queue store, kuota, & moderasi
│   ├── spotify_client.py    # Spotify Web API client (legacy/optional)
│   ├── stream_watchdog.py   # Watchdog proses siaran FFmpeg
│   ├── tools.py             # Definisi tool calling untuk LLM
│   ├── tts.py               # Piper TTS local wrapper
│   └── web_server.py        # Async HTTP server untuk HLS & REST API
├── bin/                     # Tempat meletakkan binary portable lokal (.exe)
├── data/                    # Direktori runtime (diabaikan oleh git)
│   ├── hls/                 # Segmen live.m3u8 & .ts
│   ├── tracks/              # Cache audio lagu (<video_id>.<ext>)
│   └── voice/               # Berkas audio ucapan host AI (.wav)
├── docs/                    # Dokumentasi teknis & arsitektur
├── tests/                   # Automated unit & integration tests
├── web/                     # Web Player frontend (index.html)
├── .env.example             # Contoh template konfigurasi lengkap
├── Dockerfile               # Konfigurasi container Linux (FFmpeg + yt-dlp)
├── docker-compose.yml       # Konfigurasi docker compose
└── README.md                # Panduan pengguna (User Guide)
```

---

## 3. Menjalankan Unit & Integration Test

Seluruh test dirancang mandiri menggunakan Python standard library (`unittest` / `assert`) tanpa dependensi framework eksternal:

```powershell
# Jalankan seluruh test suite:
python tests/test_downloader.py
python tests/test_queue_store.py
python tests/test_tts_llm.py
python tests/test_audio_engine.py
python tests/test_web_server.py
python tests/test_handlers.py
python tests/test_e2e.py
```

Semua test akan menghasilkan output:
```text
ALL DOWNLOADER SELF-CHECKS PASSED!
ALL QUEUE STORE TESTS PASSED!
ALL TTS & DJ SCRIPT TESTS PASSED!
ALL AUDIO ENGINE & WATCHDOG TESTS PASSED!
ALL WEB SERVER TESTS PASSED!
ALL HANDLER & TOOL TESTS PASSED!
END-TO-END PIPELINE SIMULATION PASSED!
```

---

## 4. Konfigurasi Testing Cepat (Smoke Test)

Untuk mengetes server web dan antarmuka tanpa menyalakan bot Telegram atau binary audio:
1. Buat file `.env`:
   ```powershell
   Copy-Item .env.example .env
   ```
2. Set variabel berikut di `.env`:
   ```env
   TELEGRAM_ENABLED=false
   MUSIC_SOURCE=youtube
   WEB_PORT=8000
   ```
3. Jalankan aplikasi:
   ```powershell
   python -m app.main
   ```
4. Akses Web Player di `http://localhost:8000`.

---

## 5. Menambahkan Binary Portable di Host Windows

Jika ingin menjalankan full live streaming di Windows tanpa Docker:
1. Unduh executable berikut:
   - `ffmpeg.exe` (dari gyan.dev atau BtbN)
   - `yt-dlp.exe` (dari rilis resmi GitHub yt-dlp)
   - `piper.exe` + model `id_ID-*.onnx` (dari rilis Piper TTS)
2. Letakkan file `.exe` ke dalam folder `bin/`:
   ```text
   bin/
   ├── ffmpeg.exe
   ├── yt-dlp.exe
   └── piper.exe
   ```
3. Periksa deteksi binary dengan perintah:
   ```powershell
   python -m app.binary_resolver
   ```
