# Spec Delta: fifo-streaming

## Purpose

Menetapkan persyaratan ketahanan transmisi RTMP menggunakan FIFO buffer wrapper FFmpeg untuk mencegah pemutusan siaran akibat packet loss dan buffer overflow.

## ADDED Requirements

### Requirement: Penanganan Buffer Overflow Menggunakan FIFO Muxer
Sistem SHALL membungkus aliran keluaran RTMP menggunakan format antrian FIFO (`-f fifo -fifo_format flv`) dengan opsi `drop_pkts_on_overflow=1`, sehingga saat terjadi hambatan transmisi jaringan, paket video non-kritis dapat dibuang tanpa mematikan proses siaran.

#### Scenario: Terjadi hambatan throughput jaringan internasional
- **WHEN** buffer soket jaringan TCP penuh akibat fluktuasi koneksi ke server Telegram
- **THEN** FFmpeg membuang paket yang meluap dan tetap melanjutkan transmisi audio secara real-time tanpa melempar error Broken Pipe

### Requirement: Pemulihan Koneksi Otomatis (Auto-Recovery)
Sistem SHALL mengonfigurasi percobaan pemulihan koneksi otomatis (`attempt_recovery=1`) dengan waktu tunggu 1 detik (`recovery_wait_time=1`) pada keluaran RTMP.

#### Scenario: Soket RTMPS terputus sesaat
- **WHEN** koneksi jaringan ke endpoint Telegram terputus secara tidak terduga
- **THEN** FIFO muxer mencoba menyambungkan kembali soket dalam 1 detik tanpa membatalkan atau mematikan proses pemutaran lagu yang sedang berjalan
