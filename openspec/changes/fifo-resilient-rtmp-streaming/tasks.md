# Tasks: FIFO Resilient RTMP Streaming

## 1. Peningkatan Muxer Output di Audio Engine (`app/audio_engine.py`)

- [x] 1.1 Perbarui fungsi `build_ffmpeg_cmd` di `app/audio_engine.py` untuk membungkus keluaran RTMP menggunakan `-f fifo -fifo_format flv -drop_pkts_on_overflow 1 -attempt_recovery 1 -recovery_wait_time 1`.
- [x] 1.2 Perbarui fungsi `build_message_cmd` dan `build_standby_cmd` di `app/audio_engine.py` agar juga menggunakan wrapper FIFO yang tangguh.

## 2. Pengujian & Verifikasi

- [x] 2.1 Perbarui unit test di `tests/test_audio_engine.py` untuk memverifikasi struktur flag FIFO muxer pada seluruh variasi perintah pemutaran audio. Jalankan unit test dan pastikan lulus 100%.
