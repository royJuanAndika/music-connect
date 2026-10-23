# Tasks: Audio Quality Overhaul & Live Pesan Fix

## 1. Config & Audio Engine Tuning (`app/config.py`, `app/audio_engine.py`)

- [x] 1.1 Perbarui konfigurasi audio di `app/config.py`: ubah default `STREAM_SAMPLE_RATE=48000`, `STREAM_BITRATE=192k`, ducking attack/release/ratio, dan verifikasi objek settings memuat nilai default baru dengan benar melalui unit test.
- [x] 1.2 Rombak filter mixing di `app/audio_engine.py`: ganti pengali kasar `volume=2.0` dengan `alimiter` (anti-clipping), pasang filter vokal pada suara penyiar (`highpass=f=80`), dan verifikasi via command test bahwa filter graph FFmpeg yang di-generate valid secara sintaksis.
- [x] 1.3 Perbaiki `build_message_ffmpeg_cmd` dan `play_message_sync` di `app/audio_engine.py`: pastikan generator audio bed sintetis lavfi dan mapping duration first berjalan tanpa hang dan mengalir ke HLS & RTMP secara sinkron.

## 2. Live Message Orchestration (`app/handlers.py`, `app/main.py`)

- [x] 2.1 Audit dan selaraskan eksekusi antrean pesan di `app/main.py`: pastikan saat pesan disiarkan, audio engine memicu `play_message_sync` dengan voice file yang sudah selesai disintesis dan status queue diperbarui menjadi `played`.
- [x] 2.2 Pastikan notifikasi bot di `app/handlers.py` untuk `/pesan` memberikan feedback jelas bahwa pesan sedang diproses dan masuk siaran live.

## 3. Verification & Testing (`tests/`)

- [x] 3.1 Buat unit test di `tests/test_audio_quality_limiter.py` untuk menguji parameter `build_ffmpeg_cmd` dan `build_message_ffmpeg_cmd` memastikan keberadaan `alimiter`, 48000 Hz, dan 192k bitrate.
- [x] 3.2 Jalankan rangkaian test `pytest tests/` dan pastikan seluruh test audio engine dan queue store lulus tanpa error.
