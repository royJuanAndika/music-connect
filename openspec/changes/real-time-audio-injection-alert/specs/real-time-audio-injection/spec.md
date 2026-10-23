# Spec Delta

## Purpose
Menyediakan kemampuan injeksi audio pesan dan salam secara instan dan real-time ke dalam stream siaran live yang sedang berlangsung dengan efek volume ducking otomatis tanpa memutus audio lagu maupun stream RTMP/HLS.

## ADDED Requirements

### Requirement: Real-time Audio Alert Injection
Sistem SHALL mampu menerima permintaan suara (pesan/salam) dan memutarkannya di atas musik yang sedang berjalan dalam waktu kurang dari 3 detik tanpa menunggu pergantian lagu.

#### Scenario: Pesan masuk saat lagu sedang berputar
- **WHEN** pengguna atau admin mengirimkan perintah `/pesan` atau `/salam` saat lagu sedang diputar
- **THEN** audio pesan suara langsung disintesis oleh Piper TTS dan disuntikkan ke stream siaran yang sedang berjalan tanpa menunggu lagu selesai

### Requirement: Dynamic Music Ducking on Alert
Sistem SHALL secara otomatis menurunkan volume background musik (ducking) saat audio alert sedang berbicara dan menaikkannya kembali ke tingkat normal setelah audio alert selesai.

#### Scenario: Ducking otomatis selama pesan bersuara
- **WHEN** audio pesan suara mulai dimainkan pada live stream
- **THEN** volume musik yang sedang berjalan otomatis turun ke rentang 20-30% volume normal, suara pesan terdengar jernih di latar depan, dan volume musik kembali ke 100% setelah pesan selesai

### Requirement: Stream Continuity Preservation
Sistem SHALL menjaga kontinuitas stream RTMP Telegram dan segmen HLS Web tanpa buffering ulang atau pemutusan koneksi saat alert disuntikkan.

#### Scenario: Tidak ada restart subprocess yang memutus koneksi
- **WHEN** injeksi audio alert berlangsung atau selesai
- **THEN** koneksi RTMP Telegram dan file segmen HLS tetap berlanjut secara kontinu tanpa interupsi socket
