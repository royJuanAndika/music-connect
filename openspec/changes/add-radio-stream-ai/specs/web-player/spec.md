# Spec Delta: web-player

## Purpose

Menyediakan antarmuka web bagi pendengar untuk mendengarkan siaran secara sinkron, melihat informasi siaran langsung (now playing dan antrian), serta mengirimkan permintaan lagu.

## ADDED Requirements

### Requirement: Pemutar Audio Web Sinkron
Sistem SHALL menyajikan pemutar audio berbasis peramban (browser) yang memutar aliran siaran HLS secara sinkron, sehingga semua pendengar web mendengar bagian audio yang sama pada waktu yang hampir bersamaan.

#### Scenario: Pendengar membuka halaman web
- **WHEN** pendengar mengakses URL pemutar web di peramban
- **THEN** pemutar memuat berkas playlist HLS dan mulai memutar siaran langsung

### Requirement: Tampilan Now Playing dan Antrian
Sistem SHALL menyediakan antarmuka dan endpoint data yang menyajikan informasi lagu yang sedang diputar (judul, artis, cover/thumbnail), status host (sedang bicara atau tidak), dan daftar antrian berikutnya.

#### Scenario: Informasi lagu berubah saat lagu berganti
- **WHEN** sebuah lagu baru mulai diputar di aliran siaran
- **THEN** tampilan judul, artis, dan cover di halaman web diperbarui secara otomatis tanpa memuat ulang halaman

### Requirement: Teks Salam yang Sedang Dibacakan
Sistem SHALL menampilkan teks titip salam yang sedang dibacakan oleh host di halaman web agar pendengar dapat membaca pesan tersebut.

#### Scenario: Host membacakan salam
- **WHEN** host sedang membacakan salam dari pendengar
- **THEN** teks salam tersebut tampil pada kotak informasi siaran di halaman web

### Requirement: Form Request Terintegrasi
Sistem SHALL menyediakan form di halaman web bagi pendengar untuk memasukkan judul lagu/URL dan pesan salam tanpa perlu memiliki akun atau menggunakan Telegram.

#### Scenario: Mengirim request dari halaman pemutar
- **WHEN** pendengar mengisi kolom judul lagu dan salam di form web lalu menekan tombol kirim
- **THEN** request diproses ke antrian siaran dan status penerimaan ditampilkan di halaman tersebut
