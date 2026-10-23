# Proposal

## Why
Saat ini, fitur `/pesan` dan `/salam` dimasukkan ke dalam antrean tunggu (`queue`) SQLite yang bersifat sekuensial dan diputar setelah lagu yang sedang aktif selesai diputar. Ketika lagu sedang berjalan, pesan tidak dapat langsung menyela atau menimpa audio seperti sistem donasi/alert real-time (Saweria/OBS alert). Selain itu, tombol inline Telegram (`InlineKeyboardMarkup`) di grup kerap mengalami masalah responsif (error Telegram silent saat edit message, pesan duplikat saat tombol bump/delete ditekan, ketiadaan pagination antrean). Perubahan ini memperkenalkan arsitektur real-time audio injection alert sekaligus menyempurnakan interaktivitas dan reliabilitas tombol-tombol Telegram bot.

## What Changes
- Menghapus ketergantungan `/pesan` dan `/salam` dari antrean lagu sekuensial (langsung diproses secara instan/real-time via alert injection).
- Mengimplementasikan pipeline streaming audio dinamis dengan kemampuan real-time injection: audio lagu yang sedang berjalan di-ducking secara dinamis saat ada pesan audio TTS baru yang disuntikkan.
- Menambahkan alert audio queue/channel independen yang mentrigger proses synthesis Piper TTS segera setelah perintah diterima dan membunyikannya ke live stream dalam hitungan detik.
- Mengembalikan volume lagu ke level normal secara halus (fade-in / auto release) setelah pesan suara selesai dibacakan.
- Memperbaiki penanganan Callback Query Telegram: perlindungan safe edit message (penanganan `MessageNotModified` & sanitasi markdown aman), feedback toast instan di semua tombol, in-place update untuk antrean (`bump`, `del`, `refresh`), serta dukungan pagination antrean lagu interaktif.

### Non-goals
- Tidak mengganti playback stream HLS atau RTMP Telegram dengan server media pihak ketiga yang membutuhkan lisensi eksternal berbayar.
- Tidak mengubah antrean request lagu reguler (`/request`, `/q`), yang tetap berjalan berurutan sesuai urutan di `QueueStore`.

## Capabilities

### New Capabilities
- `real-time-audio-injection`: Mengelola injeksi audio alert (pesan suara/salam) secara langsung ke stream broadcast yang sedang aktif dengan efek dynamic volume ducking tanpa menunggu lagu selesai.
- `telegram-interactive-ui`: Memperbaiki dan memperkaya fungsionalitas tombol Telegram (safe callback handlers, in-place list update, toast alert feedback, navigasi antrean interaktif).

### Modified Capabilities
<!-- None. -->

## Impact
- **Affected code**: `app/audio_engine.py`, `app/handlers.py`, `app/main.py`, `app/config.py`, `app/alert_manager.py`.
- **APIs & Telegram Handlers**: Perintah `/pesan` dan `/salam` merespons secara asinkron tanpa menambah item `status="pending"` ke antrean lagu radio; callback query router Telegram bekerja secara mulus tanpa error parsing markdown.
- **Dependencies**: Mengoptimalkan FFmpeg piping dan Telegram Inline UI.
