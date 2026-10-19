# Design: FIFO Resilient RTMP Streaming

## Context

Lihat `proposal.md` untuk motivasi. Transmisi langsung `-f flv rtmps://...` sangat rentan terhadap fluktuasi latensi jaringan TCP internasional. Ketika antrian kirim penuh, FFmpeg memblokir I/O hingga akhirnya sistem operasi memutus soket dengan error `EPIPE / Broken pipe (exit code 224/251)`.

## Goals / Non-Goals

**Goals:**
- Mengisolasi transmisi jaringan RTMP dari proses encoding audio/video menggunakan thread FIFO terpisah.
- Mencegah crash FFmpeg saat terjadi lag jaringan sesaat dengan membuang frame video yang overflow.
- Memungkinkan auto-reconnect transparan saat soket goyang.

**Non-Goals:**
- Tidak mengubah output HLS (HLS bekerja secara lokal menulis berkas statis, sehingga tidak terpengaruh oleh fluktuasi jaringan RTMP).

## Decisions

### 1. Menggunakan Format Output `-f fifo -fifo_format flv`
Struktur argumen RTMP diubah dari:
```bash
-flvflags no_duration_filesize -f flv <url>
```
Menjadi:
```bash
-flvflags no_duration_filesize \
-f fifo -fifo_format flv \
-drop_pkts_on_overflow 1 \
-attempt_recovery 1 \
-recovery_wait_time 1 \
<url>
```

### 2. Pacing Buffer
- Menetapkan `-bufsize 400k` untuk memberikan toleransi lonjakan transmisi data audio dan video sintetis.

## Risks / Trade-offs

- **Frame Drop Video:** Jika koneksi sangat lambat, beberapa frame video kanvas hitam akan dibuang. Hal ini tidak menjadi masalah karena video hanyalah kanvas statis 320x240, sedangkan audio tetap diprioritaskan.
