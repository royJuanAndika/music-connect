# Design: Live Audio Overlay for Admin Announcements

## Context

Lihat `proposal.md` untuk motivasi. Saat ini perintah `/pesan` memutus lagu yang sedang diputar (`audio_engine.stop()`) dan memicu putus soket RTMPS Telegram (*broken pipe*).

## Goals / Non-Goals

**Goals:**
- Mengizinkan pengumuman suara menyisip di atas siaran lagu yang sedang berjalan dengan penurunan volume otomatis (ducking) tanpa memutus koneksi streaming.
- Memastikan durasi proses pemutaran audio memiliki batas waktu yang jelas agar tidak menggantung (*anti-deadlock*).
- Memperbarui `ALLOWED_GROUP_IDS` menjadi `-1003946103740`.

**Non-Goals:**
- Tidak mengubah antrian lagu pendengar `/request` dan `/salam`.

## Decisions

### 1. Zero Stream Disconnect
Pesan suara di-render ke file audio WAV/MP3 di `data/voice/`. Jika lagu sedang berputar, durasi lagu dan audio pesan dicampur secara mulus. Jika proses harus beralih, FFmpeg dipanggil dengan flag `-shortest` dan batasan waktu eksplisit agar tidak pernah terjadi infinite loop.

### 2. Otorisasi Grup dan Admin
- Grup ID: `-1003946103740`.
- Perintah `/pesan` diverifikasi terhadap `ALLOWED_TELEGRAM_IDS`.
