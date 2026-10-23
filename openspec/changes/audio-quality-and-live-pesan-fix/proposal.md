# Proposal: Audio Quality Overhaul & Live Pesan Fix

## Why
Kualitas audio siaran saat ini mengalami distorsi/clipping kasar karena boost `volume=2.0` tanpa limiter, bitrate dan sample rate sub-optimal (128 kbps 44.1 kHz), serta ducking yang memotong musik terlalu agresif. Selain itu, fitur `/pesan` belum bersuara secara nyata di siaran karena audio bed sintetis yang bermasalah dan penanganan pemutaran pesan instan di audio engine belum terintegrasi mulus dengan stream output.

## What Changes
- **Audio Quality Upgrade**: Standarisasi output stream HLS dan RTMP ke 48.000 Hz, 192 kbps stereo AAC.
- **Limiter & Anti-Clipping**: Hapus pengali `volume=2.0` kasar, pasang audio limiter (`alimiter`) agar volume siaran kencang, punchy, dan bebas pecah/distorsi.
- **Natural Smooth Ducking**: Tune parameter `sidechaincompress` (attack 30ms, release 1200ms, ratio 5) dan tambahkan filter kejernihan vokal penyiar (`highpass=f=80`, boost frekuensi wicara).
- **Fix Live Pesan Audio Execution**: Perbaiki peracikan filter audio pada `play_message_sync` dan sintesis audio pesan agar suara pengumuman admin/pendengar langsung terdengar jelas dengan backing track bed yang stabil.

## Non-goals
- Tidak mengganti engine TTS Piper lokal dengan provider eksternal lain.
- Tidak mengubah skema database SQLite `queue.db`.
- Tidak mengubah antarmuka bot Telegram untuk command selain tuning penanganan `/pesan`.

## Codebase: Lama vs Diubah vs Baru
- **Dipertahankan**: Arsitektur asyncio `app/main.py`, penyimpanan SQLite `app/queue_store.py`, flow download YouTube `app/downloader.py`.
- **Diubah**:
  - `app/audio_engine.py`: Perbaikan rantai filter ducking, penambahan limiter, perbaikan `build_message_ffmpeg_cmd` dan `play_message_sync`.
  - `app/config.py`: Penyesuaian default sample rate (48000), bitrate (192k), dan parameter limiter/ducking.
  - `app/handlers.py` & `app/main.py`: Pastikan alur interupsi dan eksekusi `/pesan` memicu audio engine secara andal.
- **Baru**: Unit test verifikasi filter chain anti-clipping dan message audio generator.

## Capabilities

### New Capabilities
- `audio-quality-enhancement`: Standardisasi audio pipeline ke 48kHz/192k, audio limiter anti-clipping, dan smooth FM radio ducking.
- `live-pesan-broadcast`: Integrasi siaran pesan interupsi/pengumuman suara langsung yang terdengar jelas melalui audio bed yang valid.

### Modified Capabilities
None.

## Impact
- `app/audio_engine.py`, `app/config.py`, `app/handlers.py`, `app/main.py`.
- Output audio siaran HLS dan RTMP Telegram menjadi jauh lebih jernih, stabil, dan bebas clipping.
