# Tasks

## 1. Config & Audio Engine Pipeline Preparation

- [x] 1.1 Tambahkan konfigurasi `ALERT_DUCK_LEVEL`, `ALERT_ATTACK_MS`, `ALERT_RELEASE_MS` di `app/config.py` dan verifikasi pemuatan defaultnya lewat unit test.
- [x] 1.2 Implementasikan named pipe / alert injection channel listener di `app/audio_engine.py` untuk mengizinkan audio alert disuntikkan secara dinamis ke proses FFmpeg aktif, dan verifikasi pipeline filter FFmpeg menerima pipe input tanpa error stream syntax.

## 2. Alert Manager & TTS Generation

- [x] 2.1 Buat modul `app/alert_manager.py` untuk mengelola antrean in-memory alert independen, pemicu TTS latar belakang, dan streaming audio alert ke pipe `AudioEngine`.
- [x] 2.2 Hubungkan `PiperTTS` dan `LLMClient` di `AlertManager` agar pembuatan suara pesan selesai dalam <3 detik dan verifikasi file WAV/PCM alert berhasil dihasilkan.

## 3. Telegram Handlers & Integration

- [x] 3.1 Perbarui command handler `/pesan` dan `/salam` di `app/handlers.py` agar meneruskan permintaan ke `AlertManager` alih-alih memasukkannya ke antrean lagu `QueueStore`, dan verifikasi respons bot Telegram tetap instan.
- [x] 3.2 Uji end-to-end injeksi alert saat pemutaran lagu sedang aktif (simulasi `/pesan` dikirim saat lagu berjalan) untuk memastikan volume lagu otomatis mengecil (ducking), pesan berbunyi, dan koneksi RTMP Telegram/HLS tidak terputus.

## 4. Telegram Interactive Buttons & Callback Fix

- [x] 4.1 Perbaiki `handle_callback` di `app/handlers.py` untuk membungkus `query.edit_message_text` dengan error-guard (tangani `BadRequest: Message is not modified` dan escape MarkdownV2/HTML agar tidak pernah silent fail).
- [x] 4.2 Ubah aksi tombol antrean (`act:bump`, `act:del`, `act:refresh`) agar meng-update tampilan pesan & tombol secara in-place (tanpa spam chat baru di grup), serta tambahkan toast feedback informatif pada setiap klik tombol.
- [x] 4.3 Tambahkan navigasi tombol interaktif untuk pagination antrean (`act:page:<n>`) dan kontrol siaran langsung yang responsif.
