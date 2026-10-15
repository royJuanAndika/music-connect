# Design: Radio Stream AI

## Context

Lihat `proposal.md` (Why & What Changes) untuk motivasi. Konteks teknis yang membentuk desain ini:

- Repo lama (`music-connect`) adalah bot Python 3.12 dengan `python-telegram-bot`, `httpx`, SQLite (`QueueStore`), `MemoryStore` berbasis markdown, dan `SpotifyClient` sebagai pengendali device fisik.
- Tidak ada komponen audio apa pun saat ini — seluruh pemutaran didelegasikan ke Spotify Connect.
- Konvensi proyek: config-driven via `.env` + `app/config.py`, SQLite parameterized + lock, kode modular tanpa boilerplate.
- Batasan lingkungan operator: Windows, binary portable lebih disukai daripada paket sistem.

## Goals / Non-Goals

**Goals:**
- Satu proses siaran kontinu yang menggabungkan musik YouTube dan suara host dengan ducking.
- Keluaran HLS untuk web dan RTMP opsional, dari satu sumber audio yang sama (sinkron).
- Antrian request + salam dari Telegram dan web dengan moderasi/kuota.
- Semua perilaku dikendalikan env; default full-YouTube tanpa Spotify.

**Non-Goals:**
- Tidak membangun layanan VOD atau playlist per-pendengar.
- Tidak menangani voice 2 arah realtime.
- Tidak mengimplementasikan transcoding multi-bitrate (ABR) atau CDN — cukup single-bitrate HLS.
- Tidak menangani lisensi musik atau billing.

## Alur Audio

```
   Request masuk (Telegram / Web)
              │
              ▼
      ┌───────────────┐     ┌──────────────────┐
      │  QueueStore   │     │  yt-dlp          │
      │  (SQLite)     │◄────│  download/cache  │
      └──────┬────────┘     └──────────────────┘
             │  track berikutnya (audio cache lokal)
             │
             │        ┌──────────────────┐
             │        │  LLM (naskah DJ) │
             │        └────────┬─────────┘
             │                 ▼
             │        ┌──────────────────┐
             │        │  Piper TTS (WAV) │
             │        └────────┬─────────┘
             ▼                 ▼
   ┌────────────────────────────────────────────┐
   │            FFmpeg Broadcast Engine          │
   │                                             │
   │  [music]───┐                                │
   │            ├─► sidechaincompress (ducking)  │
   │  [voice]───┘        │                       │
   │                     ▼                       │
   │              [mixed audio]                  │
   └─────────────────────┬───────────────────────┘
                         │
            ┌────────────┴────────────┐
            ▼                         ▼
     HLS (.m3u8 + .ts)          RTMP (opsional)
            │                         │
            ▼                         ▼
     Web Player (hls.js)      Telegram Channel Live
```

## Decisions

### 1. Satu proses FFmpeg kontinu sebagai inti siaran
Musik dan suara host digabung dalam satu graf filter FFmpeg, bukan mencampur file per lagu.
- **Rationale:** menjamin sinkron antar pendengar dan memungkinkan ducking lintas transisi lagu tanpa gap.
- **Alternatif ditolak:** pra-render tiap lagu menjadi file jadi (tidak sinkron/live, dan salam tidak bisa menyela di tengah).

### 2. Ducking dengan `sidechaincompress` ketimbang `volume` statis
Suara host menjadi sisi kontrol (sidechain) yang menekan musik.
- **Rationale:** ducking otomatis mengikuti aktivitas suara host, tidak perlu timing manual.
- **Alternatif ditolak:** menurunkan volume musik secara terjadwal (rawan salah timing).

### 3. Cache audio berbasis ID video YouTube
File disimpan di `data/tracks/<video_id>.<ext>` dan dipakai ulang.
- **Rationale:** mengurangi beban jaringan dan risiko rate-limit YouTube; request ulang jadi instan.
- **Alternatif ditolak:** streaming langsung dari URL YouTube tiap kali (lambat, rentan throttle).

### 4. HLS sebagai keluaran default, RTMP opsional
`STREAM_MODE` menentukan keluaran; default `hls`.
- **Rationale:** HLS mudah dikonsumsi browser via `hls.js` dan skalabel tanpa server media tambahan; RTMP (Telegram Live) ditambahkan belakangan.
- **Alternatif ditolak:** Icecast (butuh server terpisah), WebRTC (kompleks untuk fan-out pasif).

