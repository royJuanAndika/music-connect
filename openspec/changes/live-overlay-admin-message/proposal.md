# Proposal: Live Audio Overlay for Admin Announcements

## Why

Perintah siaran pesan mandiri (`/pesan`) saat ini bekerja dengan membunuh subproses pemutaran lagu yang sedang berjalan (`audio_engine.stop()`) dan menyalakan subproses baru. Pola ini memutus soket RTMPS Telegram secara mendadak (*broken pipe / connection reset*), menimbulkan jeda hening berkepanjangan, dan merusak kenyamanan siaran langsung.

Perubahan ini merancang mekanisme **Live Audio Overlay**: pesan dari Admin disuntikkan secara dinamis di atas musik yang sedang mengudara. Musik otomatis melirih (ducking) perlahan di menit pemutaran saat itu, suara penyiar membacakan pesan/salam, dan musik kembali naik ke 100% tanpa menghentikan lagu atau memutus koneksi RTMP Telegram.

## What Changes

- **Live Audio Overlay / Mid-Song Ducking:**
  - Menghilangkan terminasi subproses FFmpeg saat `/pesan` dieksekusi.
  - Memanfaatkan penyuntikan audio dinamis (mis. FIFO audio stream / live sidechain mix) sehingga suara pengumuman masuk di tengah lagu yang sedang mengudara.
  - Volume musik melirih ke ~15% saat suara pesan aktif, lalu kembali naik secara halus ke 100% dan melanjutkan lagu sampai selesai.
- **Transisi Bebas Putus (Zero Disconnect):**
  - Soket RTMPS Telegram dan stream HLS Web Player tetap berstatus *ESTABLISHED* terus-menerus tanpa ada interupsi jaringan.
- **Antarmuka Konfirmasi Admin:**
  - Memberi notifikasi bahwa pengumuman sedang disisipkan ke siaran langsung saat ini juga.

### Yang Dipertahankan (re-use)
- Karakter suara cewek manis Gadis (`id-ID-GadisNeural`) berbasis `edge-tts`.
- Filter ducking presisi (`sidechaincompress`, `normalize=0`, `dropout_transition=0`).
- Otorisasi ketat Admin (`ALLOWED_TELEGRAM_IDS`).

### Yang Diubah (refactor)
- `app/handlers.py`: Mengubah `cmd_pesan` agar tidak lagi mematikan `audio_engine.stop()`, melainkan memicu metode overlay/inject.
- `app/audio_engine.py`: Menyediakan kanal injeksi live audio atau dynamic mixing overlay.

## Capabilities

### New Capabilities
- `live-overlay-broadcast`: Penyuntikan dan mixing pesan suara admin secara langsung di atas aliran lagu yang sedang berjalan tanpa pemutusan stream.

### Modified Capabilities
- (Tidak ada) — Belum ada baseline spec di `openspec/specs/`.

## Impact

- **Kode yang terpengaruh:** `app/audio_engine.py`, `app/handlers.py`, `app/main.py`.
- **Pengguna:** Pendengar tidak lagi merasakan siaran putus atau macet saat ada pengumuman masuk.

## Non-goals

- **Bukan** penggantian lagu secara instan (jika ingin mengganti lagu tetap menggunakan perintah `/skip`).
- **Bukan** penumpukan banyak suara penyiar sekaligus (pesan diproses bergantian secara teratur).
