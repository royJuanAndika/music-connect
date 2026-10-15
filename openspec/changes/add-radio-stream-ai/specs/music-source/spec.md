# Spec Delta: music-source

## Purpose

Mengatur resolusi sumber musik dari YouTube (URL atau teks pencarian), mengunduh audio ke cache lokal, dan menegakkan batas durasi serta larangan live stream untuk siaran radio.

## ADDED Requirements

### Requirement: YouTube URL and Text Search Resolution
Sistem SHALL mendukung penerimaan input lagu berupa URL langsung YouTube (`youtube.com/watch?v=...`, `youtu.be/...`) maupun kueri pencarian teks bebas (misal: "Sheila on 7 Dan"). Bila menerima teks pencarian, sistem SHALL memilih hasil teratas yang relevan.

#### Scenario: Input berupa URL YouTube yang valid
- **WHEN** pengguna mengirimkan link video YouTube yang valid
- **THEN** sistem mengekstrak metadata (judul, artis/uploader, durasi, thumbnail) dan mengunduh audio track ke penyimpanan lokal

#### Scenario: Input berupa kueri pencarian teks
- **WHEN** pengguna mengirimkan judul dan artis lagu dalam teks biasa
- **THEN** sistem menjalankan pencarian YouTube dan mengambil hasil pertama yang cocok untuk diunduh

### Requirement: Durasi Maksimal dan Pencegahan Live Stream
Sistem SHALL menolak lagu yang durasinya melebihi batas `YT_MAX_DURATION_SEC` (default 600 detik) atau yang berstatus siaran langsung (live stream).

#### Scenario: Lagu melebihi batas durasi maksimal
- **WHEN** lagu yang diminta memiliki durasi lebih dari 10 menit (misal podcast 1 jam)
- **THEN** sistem menolak permintaan dan mengembalikan pesan bahwa durasi lagu terlalu panjang

#### Scenario: Link adalah live stream yang sedang aktif
- **WHEN** pengguna mengirimkan URL YouTube Live
- **THEN** sistem menolak permintaan dengan pesan bahwa siaran langsung tidak dapat diputar di radio

### Requirement: Cache Audio Lokal
Sistem SHALL menyimpan audio hasil unduhan di direktori cache lokal dengan penamaan berbasis ID video. Jika ID video sudah ada di cache, sistem SHALL langsung menggunakan file lokal tanpa mengunduh ulang dari internet.

#### Scenario: Request lagu yang sudah ada di cache
- **WHEN** lagu diminta dan filenya sudah tersimpan di direktori cache
- **THEN** sistem langsung memasukkannya ke antrian tanpa memicu proses unduh jaringan baru
