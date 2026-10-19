# Tasks: Live Audio Overlay for Admin Announcements

## 1. Konfigurasi Grup & Keamanan

- [x] 1.1 Perbarui `ALLOWED_GROUP_IDS` menjadi `-1003946103740` di `.env`, `.env.example`, dan VPS.

## 2. Audio Engine & Transisi Pesan (`app/audio_engine.py`)

- [x] 2.1 Tambahkan flag `-shortest` pada `build_message_cmd` agar FFmpeg keluar seketika begitu audio ucapan selesai dan tidak menggantung.
- [x] 2.2 Sempurnakan `play_message_sync` agar mengisolasi error terminasi dan memastikan transisi kembali ke antrian lagu normal berjalan mulus.

## 3. Integrasi Perintah Pesan (`app/handlers.py`)

- [x] 3.1 Perbaiki `cmd_pesan` di `app/handlers.py` agar menyiarkan pesan ke antrian terdepan dan memicu pemutaran pesan tanpa menyebabkan dead-lock pada proses siaran.

## 4. Pengujian & Deployment ke VPS

- [ ] 4.1 Jalankan seluruh suite test di `tests/test_audio_engine.py` dan `tests/test_handlers.py`.
- [ ] 4.2 Push perubahan ke remote GitHub dan rebuild/restart container di VPS. Verifikasi log kontainer berjalan mulus di grup `-1003946103740`.
