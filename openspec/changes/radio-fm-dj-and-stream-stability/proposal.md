# Proposal: Radio FM DJ Voice & Stream Stability

## Why

Siaran Telegram Live saat ini rentan terputus saat antrian lagu kosong atau ketika terjadi lonjakan buffer jaringan karena parameter RTMP FFmpeg belum dioptimalkan untuk transmisi RTMPS Telegram. Di sisi lain, fitur AI Host saat ini masih nonaktif dan belum mendukung pembacaan titip salam terstruktur yang menyebutkan target penerima secara luwes layaknya penyiar radio FM profesional dengan suara natural yang ringan untuk lingkungan VPS.

Perubahan ini diperlukan untuk menjamin stabilitas siaran 24/7 (anti-putus saat antrian kosong) serta menghadirkan AI Host dengan suara neural alami (`edge-tts`) yang membacakan request lagu dan titip salam ke target spesifik dengan gaya penyiar radio FM anak muda.

## What Changes

- **Stabilitas Aliran Siaran Kontinu (Anti-Putus):**
  - **Loop Siaran Saat Antrian Kosong:** Saat antrian `pending` kosong, sistem tidak langsung mematikan proses siaran RTMP, melainkan memutar audio jeda/jingle standby atau mempertahankan koneksi stream agar sesi Telegram Live tidak putus (*broken pipe*).
  - **Optimalisasi Argumen FFmpeg RTMPS:** Menambahkan `-max_muxing_queue_size 9999`, `-fps_mode cfr`, keyframe interval konstan (`-g 30 -keyint_min 30 -sc_threshold 0`), serta batas buffer (`-bufsize 500k`) untuk mencegah buffering dan drop koneksi di server Telegram.
- **Penyiar Radio AI FM (DJ Persona) & Target Salam:**
  - **Ekstraksi Target Salam:** Mendukung struktur salam dengan target penerima (mis. `/salam <Lagu> | untuk <Target> | <Pesan>`) baik via perintah teks maupun bahasa natural AI.
  - **Penyusunan Naskah DJ Radio FM:** LLM menyusun naskah yang membacakan salam, menyebutkan pengirim, target penerima, pesan hangat, dan transisi ke lagu berikutnya secara natural.
  - **Sintesis Suara Neural VPS-Ready (`edge-tts`):** Menambahkan engine TTS berbasis Microsoft Edge Neural (`id-ID-ArdiNeural` / `id-ID-GadisNeural`) yang gratis, berkualitas manusiawi, dan tanpa kebutuhan kompilasi binary C++ berat di VPS.

### Yang Dipertahankan (re-use)
- Logika dynamic ducking FFmpeg (`sidechaincompress`).
- Antarmuka Web Player HLS dan REST API.
- Struktur antrian SQLite (`queue_store.py`) dan sistem moderasi kata terlarang.
- Komponen bot Telegram dan tombol interaktif yang sudah ada.

### Yang Diubah (refactor)
- `app/tts.py`: Menambahkan provider `edge-tts` sebagai alternatif/pengganti Piper lokal.
- `app/llm.py`: Memperbarui prompt generator DJ radio FM untuk menyertakan target penerima salam.
- `app/handlers.py`: Memperbarui parsing perintah `/salam` agar mengenali parameter target salam.
- `app/audio_engine.py`: Menyempurnakan parameter muxing, buffer, dan framerate FFmpeg RTMPS.
- `app/main.py`: Menambahkan penanganan siaran standby saat antrian kosong agar RTMP tidak terputus mendadak.

### Yang Baru
- Pengaturan konfigurasi `TTS_ENGINE=edge-tts` dan `TTS_VOICE=id-ID-ArdiNeural` di `config.py` dan `.env.example`.

## Capabilities

### New Capabilities
- `stream-stability`: Pengaturan aliran siaran berkelanjutan dengan pencegahan disconnect saat antrian kosong dan optimasi buffer RTMP/RTMPS.
- `radio-fm-dj-voice`: Pembacaan naskah penyiar radio dengan target salam terstruktur dan sintesis suara neural alami berbasis `edge-tts`.

### Modified Capabilities
- (Tidak ada) — Belum ada baseline spec di `openspec/specs/`.

## Impact

- **Kode yang terpengaruh:** `app/tts.py`, `app/audio_engine.py`, `app/main.py`, `app/handlers.py`, `app/llm.py`, `app/config.py`, `Dockerfile`, `requirements.txt`.
- **Dependensi baru:** `edge-tts` pada `requirements.txt`.
- **Lingkungan Deployment:** Sangat ideal untuk VPS tanpa memerlukan file model onnx besar secara lokal.

## Non-goals

- **Bukan** pengalihan siaran menjadi streaming video kamera live; visual tetap menggunakan synthetic canvas/thumbnail cover art.
- **Bukan** layanan percakapan 2 arah real-time dengan penyiar (pendengar tetap berinteraksi lewat teks).
- **Bukan** sistem billing berbayar untuk request prioritas.
