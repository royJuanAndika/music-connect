# Design: Admin Message Broadcast & Radio Bed Ducking

## Context

Lihat `proposal.md` untuk motivasi. Saat ini siaran hanya memproses item bertipe lagu YouTube. Kita membutuhkan kemampuan untuk menyiarkan pesan pengumuman suara mandiri khusus Admin diiringi musik latar instrumental yang melirih (Radio Bed).

## Goals / Non-Goals

**Goals:**
- Menambahkan perintah `/pesan` dengan otorisasi Admin (`ALLOWED_TELEGRAM_IDS`).
- Menghasilkan audio pembacaan pesan menggunakan `edge-tts` (didukung fallback template naskah radio FM bila LLM offline).
- Memutar audio pengiring (Radio Bed) menggunakan generator sintesis atau audio instrumental dengan dynamic ducking FFmpeg (`sidechaincompress` ke 20%).

**Non-Goals:**
- Tidak mengizinkan non-admin menyiarkan pesan tanpa lagu.

## Alur Audio Pesan Mandiri (Radio Bed)

```
       Admin kirim /pesan untuk <Target> | <Isi Pesan>
                             │
                             ▼
              Otorisasi (ALLOWED_TELEGRAM_IDS)
                             │
                             ▼
                QueueStore (source_type='message')
                             │
                             ▼
         ┌───────────────────┴───────────────────┐
         ▼                                       ▼
 1. Audio Bed / Background           2. Naskah DJ & edge-tts
    (Instrumental / Synth Loop)         (Suara Host WAV)
         │                                       │
         │ [0:a] (Musik Latar)                   │ [1:a] (Voice)
         └───────────────────┬───────────────────┘
                             │
                             ▼
      ┌─────────────────────────────────────────────────────┐
      │               FFmpeg Broadcast Engine               │
      │                                                     │
      │   Filter Graph:                                     │
      │   [0:a][1:a] sidechaincompress=threshold=0.20:     │
      │   ratio=8:attack=150:release=600 [ducked];          │
      │   [ducked][1:a] amix=inputs=2:duration=first [out]  │
      │                                                     │
      │   (Volume musik latar melirih saat host bicara)     │
      └──────────────────────┬──────────────────────────────┘
                             │
                             ▼
               Telegram Live & HLS Web Player
```

## Decisions

### 1. Guard Akses Admin Eksplisit
Perintah `/pesan` memeriksa `user.id in self.settings.allowed_telegram_ids`.
- Jika bukan admin: tolak dengan pesan *"⛔ Maaf, siaran pengumuman radio hanya dapat dilakukan oleh Admin."*

### 2. Audio Bed Generator Sintetis Bawaan FFmpeg
Jika tidak ada file mp3 instrumental khusus di server:
- Gunakan filter generator audio FFmpeg `sine / aevalsrc` atau tone harmonik santai pendek dengan envelope halus sehingga sistem **mandiri tanpa wajib mengunduh file audio luar**.
- Jika operator meletakkan file `data/radio_bed.mp3`, sistem otomatis mengutamakan file tersebut.

### 3. Fallback Naskah Otomatis (Anti-Hening)
Jika LLM API key kosong, sistem menyusun naskah penyiar radio FM otomatis:
`"Halo sobat radio yang lagi standby! Ada pengumuman spesial dari Admin [Nama] untuk [Target]: '[Pesan]'. Sekian info dari kami, selamat beraktivitas kembali!"`

## Risks / Trade-offs

- **Durasi Audio Bed** $\rightarrow$ Disesuaikan otomatis dengan panjang suara penyiar (`duration=first` pada audio voice + padding 2 detik).
