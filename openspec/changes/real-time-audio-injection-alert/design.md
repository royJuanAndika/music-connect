# Design

## Context
Lihat `proposal.md` untuk motivasi. Saat ini playback dijalankan via subprocess FFmpeg per lagu (`AudioEngine.play_track_sync`). Menginjeksi audio secara dinamis di tengah proses FFmpeg yang sedang membaca input file secara statis tidak mungkin dilakukan tanpa mematikan proses tersebut atau memakai mekanisme dynamic audio routing.

## Audio Flow Diagram

```text
[Lagu Aktif (PCM stdin / Named Pipe)] ───┐
                                          ├──> [Audio Mixer Node: Ducking / Sidechain] ──> [FFmpeg Encoder Stream]
[Alert TTS (Piper / WAV Buffer)] ────────┘                                                 ├──> HLS (.m3u8/.ts)
                                                                                           └──> RTMP Telegram
```

Ketika ada alert masuk:
1. Jalur musik menerima signal ducking (skala volume diturunkan ke 0.25).
2. Audio alert dimix bersama musik secara sinkron.
3. Setelah alert selesai, volume musik kembali perlahan ke 1.0 (smooth fade).

## Goals / Non-Goals

**Goals:**
- Mengizinkan injeksi audio alert (pesan suara / salam) secara langsung ke siaran yang sedang berjalan dalam hitungan detik.
- Menjaga koneksi RTMP Telegram dan segmen HLS stabil tanpa reload container atau restart streaming process.
- Menyediakan mekanisme queue alert in-memory yang non-blocking terhadap antrean lagu utama.

**Non-Goals:**
- Mengganti seluruh stack ke server streaming terpisah yang rumit (seperti setup Icecast/Liquidsoap multi-port).
- Mengubah alur request lagu YouTube di `QueueStore`.

## Decisions

### 1. Dedicated Live Alert Injection via Named Pipe / Unix Domain Socket (atau Frame Multiplexer)
- **Keputusan:** Menggunakan FFmpeg dengan dual input pipe atau named pipe (FIFO) untuk alert stream. Input 0 adalah audio musik yang sedang berjalan, Input 1 adalah named pipe alert yang selalu terbuka (`-f s16le` atau `-f wav` via live pipe). Ketika ada pesan suara, TTS menulis data audio ke alert pipe. Filter `sidechaincompress` atau `amix` di FFmpeg langsung merespons stream tersebut.
- **Alternatif dipertimbangkan:** 
  - *Full in-memory PCM mixing di Python:* Mengonsumsi CPU lebih tinggi untuk encoding ulang di Python.
  - *Liquidsoap engine terpisah:* Membutuhkan install dependency sistem besar OCaml/Liquidsoap di VPS dan rewrite config total.
  - *FIFO / Named Pipe alert:* Tetap menggunakan binary FFmpeg yang sudah ada, efisien, dan native Linux.

### 2. Handler Telegram Mengirim ke `AlertManager`
- **Keputusan:** `/pesan` dan `/salam` tidak lagi memanggil `queue_store.add(...)` sebagai track `message`. Handler langsung memicu task `alert_manager.enqueue_alert(...)` yang memproses naskah LLM -> render Piper TTS -> kirim ke alert stream secara asinkron.

### 3. Environment Variables
- `ALERT_DUCK_LEVEL`: `0.25` (Level volume musik saat ada alert berbicara).
- `ALERT_ATTACK_MS`: `15` (Kecepatan musik mengecil saat suara masuk).
- `ALERT_RELEASE_MS`: `400` (Kecepatan musik kembali normal setelah suara selesai).

## Risks / Trade-offs

- **[Risk]** Pipe blocking / buffer overflow jika named pipe tidak dikonsumsi FFmpeg secara lancar.  
  → **Mitigation:** Gunakan non-blocking I/O atau async writer di Python dengan timeout.
- **[Risk]** Delay sintesis TTS Piper + LLM.  
  → **Mitigation:** Jalankan sintesis LLM + Piper di background task terpisah dan putar jingle pembuka alert pendek (0.5s) jika diperlukan buffer time.
