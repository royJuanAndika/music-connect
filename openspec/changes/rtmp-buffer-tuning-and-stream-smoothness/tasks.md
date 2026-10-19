# Tasks: RTMP Buffer Tuning & Telegram Stream Smoothness

## 1. Konfigurasi Default & Parameter Builder

- [x] 1.1 Perbarui default `RTMP_VIDEO_FPS=15` dan `RTMP_VIDEO_BITRATE=100k` di `app/config.py` dan `.env.example`.
- [x] 1.2 Perbarui `build_ffmpeg_cmd`, `build_message_cmd`, dan `build_standby_cmd` di `app/audio_engine.py` agar menyertakan `-maxrate 100k -bufsize 200k` dan keyframe `-g 30 -keyint_min 30`.

## 2. Pengujian & Verifikasi

- [x] 2.1 Perbarui unit test di `tests/test_audio_engine.py` untuk memverifikasi framerate 15 fps dan flag buffer ceiling pada string perintah FFmpeg. Jalankan unit test dan pastikan lulus.
