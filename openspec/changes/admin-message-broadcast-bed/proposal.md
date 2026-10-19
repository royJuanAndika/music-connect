# Proposal: Admin Message Broadcast & Radio Bed Ducking

## Why

Saat ini sistem hanya mendukung titip salam yang menempel pada permintaan lagu (`/salam <lagu> | <pesan>`). Tidak ada mekanisme bagi pengelola siaran (Admin) untuk menyiarkan pesan pengumuman atau titip salam saja (message-only) dengan latar musik instrumental lirih (Radio Bed / ducking) layaknya stasiun radio FM sungguhan. Selain itu, fitur titip pesan mandiri ini harus dibatasi khusus untuk Admin (`ALLOWED_TELEGRAM_IDS`) guna mencegah spam siaran oleh sembarang pengguna grup.

Perubahan ini menambahkan kemampuan siaran pesan mandiri khusus Admin yang diiringi musik latar instrumental otomatis dengan penurunan volume (dynamic ducking), sehingga penyiar AI dapat menyampaikan pengumuman/salam secara elegan tanpa memutus alur siaran.

## What Changes

- **Perintah Baru Khusus Admin `/pesan`:**
  - Sintaks: `/pesan untuk <Target> | <Isi Pesan>` atau `/pesan <Isi Pesan>`.
  - Akses ketat: Hanya user yang ID-nya terdaftar di `ALLOWED_TELEGRAM_IDS` yang dapat mengeksekusi perintah ini. Pengguna biasa di grup akan ditolak secara santun.
- **Dukungan Tipe Item `source_type='message'` di QueueStore:**
  - Menyimpan item antrian tanpa URL/file musik YouTube.
  - Membawa atribut pesan, target, pengirim, dan durasi perkiraan naskah suara.
- **Audio Bed / Musik Instrumental Pengiring Default:**
  - Menyediakan generator nada latar sintetis / audio bed instrumental santai di `app/audio_engine.py` untuk mengiringi ucapan penyiar saat tidak ada lagu YouTube.
- **Dynamic Ducking Musik Latar Lirih:**
  - FFmpeg memutar musik latar pengiring dan secara otomatis mengecilkan volumenya (ducking ke ~20%) tepat saat suara penyiar AI membacakan pesan, lalu mengembalikan volume secara lembut sebelum segmen berakhir.
- **Fallback Template Naskah Pengumuman:**
  - LLM meracik naskah pengumuman radio formal/santai. Jika API Key kosong, sistem otomatis memakai template radio FM bawaan agar pesan tetap bersuara dengan `edge-tts`.

### Yang Dipertahankan (re-use)
- Seluruh pipeline streaming RTMPS Telegram dan HLS Web Player yang sudah stabil.
- Mekanisme dynamic ducking FFmpeg (`sidechaincompress`).
- Engine `edge-tts` (suara neural Microsoft `id-ID-ArdiNeural`).

### Yang Diubah (refactor)
- `app/handlers.py`: Menambahkan command `/pesan` dengan guard otorisasi Admin (`ALLOWED_TELEGRAM_IDS`).
- `app/main.py`: Menangani item `source_type='message'` dalam `_broadcast_loop` menggunakan audio bed latar.
- `app/audio_engine.py`: Menambahkan fungsi peracikan FFmpeg untuk `play_message_sync` dengan audio bed sintetis.

## Capabilities

### New Capabilities
- `admin-message-broadcast`: Kemampuan Admin untuk menyiarkan pengumuman/salam mandiri di siaran radio yang diiringi musik latar otomatis dengan dynamic ducking.

### Modified Capabilities
- (Tidak ada) — Belum ada baseline spec di `openspec/specs/`.

## Impact

- **Kode yang terpengaruh:** `app/handlers.py`, `app/main.py`, `app/audio_engine.py`, `app/llm.py`.
- **Keamanan:** Memastikan hanya Admin yang dapat menyela siaran dengan pesan pengumuman suara.

## Non-goals

- **Bukan** pembukaan fitur pesan mandiri untuk pendengar umum di grup (pendengar umum tetap menggunakan `/salam` yang menempel pada lagu).
- **Bukan** pengunggahan berkas suara rekaman manual oleh pengguna; suara tetap dihasilkan secara konsisten oleh AI Host.
