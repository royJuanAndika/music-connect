# Tasks: Admin Message Broadcast & Radio Bed Ducking

## 1. Audio Engine & Radio Bed Ducking (`app/audio_engine.py`)

- [x] 1.1 Implementasikan dukungan siaran pesan mandiri (`play_message_sync` atau audio bed generator) di `app/audio_engine.py` menggunakan musik latar pengiring (file `data/radio_bed.mp3` atau audio sintetis) dengan dynamic ducking saat suara penyiar berbicara. Verifikasi peracikan perintah FFmpeg dengan unit test.

## 2. Naskah Pengumuman DJ & Fallback Lokal (`app/llm.py`)

- [x] 2.1 Tambahkan fungsi generator naskah pengumuman mandiri di `app/llm.py` lengkap dengan fallback template radio FM lokal jika API Key LLM kosong/offline. Verifikasi fungsi menghasilkan naskah pengumuman yang menyebutkan pengirim, target, dan isi pesan.

## 3. Perintah Khusus Admin `/pesan` & Broadcast Loop (`app/handlers.py` & `app/main.py`)

- [x] 3.1 Implementasikan perintah `/pesan` di `app/handlers.py` dengan penegakan otorisasi ketat (`ALLOWED_TELEGRAM_IDS`), parsing target dan isi pesan, serta penyimpanan ke QueueStore dengan `source_type='message'`. Verifikasi penolakan akses untuk non-admin dan penerimaan untuk admin.
- [x] 3.2 Perbarui `_broadcast_loop` di `app/main.py`: jika item antrian bertipe `source_type='message'`, langsung render suara pengumuman dan putar dengan audio bed pengiring tanpa mencoba download YouTube. Verifikasi transisi siaran pesan di loop background.
- [x] 3.3 Daftarkan perintah `/pesan` pada `BOT_COMMANDS` di `app/main.py`.

## 4. Pengujian & Deployment

- [x] 4.1 Perbarui unit test di `tests/test_handlers.py` dan `tests/test_audio_engine.py`. Jalankan seluruh suite test dan pastikan lulus 100%.
- [x] 4.2 Re-build dan deploy ulang container Docker `radio-stream-ai` di WSL Ubuntu. Verifikasi eksekusi siaran pesan mandiri di log kontainer.
