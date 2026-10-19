# Proposal: FIFO Resilient RTMP Streaming

## Why

Siaran Telegram Live via RTMPS internasional saat ini rentan mengalami *Broken Pipe* (exit code 224/251) dan audio tersendat ketika terjadi fluktuasi latensi jaringan atau micro-packet loss TCP antara VPS dan server Telegram. Output FLV standar FFmpeg tidak memiliki mekanisme penanganan buffer overflow yang fleksibel, sehingga ketika jaringan tersendat sesaat, proses FFmpeg langsung memutus siaran.

Perubahan ini menerapkan arsitektur penyiaran tahan banting menggunakan FFmpeg **FIFO Muxer (`-f fifo -fifo_format flv`)** dengan fitur *drop packets on overflow* dan *auto-recovery*. Mekanisme ini memastikan jika terjadi hambatan jaringan sesaat, FFmpeg tidak crash dan aliran audio tetap mengalir mulus tanpa lag di aplikasi Telegram pendengar.

## What Changes

- **Penerapan FIFO Muxer Wrapper:**
  - Mengganti output langsung `-f flv <url>` dengan wrapper antrian FIFO: `-f fifo -fifo_format flv`.
  - Mengaktifkan `-drop_pkts_on_overflow 1`: Secara cerdas membuang frame video kanvas hitam jika buffer pengiriman mampet agar audio AAC tidak tercekik dan tetap mengalir secara real-time.
  - Mengaktifkan `-attempt_recovery 1` dan `-recovery_wait_time 1`: Otomatis menyambungkan ulang soket RTMP dalam 1 detik jika koneksi jaringan sempat terputus tanpa mematikan proses siaran lagu.
- **Pacing Send Buffer yang Proporsional:**
  - Menetapkan batas `-bufsize 400k` untuk mengisolasi fluktuasi throughput jaringan internasional.

### Yang Dipertahankan (re-use)
- Seluruh pipeline audio ducking, suara Gadis (`edge-tts`), dan integrasi bot Telegram.
- Jalur proxy Cloudflare WARP untuk pengunduhan YouTube.
- Skema database antrian SQLite dan otorisasi admin.

### Yang Diubah
- Fungsi pembangun perintah output RTMP di `app/audio_engine.py` (`build_ffmpeg_cmd`, `build_message_cmd`, `build_standby_cmd`).

## Capabilities

### New Capabilities
- `fifo-streaming`: Ketahanan transmisi RTMP terhadap fluktuasi jaringan menggunakan antrian FIFO, packet drop adaptif, dan auto-reconnect.

### Modified Capabilities
- (Tidak ada)

## Impact

- **Kode yang terpengaruh:** `app/audio_engine.py`, `tests/test_audio_engine.py`.
- **Pengguna:** Pendengar di Telegram Live tidak lagi mengalami audio terhenti atau tersendat saat terjadi fluktuasi jaringan internet.

## Non-goals

- Tidak mengubah codec audio AAC atau bitrate audio dasar (128 kbps).
