# Tasks: Interactive Telegram Bot & Multi-Source Routing

## 1. Multi-Track Resolution di YouTube Downloader (`app/downloader.py`)

- [x] 1.1 Tambahkan fungsi `search_multitracks(query: str, limit: int = 5) -> list[TrackMetadata]` di `app/downloader.py` menggunakan `ytsearchN:` dengan parsing JSON stream. Verifikasi dengan memanggil fungsi melalui script uji.

## 2. Fleksibilitas Routing Sumber Musik (`app/handlers.py`)

- [x] 2.1 Perbaiki `cmd_search` di `app/handlers.py` agar memeriksa `settings.music_source`: gunakan `YouTubeDownloader` saat mode `youtube` dan `SpotifyClient` saat mode `spotify`. Verifikasi respons perintah tanpa memicu error otentikasi token Spotify.
- [x] 2.2 Perbaiki `cmd_queue` di `app/handlers.py` agar resolusi lagu dan pencarian fallback menyesuaikan `MUSIC_SOURCE`. Verifikasi request angka hasil search dan pencarian teks berjalan lancar.

## 3. Komponen Interaktif Telegram (Inline Buttons & Callbacks)

- [x] 3.1 Buat keyboard inline `InlineKeyboardMarkup` pada hasil perintah `/search` yang menampilkan tombol pilihan lagu untuk langsung dimasukkan ke antrian siaran. Verifikasi tampilan pesan search di Telegram.
- [x] 3.2 Tambahkan tombol kontrol cepat pada respons perintah `/now` (`[ ⏭ Skip ]`, `[ 📜 Antrian ]`, `[ 🔄 Refresh ]`) yang dapat mengedit pesan secara langsung tanpa spam pesan baru. Verifikasi aksi tombol skip dan refresh.
- [x] 3.3 Implementasikan `handle_callback(update, ctx)` di `app/handlers.py` untuk memproses callback query (`qyt:<id>`, `act:skip`, `act:refresh`, `act:bump:<id>`). Verifikasi respons saat tombol ditekan.
- [x] 3.4 Daftarkan `CallbackQueryHandler` di `app/main.py`. Verifikasi integrasi handler saat startup bot.

## 4. Pengujian & Deployment

- [x] 4.1 Perbarui unit test di `tests/test_handlers.py` dan `tests/test_downloader.py` untuk menguji search multi-track dan routing sumber musik. Verifikasi seluruh test suite lulus 100%.
- [x] 4.2 Re-build dan deploy ulang container Docker `radio-stream-ai` di WSL Ubuntu. Verifikasi log kontainer berjalan normal tanpa error.
