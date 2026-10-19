# Design: Radio FM DJ Voice & Stream Stability

## Context

Lihat `proposal.md` untuk motivasi. Saat ini siaran Telegram RTMPS terputus ketika antrian kosong karena FFmpeg berhenti, dan AI Host belum aktif karena dependensi binary Piper yang rumit untuk environment VPS.

## Goals / Non-Goals

**Goals:**
- Menjamin siaran Telegram Live tidak putus saat antrian pending kosong (siaran standby/filler).
- Mengoptimalkan argumen muxing FFmpeg untuk koneksi RTMPS Telegram yang stabil.
- Mengintegrasikan engine `edge-tts` (suara Microsoft Neural Bahasa Indonesia: `id-ID-ArdiNeural` / `id-ID-GadisNeural`) tanpa butuh binary compile lokal.
- Mendukung penangkapan target penerima salam (`shoutout_to`) dan mengintegrasikannya ke prompt naskah DJ FM.

**Non-Goals:**
- Tidak mengubah frontend pemutar web `hls.js`.
- Tidak menghapus dukungan Piper TTS lama (tetap ada sebagai opsi `TTS_ENGINE=piper`).

## Alur Audio & Pemrosesan Siaran

```
                     Request Masuk (/salam judul | target | pesan)
                                          │
                                          ▼
                               ┌─────────────────────┐
                               │  QueueStore (DB)    │
                               │  - shoutout_to      │
                               │  - shoutout_message │
                               └──────────┬──────────┘
                                          │
                   ┌──────────────────────┴──────────────────────┐
                   ▼ (Ada antrian)                               ▼ (Antrian Kosong)
       ┌────────────────────────┐                    ┌────────────────────────┐
       │   Track Lagu YouTube   │                    │   Standby Tone / Loop  │
       │  (data/tracks/<id>)    │                    │ (jingle / silence 5s)  │
       └───────────┬────────────┘                    └───────────┬────────────┘
                   │                                             │
                   ▼                                             │
       ┌────────────────────────┐                                │
       │ LLM DJ Radio FM Naskah │                                │
       │ (Pengirim + Target)    │                                │
       └───────────┬────────────┘                                │
                   ▼                                             │
       ┌────────────────────────┐                                │
       │ edge-tts (Neural Voice)│                                │
       │ id-ID-ArdiNeural (WAV) │                                │
       └───────────┬────────────┘                                │
                   │                                             │
                   ▼                                             │
       ┌─────────────────────────────────────────────────────────┴────────┐
       │                     FFmpeg Broadcast Engine                      │
       │                                                                  │
       │  Filter Ducking:                                                 │
       │  [0:a][1:a] sidechaincompress (ducking) -> amix -> [out]         │
       │                                                                  │
       │  Keluaran RTMPS Dioptimalkan:                                    │
       │  -max_muxing_queue_size 9999 -fps_mode cfr                       │
       │  -g 30 -keyint_min 30 -sc_threshold 0 -maxrate 250k -bufsize 500k│
       └──────────────────────────────────┬───────────────────────────────┘
                                          ▼
                             Telegram Live Channel / Group
```

## Decisions

### 1. Engine TTS Default Menggunakan `edge-tts`
- **Rationale:** Ringan, kualitas suara natural seperti penyiar manusia, langsung jalan di Python via pip tanpa kompilasi C++ di Docker/VPS.
- Pilihan suara di `.env`: `TTS_VOICE=id-ID-ArdiNeural` (pria) atau `id-ID-GadisNeural` (wanita).
- **Alternatif ditolak:** Piper lokal (suara lebih kaku, butuh binary executable OS-spesifik).

### 2. Penanganan Antrian Kosong (Keep-Alive Stream)
Saat antrian pending habis:
- `_broadcast_loop` tidak langsung sleep dan mematikan FFmpeg, melainkan memutar segmen standby pendek atau audio jingle radio radio standby selama 5–10 detik.
- Begitu request baru masuk, loop langsung beralih memutar request tersebut.
- **Rationale:** Menjaga soket RTMPS Telegram tetap *ESTABLISHED* sehingga tidak muncul status "Live Ended" di Telegram.

### 3. Parsing Format Salam dengan Target
Perintah `/salam` mendukung format fleksibel:
- `/salam <Lagu> | untuk <Target> | <Pesan>`
- `/salam <Lagu> | <Pesan>` (jika tanpa target, target dianggap "seluruh pendengar/teman-teman").

## Environment Variables Baru

```env
TTS_ENGINE=edge-tts
TTS_VOICE=id-ID-ArdiNeural
HOST_ENABLED=true
HOST_PERSONA=Penyiar radio FM anak muda yang seru, ramah, dan santai
STANDBY_AUDIO_PATH=
```

## Risks / Trade-offs

- **Dependensi Internet untuk TTS (`edge-tts`)** $\rightarrow$ Graceful fallback: bila koneksi TTS gagal, lagu tetap diputar tanpa host tanpa memutus siaran.
- **Latency Edge-TTS** $\rightarrow$ Rata-rata hanya 300–600ms, di-cache lokal di `data/voice/`.
