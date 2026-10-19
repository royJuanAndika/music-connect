# Tasks: Radio FM DJ Voice & Stream Stability

## 1. Integrasi Engine Suara Neural (`app/tts.py` & Dependensi)

- [x] 1.1 Tambahkan dependensi `edge-tts` pada `requirements.txt` dan `Dockerfile`. Verifikasi instalasi paket dapat diimpor tanpa error.
- [x] 1.2 Perbarui `app/tts.py`: implementasikan provider `EdgeTTS` dengan dukungan suara `id-ID-ArdiNeural` / `id-ID-GadisNeural`, serta fallback otomatis bila offline. Verifikasi fungsi sintesis menghasilkan berkas audio suara WAV/MP3 yang valid.
- [x] 1.3 Tambahkan konfigurasi `TTS_VOICE` dan default `TTS_ENGINE=edge-tts` pada `app/config.py` dan `.env.example`. Verifikasi pemuatan konfigurasi baru melalui `load_settings()`.

## 2. Peningkatan Naskah DJ Radio FM & Target Salam (`app/llm.py` & `app/handlers.py`)

- [x] 2.1 Perbarui skema dan penanganan `QueueStore` di `app/queue_store.py` untuk menyimpan atribut target salam (`shoutout_to`). Verifikasi field tersimpan di database SQLite.
- [x] 2.2 Perbarui parsing perintah `/salam` di `app/handlers.py`: dukung format `/salam <Lagu> | untuk <Target> | <Pesan>` serta format 2 bagian lama. Verifikasi ekstraksi target penerima salam.
- [x] 2.3 Perbarui prompt penyusunan naskah DJ di `app/llm.py` agar menyertakan konteks pengirim, target penerima, salam, dan gaya penyiar radio FM anak muda yang ceria. Verifikasi naskah yang dihasilkan menyebutkan target salam dengan tepat.

## 3. Optimalisasi Parameter RTMP & Aliran Siaran Kontinu (`app/audio_engine.py` & `app/main.py`)

- [x] 3.1 Perbarui peracikan perintah FFmpeg RTMPS di `app/audio_engine.py`: tambahkan `-max_muxing_queue_size 9999`, `-fps_mode cfr`, keyframe interval tetap (`-g 30 -keyint_min 30 -sc_threshold 0`), dan buffer limit. Verifikasi string perintah FFmpeg yang dihasilkan.
- [x] 3.2 Implementasikan mekanisme siaran standby di `app/main.py`: bila antrian lagu kosong, putar trek standby pendek / radio standby loop agar soket RTMP Telegram tetap terjaga tanpa terputus. Verifikasi transisi dari standby saat request baru masuk.

## 4. Verifikasi Test Suite & Deployment

- [x] 4.1 Perbarui unit test di `tests/test_tts_llm.py`, `tests/test_audio_engine.py`, dan `tests/test_queue_store.py`. Jalankan seluruh suite test dan pastikan lulus 100%.
- [x] 4.2 Re-build dan perbarui container Docker `radio-stream-ai` di WSL Ubuntu dengan `edge-tts` aktif. Verifikasi log kontainer berjalan mulus di Portainer.
