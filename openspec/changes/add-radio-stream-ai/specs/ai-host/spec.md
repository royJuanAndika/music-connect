# Spec Delta: ai-host

## Purpose

Mendefinisikan perilaku AI Host radio: menyusun naskah siaran dari konteks request dan salam, menyintesis suara lokal, serta menurunkan volume musik secara dinamis saat host berbicara.

## ADDED Requirements

### Requirement: Pembuatan Naskah Siaran oleh LLM
Sistem SHALL menyusun naskah ucapan host secara otomatis menggunakan LLM berdasarkan konteks: judul lagu yang akan diputar, nama pengirim request, pesan titip salam, dan waktu siaran. Naskah SHALL berbahasa Indonesia dengan gaya penyiar radio dan panjang tidak melebihi `HOST_MAX_CHARS` (default 400 karakter).

#### Scenario: Naskah menyertakan titip salam
- **WHEN** sebuah request menyertakan pesan titip salam dari pendengar
- **THEN** naskah yang dihasilkan memuat nama pengirim dan isi salam tersebut secara natural

#### Scenario: LLM tidak tersedia
- **WHEN** LLM tidak aktif atau gagal merespons
- **THEN** sistem tetap memutar musik tanpa suara host dan mencatat kegagalan tanpa menghentikan siaran

### Requirement: Sintesis Suara Lokal (Piper TTS)
Sistem SHALL mengubah naskah host menjadi berkas audio menggunakan Piper TTS lokal, dan SHALL mendukung pemilihan model suara melalui konfigurasi.

#### Scenario: Naskah berhasil disintesis
- **WHEN** naskah host selesai dibuat
- **THEN** sistem menghasilkan berkas audio suara host dan menyiapkannya untuk dimasukkan ke aliran siaran

### Requirement: Mode Kemunculan Host
Sistem SHALL mendukung konfigurasi `HOST_MODE` untuk mengatur kapan host berbicara: setiap lagu (`every_song`), tiap N lagu (`interval`), atau hanya saat ada request (`request_only`). Saat `HOST_ENABLED` bernilai false, host SHALL tidak pernah muncul.

#### Scenario: Mode every_song
- **WHEN** `HOST_MODE=every_song` dan sebuah lagu akan diputar
- **THEN** host membacakan naskah sebelum lagu tersebut dimulai

#### Scenario: Host dimatikan
- **WHEN** `HOST_ENABLED=false`
- **THEN** siaran hanya berisi musik tanpa suara host

### Requirement: Dynamic Ducking Musik
Sistem SHALL menurunkan volume musik secara otomatis saat suara host aktif hingga level `DUCK_LEVEL` (default 0.25), lalu mengembalikannya ke volume normal setelah host selesai berbicara, sesuai waktu `DUCK_ATTACK_MS` dan `DUCK_RELEASE_MS`.

#### Scenario: Musik mengecil saat host bicara
- **WHEN** audio suara host mulai diputar di atas musik
- **THEN** volume musik turun ke sekitar level ducking dalam rentang attack yang dikonfigurasi

#### Scenario: Musik kembali normal setelah host selesai
- **WHEN** audio suara host selesai
- **THEN** volume musik naik kembali ke level penuh dalam rentang release yang dikonfigurasi tanpa terputus
