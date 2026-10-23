# Spec Delta: Audio Quality Enhancement

## Purpose
Menyediakan pipeline audio siaran radio live dengan fidelitas tinggi (48kHz/192k stereo), dynamic ducking yang halus, serta limiter anti-clipping untuk mencegah distorsi suara.

## ADDED Requirements

### Requirement: Broadcast Audio High-Fidelity Output
Sistem siaran audio SHALL meng-encode output siaran HLS dan RTMP menggunakan format AAC stereo 2-channel pada sample rate 48.000 Hz dan bitrate minimum 192 kbps.

#### Scenario: Stream encoding verification
- **WHEN** audio engine merender segmen siaran untuk HLS atau stream RTMP
- **THEN** FFmpeg dipanggil dengan parameter `-c:a aac -b:a 192k -ar 48000 -ac 2`

### Requirement: Dynamic Anti-Clipping Limiter
Sistem siaran audio SHALL menerapkan audio limiter (`alimiter`) di akhir rantai filter mixing untuk mencegah output audio melampaui 0.0 dBFS tanpa memicu distorsi saturasi digital kasar.

#### Scenario: Loud audio mix without clipping
- **WHEN** audio musik dan suara penyiar digabungkan dengan penguatan volume
- **THEN** audio filter melewatkan sinyal melalui `alimiter` dan level puncak (`max_volume`) tidak pernah melebihi -0.1 dBFS tanpa clipping terpotong

### Requirement: Smooth FM Radio Ducking
Sistem siaran audio SHALL menurunkan volume musik secara halus ketika AI Host berbicara dengan attack time 30ms, release time 1200ms, dan rasio kompresi 5:1, serta mempertahankan kejelasan vokal menggunakan filter vokal.

#### Scenario: Host speaks over music
- **WHEN** segmen siaran memiliki suara AI Host dan musik latar
- **THEN** musik otomatis melirih secara halus ke sekitar 40-50% volume dan kembali naik secara bertahap setelah host selesai bicara tanpa lonjakan menghentak
