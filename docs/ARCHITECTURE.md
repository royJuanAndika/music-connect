# Arsitektur Sistem Radio Stream AI

Dokumen ini menjelaskan rancangan arsitektur teknis sistem siaran radio live interaktif berbasis AI (`music-connect` v2).

## 1. Ikhtisar Sistem

Radio Stream AI mengubah fungsi bot kontroler Spotify menjadi stasiun radio streaming live:
- **Audio Sinkron:** Semua pendengar mendengar segmen audio yang sama pada waktu yang sama.
- **Sumber Musik Full-YouTube:** Menggunakan `yt-dlp` untuk mengunduh audio ke cache lokal tanpa ketergantungan akun premium.
- **AI Host (Penyiar Radio):** LLM (OpenRouter/Ollama) menyusun naskah ucapan DJ radio berbahasa Indonesia, lalu disintesis secara lokal dengan Piper TTS.
- **Dynamic Audio Ducking:** FFmpeg memproses musik dan suara host menggunakan filter `sidechaincompress` agar volume musik mengecil otomatis saat host bicara.
- **Distribusi Siaran:** Output HLS (`.m3u8` dan potongan segmen 2 detik) untuk Web Player dan opsi RTMP untuk Telegram Live.

---

## 2. Diagram Arsitektur & Alur Data

```
                     +---------------------------------------+
                     |           Input Pendengar             |
                     |  - Telegram Bot (/request, /salam)    |
                     |  - Web Player Form (REST API)         |
                     +---------------------------------------+
                                         |
                                         v
                     +---------------------------------------+
                     |         Moderasi & Kuota Antrian      |
                     |  - Banned words filter                |
                     |  - Cooldown & max limit per user      |
                     +---------------------------------------+
                                         |
                                         v
                     +---------------------------------------+
                     |       SQLite Database (QueueStore)    |
                     |            data/queue.db              |
                     +---------------------------------------+
                                         |
                   +---------------------+---------------------+
                   | (Track berikutnya)                        | (Konteks salam & request)
                   v                                           v
       +-----------------------+                   +-----------------------+
       |   YouTube Downloader  |                   |   LLM DJ Script Gen   |
       |       (yt-dlp)        |                   | (OpenRouter / Ollama) |
       +-----------------------+                   +-----------------------+
                   |                                           | (Naskah siaran)
                   v                                           v
       +-----------------------+                   +-----------------------+
       |  Audio Cache (Lokal)  |                   |    Piper TTS Engine   |
       |  data/tracks/<id>     |                   |  data/voice/<id>.wav  |
       +-----------------------+                   +-----------------------+
                   \                                           /
             [0:a]  \                                         /  [1:a]
                     \                                       /
                      v                                     v
         +-------------------------------------------------------------+
         |                    FFmpeg Broadcast Engine                  |
         |                                                             |
         |   Filter Graph:                                             |
         |   [0:a][1:a] sidechaincompress (ducking) -> amix -> [out]   |
         |                                                             |
         |   Encoders:                                                 |
         |   - HLS Packager (live.m3u8, segment_%03d.ts)               |
         |   - RTMP Streamer (flv -> Telegram Channel Live)            |
         +-------------------------------------------------------------+
                                        |
                   +--------------------+--------------------+
                   |                                         |
                   v                                         v
       +-----------------------+                 +-----------------------+
       |   Web Server HLS      |                 | Telegram Live Stream  |
       |   http://0.0.0.0:8000 |                 | (RTMP Endpoint)       |
       +-----------------------+                 +-----------------------+
                   |
                   v
       +-----------------------+
       |   Pendengar Web       |
       |   (hls.js Player)     |
       +-----------------------+
```

---

## 3. Komponen Utama

### 3.1 `app/config.py` & `app/binary_resolver.py`
- Mengatur konfigurasi berbasis environment variable (`Settings`).
- `binary_resolver.py`: Mendeteksi ketersediaan binary eksternal di folder `bin/` lokal maupun `PATH` sistem operasi.

### 3.2 `app/downloader.py` (YouTube Downloader)
- Wrapper untuk `yt-dlp`.
- Mendukung pencarian teks (`ytsearch1:`) atau URL langsung YouTube.
- Proteksi: Menolak live stream (`YT_BLOCK_LIVE`), batas maksimal durasi (`YT_MAX_DURATION_SEC`), batas minimal durasi.
- Cache lokal: Berkas audio disimpan di `data/tracks/<video_id>.<ext>` agar tidak diunduh berulang.

### 3.3 `app/queue_store.py` (SQLite Store)
- Menyimpan riwayat antrian dan status lagu (`pending`, `playing`, `played`, `error`).
- Menerapkan penegakan kuota:
  - `MAX_QUEUE_PER_USER`: Batas antrian aktif per pengguna.
  - `MAX_QUEUE_TOTAL`: Batas total kapasitas antrian.
  - `REQUEST_COOLDOWN_SEC`: Jeda waktu antar request dari pengguna yang sama.
  - `BANNED_WORDS`: Filter kata terlarang pada judul lagu dan pesan salam.

### 3.4 `app/llm.py` & `app/tts.py` (AI Host Pipeline)
- `llm.py`: Memanggil OpenRouter API untuk menyusun naskah DJ dengan persona ramah anak muda dalam Bahasa Indonesia.
- `tts.py`: Wrapper Piper TTS lokal yang merender naskah menjadi berkas audio WAV (`data/voice/`).
- Fallback: Jika LLM atau TTS bermasalah, siaran tetap berlanjut memutar musik tanpa memutus aliran audio.

### 3.5 `app/audio_engine.py` & `app/stream_watchdog.py`
- Meracik filter graph FFmpeg `sidechaincompress` untuk dynamic ducking:
  ```text
  [0:a][1:a]sidechaincompress=threshold=0.25:ratio=6:attack=200:release=800[ducked];
  [ducked][1:a]amix=inputs=2:duration=first:dropout_transition=2[out]
  ```
- Menghasilkan segmen HLS 2 detik ke direktori `data/hls/`.
- `stream_watchdog.py`: Memantau proses FFmpeg dan melakukan restart otomatis bila terjadi crash.

### 3.6 `app/web_server.py` & `web/index.html`
- Server HTTP berbasis Python standard library (`ThreadingHTTPServer`).
- Endpoint REST API:
  - `GET /api/now-playing`: Judul lagu, artis, status bicara host, dan teks titip salam.
  - `GET /api/queue`: Daftar antrian lagu yang akan datang.
  - `POST /api/request`: Menerima input lagu dan salam dari form web.
  - `GET /hls/*`: Menyalurkan playlist `.m3u8` dan segmen `.ts`.
- Frontend di `web/index.html` menggunakan `hls.js` dengan live latency recovery.

---

## 4. Panduan Ekstensi & Pengembangan Berikutnya

1. **Fallback Background Playlist:**
   - Bila antrian kosong (`queue_store.pop_next() == None`), tambahkan fungsi pemutar playlist folder lokal (`data/fallback/`) atau jingle stasiun radio agar siaran tidak berhenti.
2. **Audio Normalization (EBU R128):**
   - Tambahkan filter FFmpeg `loudnorm` pada jalur input musik agar volume antar lagu yang diunduh dari YouTube selalu seragam.
3. **Multi-Model Voice Piper:**
   - Tambahkan opsi pemilihan suara cowok/cewek untuk variasi penyiar.
