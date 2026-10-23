# Design: Audio Quality Overhaul & Live Pesan Fix

## Context
Lihat `proposal.md` untuk motivasi. Saat ini pipeline FFmpeg pada `app/audio_engine.py` mencampur trek musik YouTube dan suara AI Host/Pesan dengan filter penguat volume kasar `volume=2.0` tanpa limiter, yang menyebabkan clipping pada puncak audio. Selain itu, parameter ducking `sidechaincompress` terlalu agresif (`ratio=16`), dan encoder output masih disetel ke 44.1 kHz 128 kbps. Fitur siaran pesan instan `/pesan` (`play_message_sync`) memiliki glitch peracikan filter `amix:duration=first` dan audio bed sintetis yang menyebabkan siaran pesan kadang hening atau macet.

## Goals / Non-Goals
**Goals:**
- Meng-upgrade rantai filter audio FFmpeg dengan `alimiter` dan parameter ducking halus.
- Menstandarkan audio encoding ke 48.000 Hz, 192 kbps AAC stereo.
- Memastikan eksekusi audio pesan `/pesan` berjalan stabil dan terdengar jelas baik di HLS maupun RTMP Telegram.

**Non-Goals:**
- Perubahan model suara Piper TTS atau skema tabel SQLite `queue.db`.
- Mengubah alur antarmuka bot Telegram selain memastikan eksekusi pemutaran audio pesan.

## Audio Flow Diagram
```text
[Input 0: Music Opus 48k] ──────────────────────┐
                                                ▼
[Input 1: Voice Host/Pesan] ──>[vocal_filter] ──> [sidechaincompress (ducking)] ──>[ducked_music]
                                       │                                                │
                                       └──────────>[v_boost] ───────────┐               │
                                                                        ▼               ▼
                                                                  [amix=inputs=2:duration=first]
                                                                                │
                                                                                ▼
                                                                 [alimiter=limit=0.95:attack=5]
                                                                                │
                                                                                ▼
                                                                        [asplit=2]
                                                                       ┌────────┴────────┐
                                                                       ▼                 ▼
                                                             [HLS AAC 48k/192k]  [RTMP AAC 48k/192k]
```

## Decisions

### 1. Audio Limiter vs Fixed Volume Multiplier
- **Pilihan**: Menggunakan `alimiter=limit=0.95:attack=5:release=50:asc=1` di ujung mixing.
- **Alasan**: Mencegah digital clipping (0.0 dBFS) secara transparan saat musik keras bertumpuk dengan suara penyiar, sekaligus menjaga sinyal tetap kencang dan bertenaga.
- **Alternatif**: `loudnorm` (terlalu berat untuk CPU low-spec live streaming) atau pengali statis `volume=1.0` (suara seringkali terlalu kecil).

### 2. Standardisasi ke 48 kHz / 192 kbps
- **Pilihan**: Mengubah default `STREAM_SAMPLE_RATE=48000` dan `STREAM_BITRATE=192k`.
- **Alasan**: Audio dari YouTube yang diunduh via `yt-dlp` rata-rata adalah Opus pada 48 kHz. Menjaga sample rate 48 kHz menghindari resampling artifacts dan memenuhi standar broadcast RTMP Telegram & web modern.
- **Alternatif**: 44.1 kHz 128k (terlalu terkompresi dan berpotensi glitch di beberapa decoder RTMP).

### 3. Tuning Parameter Dynamic Ducking
- **Pilihan**:
  - `sidechaincompress=threshold=0.03:ratio=5:attack=30:release=1200`
  - Vokal host: `highpass=f=80,volume=1.6`
- **Alasan**: `ratio=5` menjaga musik tetap terdengar di latar belakang sekitar 40-50% saat host bicara. `release=1200ms` mengembalikan volume musik secara anggun ala radio FM profesional.
- **Alternatif**: `ratio=16` (membuat musik drop mati dan memantul kasar).

### 4. Perbaikan `play_message_sync` Audio Bed
- **Pilihan**: Pada pesan siaran instan, jika file audio bed tidak ada, sediakan generator lavfi ambient harmonik rendah yang aman dengan durasi yang tepat mengunci durasi vokal pesan (`amix=inputs=2:duration=first`).
- **Alasan**: Mencegah infinite loop generator lavfi dan memastikan audio teralirkan serentak ke HLS dan RTMP.

## Environment Variables
Variabel lingkungan baru / yang diperbarui nilainya di `app/config.py`:
- `STREAM_SAMPLE_RATE`: default `48000` (sebelumnya `44100`).
- `STREAM_BITRATE`: default `192k` (sebelumnya `128k`).
- `AUDIO_DUCKING_RATIO`: default `5.0` (sebelumnya `16.0`).
- `AUDIO_DUCKING_ATTACK`: default `30` (sebelumnya `15`).
- `AUDIO_DUCKING_RELEASE`: default `1200` (sebelumnya `600`).
- `AUDIO_LIMITER_ENABLED`: default `true`.

## Risks / Trade-offs
- **[Risk]** Peningkatan bitrate 192k memakan sedikit lebih banyak bandwidth jaringan di VPS.
  → **Mitigasi**: Peningkatan dari 128k ke 192k hanya ~8 KB/s, sangat aman untuk koneksi VPS.
- **[Risk]** Filter `alimiter` menambah sedikit latensi processing.
  → **Mitigasi**: Attack 5ms sangat ringan dan tidak membebani CPU container.
