# Spec Delta: listener-requests

## Purpose

Mengatur penerimaan permintaan lagu dan titip salam dari pendengar melalui Telegram dan web, termasuk antrian, kuota per pengguna, dan moderasi konten.

## ADDED Requirements

### Requirement: Penerimaan Request dari Telegram
Sistem SHALL menerima permintaan lagu dari pendengar melalui bot Telegram, baik berupa perintah eksplisit maupun teks bahasa natural, dan menambahkannya ke antrian siaran.

#### Scenario: Request lagu via Telegram
- **WHEN** pendengar mengirim permintaan lagu melalui Telegram
- **THEN** lagu ditambahkan ke antrian dan pengirim menerima konfirmasi berisi posisi antrian

### Requirement: Penerimaan Request dari Web
Sistem SHALL menerima permintaan lagu dan titip salam melalui form web publik selama `WEB_REQUESTS_OPEN` bernilai true.

#### Scenario: Request lagu via web
- **WHEN** pendengar mengisi form web dengan judul lagu dan menekan kirim
- **THEN** lagu ditambahkan ke antrian dan halaman menampilkan konfirmasi posisi antrian

#### Scenario: Request web ditutup
- **WHEN** `WEB_REQUESTS_OPEN=false`
- **THEN** sistem menolak pengiriman form dan menampilkan pesan bahwa request sedang ditutup

### Requirement: Titip Salam
Sistem SHALL menerima pesan titip salam bersama request dan menyimpannya agar dapat dibacakan oleh AI Host, dengan panjang maksimal `SHOUTOUT_MAX_CHARS` (default 200 karakter).

#### Scenario: Salam melebihi batas panjang
- **WHEN** pesan salam melebihi batas karakter yang dikonfigurasi
- **THEN** sistem memotong atau menolak pesan dan memberi tahu pengirim batasnya

### Requirement: Kuota dan Cooldown Request
Sistem SHALL membatasi jumlah request pending per pengguna sebesar `MAX_QUEUE_PER_USER` (default 3) dan total antrian sebesar `MAX_QUEUE_TOTAL` (default 20), serta menerapkan jeda `REQUEST_COOLDOWN_SEC` (default 30 detik) antar request dari pengguna yang sama.

#### Scenario: Pengguna melebihi kuota request
- **WHEN** pengguna sudah memiliki jumlah request pending yang mencapai `MAX_QUEUE_PER_USER`
- **THEN** sistem menolak request baru dengan pesan bahwa kuota belum tersedia

#### Scenario: Request terlalu cepat
- **WHEN** pengguna mengirim request baru sebelum jeda cooldown berakhir
- **THEN** sistem menolak request dan memberi tahu sisa waktu tunggu

### Requirement: Moderasi Konten
Sistem SHALL memfilter judul lagu dan pesan salam terhadap daftar `BANNED_WORDS`, dan menolak atau menyaring konten yang mengandung kata terlarang.

#### Scenario: Salam mengandung kata terlarang
- **WHEN** pesan salam mengandung kata yang ada dalam `BANNED_WORDS`
- **THEN** sistem menolak salam tersebut dan tidak meneruskannya untuk dibacakan host
