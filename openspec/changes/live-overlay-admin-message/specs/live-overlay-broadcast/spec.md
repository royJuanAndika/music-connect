# Spec Delta: live-overlay-broadcast

## Purpose

Menyediakan kemampuan bagi siaran radio untuk menyisipkan audio pesan pengumuman suara langsung di tengah pemutaran lagu dengan penurunan volume musik dinamis tanpa memutus aliran stream RTMP.

## ADDED Requirements

### Requirement: Penyisipan Pesan Tanpa Mematikan Siaran Lagu
Sistem SHALL menyiarkan pesan pengumuman suara dari Administrator langsung di atas lagu yang sedang mengudara tanpa menghentikan subproses siaran atau mereset koneksi jaringan RTMPS Telegram.

#### Scenario: Admin mengirim pesan saat lagu sedang diputar
- **WHEN** Administrator mengeksekusi perintah `/pesan <Isi Pesan>` saat sebuah lagu sedang mengudara
- **THEN** sistem langsung merender audio ucapan pesan dan menyisipkannya ke dalam aliran siaran lagu tersebut, menurunkan volume lagu sementara waktu (ducking), lalu mengembalikan volume lagu ke level normal setelah pesan selesai

#### Scenario: Admin mengirim pesan saat siaran standby
- **WHEN** Administrator mengeksekusi perintah `/pesan <Isi Pesan>` saat tidak ada lagu yang diputar
- **THEN** sistem menyiarkan pesan tersebut dengan iringan musik latar Radio Bed secara mandiri