### 5. Piper TTS lokal ketimbang TTS cloud
- **Rationale:** gratis, offline, latensi rendah (<1 detik), tanpa biaya per karakter.
- **Alternatif ditolak:** TTS cloud (kualitas lebih baik, tapi biaya berulang dan butuh internet).

### 6. Peran Spotify diturunkan menjadi resolver metadata opsional
Jalur default `MUSIC_SOURCE=youtube` tidak menyentuh Spotify sama sekali.
- **Rationale:** menghilangkan kebutuhan Premium/OAuth; menyederhanakan dependensi.
- **Alternatif ditolak:** mempertahankan playback Spotify (butuh device fisik & Premium).

## Environment Variables (baru)

**Sumber musik (default full-YouTube):**
`MUSIC_SOURCE=youtube`, `YTDLP_PATH=bin/yt-dlp.exe`, `YT_AUDIO_FORMAT=opus`, `YT_AUDIO_BITRATE=128`, `YT_SEARCH_LIMIT=5`, `YT_MAX_DURATION_SEC=600`, `YT_MIN_DURATION_SEC=30`, `YT_ALLOW_TEXT_SEARCH=true`, `YT_ALLOW_PLAYLIST=false`, `YT_BLOCK_LIVE=true`, `YT_COOKIES_FILE=`, `YT_PROXY=`, `CACHE_MAX_GB=10`, `PREFETCH_COUNT=2`

**Output siaran:**
`STREAM_MODE=hls`, `STREAM_BITRATE=128k`, `STREAM_SAMPLE_RATE=44100`, `STREAM_CHANNELS=2`, `HLS_SEGMENT_SECONDS=2`, `HLS_DIR=data/hls`, `RTMP_URL=`, `RTMP_KEY=`, `WEB_PORT=8000`, `FFMPEG_PATH=bin/ffmpeg.exe`

**AI Host:**
`HOST_ENABLED=true`, `HOST_LANGUAGE=id`, `HOST_PERSONA=`, `HOST_MODE=every_song`, `HOST_INTERVAL_SONGS=3`, `LLM_PROVIDER=openrouter`, `LLM_MODEL=openrouter/free`, `TTS_ENGINE=piper`, `PIPER_PATH=bin/piper.exe`, `PIPER_MODEL=models/id_ID-...onnx`, `HOST_MAX_CHARS=400`, `DUCK_LEVEL=0.25`, `DUCK_ATTACK_MS=200`, `DUCK_RELEASE_MS=800`

**Interaksi & moderasi:**
`SHOUTOUT_ENABLED=true`, `SHOUTOUT_MAX_CHARS=200`, `REQUEST_COOLDOWN_SEC=30`, `MAX_QUEUE_PER_USER=3`, `MAX_QUEUE_TOTAL=20`, `BANNED_WORDS=`, `WEB_REQUESTS_OPEN=true`, `TELEGRAM_ENABLED=true`

## Risks / Trade-offs

- **YouTube mengubah proteksi / yt-dlp kedaluwarsa** → pin versi yt-dlp, sediakan flag update, dan cache lokal agar lagu lama tetap bisa diputar.
- **IP rate-limit YouTube** → cache agresif + `PREFETCH_COUNT` terkendali + opsi `YT_PROXY`.
- **ToS YouTube & hak cipta** → dokumentasikan sebagai tanggung jawab operator; sediakan jalur fallback playlist lokal.
- **Latensi HLS 3–6 detik** → segmen 2 detik + tuning playlist; terima sebagai trade-off keterbacaan/skala.
- **Piper TTS intonasi sintetis** → dapat diganti via `PIPER_MODEL`; dokumentasikan cara ganti suara.
- **Proses FFmpeg bisa crash** → stream watchdog restart otomatis + notifikasi operator.
- **Ketergantungan LLM eksternal** → fallback ke mode musik-saja saat LLM gagal.

## Migration Plan

1. Tambah modul baru tanpa menghapus modul lama terlebih dahulu (jalur Spotify tetap ada sebagai opsi nonaktif).
2. Perluas `config.py` dan `.env.example` dengan env baru; default mengarah ke jalur YouTube.
3. Aktifkan broadcast engine + web player, uji end-to-end dengan antrian manual.
4. Setelah stabil, pensiunkan jalur Spotify playback dari default (`MUSIC_SOURCE=youtube`).
5. **Rollback:** kembalikan `MUSIC_SOURCE`/`STREAM_MODE` atau checkout commit sebelumnya; modul lama tetap utuh selama fase migrasi.
