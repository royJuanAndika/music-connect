# Spec Delta: interactive-telegram-bot

## Purpose

Menyediakan antarmuka bot Telegram yang interaktif menggunakan Inline Keyboard Buttons untuk kemudahan pencarian lagu, skip cepat, dan manipulasi antrian siaran radio.

## ADDED Requirements

### Requirement: Pencarian Lagu Interaktif dengan Tombol
Sistem SHALL menampilkan hasil pencarian lagu dalam bentuk tombol klik (inline keyboard button) di bawah pesan hasil pencarian Telegram, sehingga pengguna dapat memasukkan lagu ke antrian hanya dengan menekan tombol.

#### Scenario: Memilih lagu dari tombol pencarian
- **WHEN** pengguna menekan salah satu tombol pilihan lagu dari hasil `/search`
- **THEN** sistem langsung menambahkan lagu tersebut ke antrian siaran radio dan mengonfirmasi nomor urut antrian kepada pengguna

### Requirement: Tombol Kontrol Cepat pada Status Now Playing
Sistem SHALL menyertakan tombol aksi cepat pada respons perintah `/now`, minimal tombol skip dan tombol refresh status.

#### Scenario: Melewati lagu via tombol inline
- **WHEN** pengguna menekan tombol `[ ⏭ Skip ]` pada pesan `/now`
- **THEN** sistem menghentikan lagu yang sedang mengudara dan langsung memutar lagu berikutnya di antrian

#### Scenario: Memperbarui tampilan durasi via tombol refresh
- **WHEN** pengguna menekan tombol `[ 🔄 Refresh ]` pada pesan `/now`
- **THEN** sistem memperbarui teks sisa waktu dan status siaran pada pesan yang sama tanpa mengirim pesan obrolan baru
