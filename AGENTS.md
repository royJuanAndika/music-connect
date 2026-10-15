# Project Instructions: Radio Stream AI

## Project Overview
Proyek ini adalah evolusi dari `music-connect` (Spotify Telegram Bot) menjadi **Radio Stream AI**:
stasiun siaran radio sinkron (live broadcast) berbasis web (HLS) dan Telegram (RTMP), ditenagai musik murni dari **YouTube** (`yt-dlp`), dipandu **AI Host** (LLM Script + Piper TTS lokal) dengan efek audio ducking studio (FFmpeg sidechain).

## Tech Stack
- **Language:** Python 3.12 (typing, dataclasses, asyncio)
- **Audio Processing:** FFmpeg (sidechaincompress ducking, HLS segmentation, RTMP ingest)
- **Audio Source:** YouTube via `yt-dlp` (direct URL, search query, audio cache)
- **AI Announcer / Host:** LLM (OpenRouter / Ollama) + Piper TTS (lokal Bahasa Indonesia)
- **Database & Queue:** SQLite (`QueueStore` dengan thread-safe connection)
- **Messaging & Control:** Telegram Bot (`python-telegram-bot`)
- **Web Server:** Asynchronous HTTP server (`hls.js` web player + JSON REST API)

## Architecture Rules & Conventions
1. **Config-Driven:** Semua perilaku runtime wajib dikendalikan via environment variable (`.env` dan `app/config.py`).
2. **Default Full-YouTube:** Default `MUSIC_SOURCE=youtube`. Spotify resolver hanya opsional jika dikonfigurasi.
3. **No Breaking Changes to SQLite Safety:** Gunakan parameterized queries dan connection locking pada SQLite.
4. **Binary Management:** Binary portable (`yt-dlp`, `ffmpeg`, `piper`) diletakkan di `bin/` atau diarahkan via env.
5. **Terse & Clean:** Tulis kode yang modular, efisien, minim boilerplate tanpa abstraksi berlebihan.
