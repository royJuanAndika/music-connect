# Spec Delta: Live Pesan Broadcast

## Purpose
Menyediakan mekanisme penyiaran pesan interupsi atau pengumuman suara seketika di atas backing track radio bed yang andal dan terdengar jelas di stream siaran.

## ADDED Requirements

### Requirement: Instant Announcement Playback
Sistem siaran SHALL memutar pesan pengumuman suara yang di-generate dari perintah `/pesan` melalui `play_message_sync` dengan durasi siaran yang persis sama dengan panjang audio pesan suara.

#### Scenario: Admin message broadcast execution
- **WHEN** item antrian bertipe pesan pengumuman diproses oleh loop siaran
- **THEN** audio engine memutar pesan suara host menggunakan audio backing bed yang valid dan mengalirkan audionya ke HLS dan RTMP secara sinkron

### Requirement: Harmonious Radio Bed Background
Sistem siaran audio SHALL mencampur suara pesan penyiar dengan radio bed latar belakang (file audio loop atau generator frekuensi harmonik santai) dengan ducking otomatis saat penyiar menyampaikan pesan.

#### Scenario: Radio bed ambient during message
- **WHEN** audio pesan diputar tanpa file audio bed eksternal
- **THEN** audio engine menghasilkan nada latar ambient harmonik rendah yang terkompresi lembut saat suara pesan terdengar jelas di layer depan
