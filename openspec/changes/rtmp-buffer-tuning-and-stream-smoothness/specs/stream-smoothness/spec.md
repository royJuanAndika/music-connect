# Spec Delta: stream-smoothness

## Purpose

Menetapkan parameter transmisi video sintetis dan penyangga buffer RTMP FFmpeg agar aliran audio siaran Telegram Live berjalan mulus tanpa micro-buffering.

## ADDED Requirements

### Requirement: Standar Framerate Minimum untuk Decoder Telegram
Sistem SHALL menghasilkan aliran video sintetis kanvas dengan framerate minimum 15 frame per detik (fps) dan interval keyframe (GOP) tepat setiap 2 detik.

#### Scenario: Transmisi siaran ke endpoint RTMP Telegram
- **WHEN** siaran audio dipancarkan ke endpoint RTMP Telegram
- **THEN** aliran video menggunakan 15 fps dengan parameter `-g 30 -keyint_min 30` sehingga decoder klien Telegram tidak mengalami kelaparan frame (frame starvation)

### Requirement: Pembatasan Bitrate Konstan (CBR)
Sistem SHALL menerapkan batas maksimum bitrate video (`maxrate`) dan ukuran buffer (`bufsize`) yang proporsional guna mencegah fluktuasi lonjakan paket jaringan ke server Telegram.

#### Scenario: Terjadi variasi bandwidth jaringan
- **WHEN** paket video dan audio dikirimkan melalui koneksi TCP RTMP
- **THEN** bitrate video dikunci pada level konstan (100 kbps) dengan buffer ceiling (200 kbps) untuk menjaga kestabilan aliran audio
