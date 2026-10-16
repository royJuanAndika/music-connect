# Spec Delta: flexible-source-routing

## Purpose

Mengatur rute pencarian dan penambahan lagu secara dinamis berdasarkan konfigurasi `MUSIC_SOURCE` di environment tanpa menimbulkan ketergantungan wajib pada akun Spotify.

## ADDED Requirements

### Requirement: Pencarian Lagu Sesuai Sumber Konfigurasi
Sistem SHALL mengarahkan kueri pencarian perintah `/search` dan `/queue` ke resolver YouTube bila `MUSIC_SOURCE=youtube`, dan hanya memanggil API Spotify bila `MUSIC_SOURCE=spotify`.

#### Scenario: Pencarian saat mode YouTube aktif
- **WHEN** pengguna menjalankan `/search` atau `/queue` dan konfigurasi `MUSIC_SOURCE` bernilai `youtube`
- **THEN** sistem mencari metadata lagu melalui YouTube tanpa memeriksa atau menuntut ketersediaan token otentikasi Spotify

#### Scenario: Pencarian saat mode Spotify aktif
- **WHEN** pengguna menjalankan `/search` atau `/queue` dan konfigurasi `MUSIC_SOURCE` bernilai `spotify`
- **THEN** sistem mencari lagu melalui Spotify Web API menggunakan token yang tersimpan

### Requirement: Pencarian YouTube Multi-Hasil
Sistem SHALL mendukung pencarian teks YouTube yang mengembalikan hingga N hasil teratas (default 5 hasil) untuk disajikan kepada pengguna.

#### Scenario: Menampilkan beberapa kandidat lagu YouTube
- **WHEN** sistem meminta pencarian multi-track dengan kata kunci tertentu ke resolver YouTube
- **THEN** sistem mengembalikan daftar berisi judul, artis, durasi, dan video ID untuk setiap hasil yang cocok
