# Design: Interactive Telegram Bot & Multi-Source Routing

## Context

Lihat `proposal.md` untuk motivasi. Saat ini `app/handlers.py` mengasumsikan client Spotify selalu terotentikasi saat memproses `/search` dan `/queue`. Selain itu, interaksi Telegram masih berupa chat command teks statis.

## Goals / Non-Goals

**Goals:**
- Menghubungkan `/search` dan `/queue` secara dinamis ke `YouTubeDownloader` saat `MUSIC_SOURCE=youtube`, dan ke `SpotifyClient` saat `MUSIC_SOURCE=spotify`.
- Menyediakan UI interaktif Telegram dengan `InlineKeyboardButton` untuk hasil pencarian dan tombol kontrol cepat pada pesan `/now`.
- Menjaga sistem tetap decoupled dan backward-compatible dengan kedua mode sumber musik.

**Non-Goals:**
- Tidak mengubah skema database SQLite `queue_store.py`.
- Tidak mengubah filter graph ducking audio FFmpeg.

## Alur Audio & Kontrol

```
   Perintah Telegram (/search, /now, tombol klik)
                         │
                         ▼
             ┌─────────────────────────┐
             │       Handlers          │
             └───────────┬─────────────┘
                         │
        ┌────────────────┴────────────────┐
        │ Cek settings.music_source       │
        ▼                                 ▼
┌──────────────────┐            ┌──────────────────┐
│ YouTubeDownloader│            │  SpotifyClient   │
│  (ytsearch5)     │            │  (mode legacy)   │
└────────┬─────────┘            └──────────────────┘
         │
         ▼ (Hasil lagu & metadata)
┌──────────────────────────────────────────────┐
│ InlineKeyboardMarkup (Tombol Klik Telegram)  │
│ [ 1. Lagu A ]  [ 2. Lagu B ]  [ ⏭ Skip ]    │
└──────────────────────────────────────────────┘
                         │ (User klik tombol)
                         ▼
┌──────────────────────────────────────────────┐
│           CallbackQueryHandler               │
│ -> Masuk QueueStore / trigger audio_engine   │
└──────────────────────────────────────────────┘
```

## Decisions

### 1. Ekstraksi Multi-Track via `ytsearchN:` di Downloader
`YouTubeDownloader` menambahkan fungsi `search_multitracks(query, limit=5)`:
- Menjalankan `yt-dlp --dump-json "ytsearch5:<query>"`.
- Membaca setiap baris JSON stream menjadi daftar `TrackMetadata`.
- **Alternatif ditolak:** Memanggil `resolve_query` 5 kali (terlalu lambat).

### 2. Prefix Callback Data untuk Handler Tombol
Event tombol menggunakan format string sederhana dengan prefix:
- `qyt:<video_id>` $\rightarrow$ User memilih lagu dari tombol pencarian YouTube.
- `act:skip` $\rightarrow$ User menekan tombol skip pada pesan `/now`.
- `act:refresh` $\rightarrow$ User memperbarui tampilan `/now`.
- `act:bump:<id>` $\rightarrow$ User mendahulukan lagu di antrian.
- **Rationale:** Ringkas, muat dalam batas 64 byte `callback_data` Telegram.

## Risks / Trade-offs

- **Batas karakter `callback_data` Telegram (64 byte)** $\rightarrow$ Gunakan prefix pendek (`qyt:<id>`) di mana video ID YouTube hanya 11 karakter.
- **Rate-limit pencarian YouTube** $\rightarrow$ Batasi pencarian teks hanya ketika dipicu perintah eksplisit atau button callback.
