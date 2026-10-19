# Spec Delta: broadcast-engine

## Purpose

Mengatur proses siaran audio kontinu yang menggabungkan musik dan suara host, menghasilkan keluaran HLS untuk web serta opsional RTMP untuk Telegram, dan mengawasi kesehatan proses siaran.

## ADDED Requirements

### Requirement: Aliran Siaran Kontinu
Sistem SHALL menjalankan satu proses siaran berkelanjutan yang memutar lagu-lagu dari antrian secara berurutan tanpa jeda yang terdengar (gap), sehingga semua pendengar mendengar audio yang sama pada waktu yang sama.

#### Scenario: Perpindahan antar lagu tanpa gap
- **WHEN** satu lagu selesai diputar
- **THEN** lagu berikutnya dari antrian langsung diputar tanpa memutus aliran siaran

#### Scenario: Antrian kosong
- **WHEN** tidak ada lagu dalam antrian
- **THEN** sistem memutar sumber fallback (mis. playlist lokal/jingle) agar siaran tidak berhenti

### Requirement: Output HLS untuk Web
Sistem SHALL menghasilkan keluaran HLS berupa berkas playlist `.m3u8` dan segmen audio dengan panjang segmen sesuai `HLS_SEGMENT_SECONDS` (default 2 detik) pada direktori yang dikonfigurasi.

#### Scenario: HLS tersedia untuk pendengar web
- **WHEN** siaran berjalan dengan `STREAM_MODE` bernilai `hls` atau `both`
- **THEN** berkas playlist `.m3u8` dan segmen-segmennya diperbarui secara berkala dan dapat diakses pendengar web

### Requirement: Output RTMP Opsional
Sistem SHALL mendukung pengiriman aliran ke endpoint RTMP (mis. Telegram Channel Live) bila `STREAM_MODE` bernilai `rtmp` atau `both` dan kredensial RTMP diisi.

#### Scenario: Mode RTMP aktif
- **WHEN** `STREAM_MODE=both` dan `RTMP_URL` beserta `RTMP_KEY` terisi
- **THEN** sistem mengirim aliran siaran ke endpoint RTMP di samping keluaran HLS

#### Scenario: Kredensial RTMP tidak diisi
- **WHEN** `STREAM_MODE` menyertakan RTMP tetapi kredensial kosong
- **THEN** sistem tetap menjalankan keluaran HLS dan mencatat peringatan tanpa menghentikan siaran

### Requirement: Pengawasan Proses Siaran
Sistem SHALL memantau status proses siaran dan melakukan pemulihan otomatis (restart) bila proses berhenti tidak terduga, serta melaporkan perubahan status kepada operator.

#### Scenario: Proses siaran berhenti tak terduga
- **WHEN** proses siaran berhenti tanpa diminta
- **THEN** sistem menjalankan ulang proses siaran dan mengirim notifikasi status kepada operator
