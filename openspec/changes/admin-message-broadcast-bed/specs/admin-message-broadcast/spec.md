# Spec Delta: admin-message-broadcast

## Purpose

Menyediakan fitur siaran pesan dan salam mandiri khusus Administrator yang diiringi musik latar instrumental otomatis dengan dynamic audio ducking.

## ADDED Requirements

### Requirement: Otorisasi Khusus Administrator untuk Siaran Pesan
Sistem SHALL membatasi eksekusi perintah siaran pesan mandiri (`/pesan`) hanya untuk pengguna yang ID Telegram-nya terdaftar di dalam `ALLOWED_TELEGRAM_IDS`. Pengguna yang tidak terdaftar SHALL ditolak dengan pesan peringatan.

#### Scenario: Admin mengirim perintah pesan mandiri
- **WHEN** seorang pengguna yang terdaftar dalam `ALLOWED_TELEGRAM_IDS` mengeksekusi `/pesan untuk Tim IT | Tetap semangat deploy!`
- **THEN** sistem menerima pesan tersebut dan menambahkannya ke antrian siaran dengan tipe `message`

#### Scenario: Pengguna non-admin mencoba mengirim pesan mandiri
- **WHEN** seorang pengguna yang tidak terdaftar dalam `ALLOWED_TELEGRAM_IDS` mengeksekusi `/pesan Halo semua`
- **THEN** sistem menolak permintaan dan mengembalikan pesan bahwa fitur pengumuman siaran hanya untuk Administrator

### Requirement: Siaran Pesan dengan Musik Latar dan Ducking
Sistem SHALL memutar audio pengumuman penyiar di atas alunan musik latar instrumental (Radio Bed). Selama penyiar berbicara, volume musik latar SHALL mengecil secara otomatis (ducking) ke level yang ditentukan dan kembali normal saat ucapan selesai.

#### Scenario: Pemutaran pesan mandiri di aliran siaran
- **WHEN** giliran antrian dengan tipe `message` diproses oleh siaran
- **THEN** sistem memutar musik latar dan suara penyiar secara bersamaan dengan ducking, lalu melanjutkan ke antrian berikutnya setelah pesan selesai
