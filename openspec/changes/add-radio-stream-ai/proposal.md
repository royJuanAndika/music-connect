# Proposal: Radio Stream AI (Evolusi `music-connect`)

## Why

`music-connect` saat ini hanya **remote control Spotify**: bot Telegram menitipkan lagu ke perangkat Spotify Connect fisik, dan audio diputar oleh HP/speaker di lokasi operator. Tidak ada siaran yang bisa didengar banyak orang secara sinkron, tidak ada suara penyiar, dan bergantung pada akun Spotify Premium + device yang harus selalu online.

Kita ingin mengubahnya menjadi **stasiun radio live sungguhan**: satu aliran audio yang didengar sinkron oleh banyak pendengar (>10) lewat web (HLS) maupun Telegram (RTMP), dengan **AI Host** yang membacakan request dan titip salam layaknya penyiar radio FM. Sumber musik dialihkan **full ke YouTube** (`yt-dlp`) sehingga tidak butuh Spotify Premium maupun device fisik.

## What Changes

- **Sumber musik baru (default full-YouTube):** resolusi link YouTube / teks pencarian via `yt-dlp`, plus cache audio lokal agar tidak download berulang.
- **Broadcast engine baru (FFmpeg):** satu proses streaming kontinu yang menggabungkan musik + suara host, output HLS (`.m3u8`) untuk web dan opsional RTMP untuk Telegram Live.
- **AI Host baru:** LLM menyusun naskah siaran (backsell/forward-sell, salam, time check) lalu Piper TTS (lokal) merender suara; FFmpeg melakukan **dynamic ducking** (`sidechaincompress`) saat host bicara.
- **Request & titip salam:** memperluas `QueueStore` (source URL, path cache, pesan salam, status) dan menambah jalur masuk dari **web form** di samping Telegram bot.
- **Web Player baru:** halaman `hls.js` + REST API (now-playing, queue, form request) — **BREAKING** terhadap model "kontrol device Spotify" yang lama.
- **Konfigurasi config-driven:** semua perilaku diatur via `.env` (`app/config.py`), default `MUSIC_SOURCE=youtube`.
- **Penghapusan jalur Spotify playback:** `auth.py` (OAuth callback port 8888), kontrol `/me/player/*`, dan `device_watchdog` fisik tidak lagi menjadi jalur utama.

### Yang Dipertahankan (re-use)
- `app/memory.py` — dipakai sebagai memori AI Host (routine playlist & catatan/preferensi pendengar).
- `app/queue_store.py` — diperluas, bukan diganti.
- `app/llm.py` & `app/tools.py` — diperluas dengan mode DJ Host + tool baru.
- `app/handlers.py` & `app/main.py` — dipakai ulang sebagai pintu Telegram, ditambah worker siaran.
- Pola config-driven (`app/config.py`, `.env.example`), struktur Docker, dan gaya kode.

### Yang Diubah (refactor)
- `app/spotify_client.py` — peran bergeser dari pemutar menjadi **resolver metadata opsional** (default nonaktif).
- `app/device_watchdog.py` — menjadi **stream watchdog** yang mengawasi proses FFmpeg (bukan device fisik).
- `app/config.py` — menambah ~40 env baru, menghapus field Spotify dari jalur default.

### Yang Baru
- `app/downloader.py` — wrapper `yt-dlp` + cache + normalizer judul.
- `app/tts.py` — wrapper Piper TTS.
- `app/audio_engine.py` — FFmpeg mixing/ducking + HLS/RTMP.
- `app/web_server.py` + `web/index.html` — Web Player & REST API.

## Capabilities

### New Capabilities
- `music-source`: resolusi & pengambilan audio YouTube (URL/link/teks), cache lokal, normalisasi judul, batas durasi/anti-live.
- `ai-host`: pembuatan naskah siaran oleh LLM, sintesis suara Piper TTS, dan ducking musik saat host bicara.
- `broadcast-engine`: proses siaran kontinu FFmpeg dengan output HLS dan/atau RTMP serta pengawasan proses.
- `listener-requests`: antrian request + titip salam dari Telegram dan web, termasuk aturan moderasi/kuota.
- `web-player`: halaman pemutar web sinkron (`hls.js`), REST API now-playing/queue, dan form request publik.

### Modified Capabilities
- (Tidak ada) — belum ada spec lama di `openspec/specs/`; semua perilaku di atas didefinisikan sebagai capability baru.

## Impact

- **Kode:** `app/config.py`, `app/queue_store.py`, `app/llm.py`, `app/tools.py`, `app/handlers.py`, `app/main.py` diubah; `app/spotify_client.py`, `app/device_watchdog.py`, `app/auth.py` direfaktor/dipensiunkan dari jalur default; modul baru `downloader.py`, `tts.py`, `audio_engine.py`, `web_server.py`; frontend `web/index.html`.
- **Dependensi eksternal baru:** binary `yt-dlp`, `ffmpeg`, `piper` (+ model voice `id_ID`). Tidak lagi butuh akun Spotify Premium untuk jalur default.
- **Konfigurasi:** penambahan besar env di `.env.example` (sumber musik, output stream, host AI, moderasi); env Spotify menjadi opsional.
- **Infrastruktur:** port web player baru; folder runtime `data/tracks`, `data/voice`, `data/hls`; Dockerfile perlu menyertakan FFmpeg & yt-dlp.
- **Non-teknis:** meningkatnya ketergantungan pada `yt-dlp` (rawan berubah saat YouTube update) dan risiko kepatuhan ToS YouTube/hak cipta yang harus disadari operator.

## Non-goals

- **Bukan** layanan streaming on-demand (VOD) atau playlist pribadi per-pendengar; audio bersifat siaran sinkron.
- **Bukan** interaksi voice 2 arah realtime (pendengar tidak bicara langsung ke host); interaksi berupa teks request/salam.
- **Bukan** penarikan audio langsung dari server Spotify (DRM); Spotify hanya opsional sebagai sumber metadata, bukan sumber audio.
- **Bukan** jaminan latensi sub-detik; HLS memiliki delay wajar (3–6 detik).
- **Bukan** sistem multi-tenant/komersial dengan manajemen lisensi musik atau billing.
