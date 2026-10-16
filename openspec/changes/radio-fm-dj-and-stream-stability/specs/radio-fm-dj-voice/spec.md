# Spec Delta: radio-fm-dj-voice

## Purpose

Menyediakan AI Host penyiar radio FM dengan gaya bahasa luwes, pembacaan salam dengan target penerima spesifik, dan sintesis suara neural alami yang efisien.

## ADDED Requirements

### Requirement: Pembacaan Target Titip Salam Spesifik
Sistem SHALL menerima dan memproses informasi target penerima salam dari pendengar (baik melalui sintaks perintah pemisah maupun bahasa natural AI), dan menyertakannya secara eksplisit dalam naskah siaran yang dibacakan oleh host.

#### Scenario: Salam dengan target penerima eksplisit
- **WHEN** pendengar mengirimkan request lagu yang menyertakan target salam (misal: "untuk anak-anak IT")
- **THEN** naskah siaran yang dihasilkan menyebutkan nama pengirim, target penerima, dan pesan salam secara natural layaknya penyiar radio FM

### Requirement: Sintesis Suara Neural Bahasa Indonesia
Sistem SHALL mendukung sintesis suara berbasis teknologi neural Microsoft Edge (`edge-tts`) dalam Bahasa Indonesia (`id-ID-ArdiNeural` atau `id-ID-GadisNeural`) tanpa memerlukan lisensi berbayar atau dependensi model onnx lokal yang berat.

#### Scenario: Sintesis naskah DJ menggunakan neural voice
- **WHEN** naskah siaran selesai disusun oleh LLM
- **THEN** sistem menghasilkan berkas audio suara berkualitas tinggi dengan intonasi alami berbahasa Indonesia untuk dicampur ke dalam aliran siaran
