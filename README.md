# Spotify Telegram Bot (lightweight)

Bot Telegram untuk **search, queue, dan list lagu** ke pemutar Spotify Connect
(yang memutar ke Bluetooth speaker). Ringan: 1 container, long polling (tanpa URL publik),
queue pakai SQLite.

## Arsitektur

```
Telegram <--long poll--> [BOT] --Spotify Web API--> Spotify Connect device (Android)
                            |
                        SQLite queue
                            |
                        /healthz  (buat watchdog host nanti)
```

## Fitur

- `/search <judul>` — cari 5 lagu
- `/queue <judul|nomor>` atau `/q` — tambah ke queue (lokal + Spotify)
- `/list` — lihat isi queue
- `/remove <nomor>` — hapus lagu dari queue (nomor urut dari `/list`, bisa beberapa: `/remove 1 3`)
- `/now` — lagu yang sedang diputar
- `/next`, `/pause`, `/resume` — kontrol playback
- `/device` — status device pemutar
- `/status` — ringkasan
- `/clearqueue` — kosongkan queue lokal
- `/routines` — daftar routine tersimpan
- `/routine <nama>` — putar routine tanpa LLM
- Watchdog device: cek tiap `POLL_INTERVAL_SECONDS`, notif saat device **offline/online**,
  auto-retarget (by nama, karena device id berubah tiap reconnect).

## Asisten AI + Memory (OpenRouter)

Isi `OPENROUTER_API_KEY` di `.env` untuk mengaktifkan asisten bahasa natural
(**tool calling**). Contoh yang bisa diketik langsung di chat (tanpa command):

- `putar lagu Hindia`
- `tambahin everything you are`
- `lagi main apa sekarang?`
- `hapus lagu nomor 2 dari queue`
- `simpan morning routine: slipknot, nirvana, metallica`
- **`hey dude, morning routine`** → langsung memutar routine tersimpan
- `catat ya Roy suka metal` → menyimpan catatan bebas
- `kamu tau apa soal Roy?` → membaca catatan

Model default `openrouter/free` = **router otomatis ke model gratis** yang
mendukung tool calling. Ganti lewat `OPENROUTER_MODEL` bila mau model lain.

### Memory = file Markdown

Ada **2 jenis memory**:

1. **Routine** (playlist bernama) — `data/memory/<slug>.md`
2. **Notes** (catatan bebas: preferensi, fakta, pengingat, apapun) —
   `data/memory/notes/<slug>.md`

```
data/memory/
├─ MEMORY.md              # ringkasan semua routine + notes (auto)
├─ morning-routine.md
├─ ngebut.md
└─ notes/
   ├─ preferensi-roy.md
   └─ fakta-ani.md
```

Semua plain markdown (gampang dibaca & diedit manual). `MEMORY.md` otomatis
di-generate ulang tiap ada perubahan.

Tools LLM: `search_tracks`, `queue_track`, `list_queue`, `remove_from_queue`,
`now_playing`, `device_status`, `next_track`, `pause`, `resume`,
`save_routine`, `list_routines`, `play_routine`, `delete_routine`,
`save_note`, `get_note`, `list_notes`, `delete_note`.

## Aturan akses (siapa yang boleh pakai)

- **Grup**: bebas. Cukup tambahkan bot ke grup, semua anggota grup bisa `/queue`.
  (Kalau mau batasi cuma grup tertentu, isi `ALLOWED_GROUP_IDS`.)
- **DM / chat pribadi**: cuma ID di `ALLOWED_TELEGRAM_IDS` (admin, yaitu kamu).
- Queue terpisah per-chat: `/list` di grup nampilkan queue grup itu saja.

## Setup

### 1. Bot Telegram
- Chat `@BotFather` → `/newbot` → ambil token.
- Chat `@userinfobot` → ambil **user id** kamu dan temen.

### 2. Spotify app
- Buka https://developer.spotify.com/dashboard → **Create app**.
- **Redirect URI** wajib: `http://127.0.0.1:8888/callback` (persis).
- Catat **Client ID** dan **Client Secret**.
- Catatan: kontrol playback & queue butuh akun **Spotify Premium**.

### 3. Konfigurasi
```bash
cp .env.example .env
# isi TELEGRAM_BOT_TOKEN, ALLOWED_TELEGRAM_IDS, SPOTIFY_CLIENT_ID,
# SPOTIFY_CLIENT_SECRET, DEVICE_NAME
```

### 4. Login Spotify sekali

**Redirect URI `http://127.0.0.1:8888/callback` itu BENAR** untuk setup lokal:
server OAuth kecil hidup di komputer yang sama dengan browsernya, jadi
`127.0.0.1` nyambung. Cuma dipakai sekali untuk mengambil refresh token.

**Kenapa "browser can't connect"?** Karena server callback-nya belum/ sudah tidak
jalan saat kamu klik login, atau (kalau via Docker) port `8888` belum di-map.
Pakai salah satu mode di bawah.

**Mode A — otomatis (browser & bot host sama):**
```bash
docker compose run --rm -p 8888:8888 bot python -m app.auth
```
Server hidup DULU, baru browser dibuka. Login, lalu biarkan redirect balik.

**Mode B — paste manual (paling anti-gagal, cocok buat Docker/WSL):**
```bash
docker compose run --rm bot python -m app.auth --manual
```
- Buka URL login di browser, login Spotify.
- Walaupun browser gagal connect (`127.0.0.1` tidak bisa dibuka), itu **normal**.
- **Copy seluruh URL di address bar** (yang berisi `?code=...`) dan **tempel** ke
  terminal saat diminta. Script menukarnya jadi token.

Token tersimpan di `data/token.json` (jangan di-commit).

> Tips: kalau login berkali-kali gagal, tambahkan akun Spotify kamu di
> **Dashboard → app → Settings → User Management** (mode Development max 25 user).

### 5. Jalankan
```bash
docker compose up -d --build
docker compose logs -f
```

## Set HP Android (WAJIB biar device tidak hilang)

Bot **tidak bisa** memaksa HP melek. Di HP yang memutar (lantai lain):
1. **Colok charger terus**.
2. **Developer Options → Stay awake while charging** (tetap bangun saat mengisi).
3. **Matikan battery optimization** untuk Spotify.
4. Spotify tetap **jalan di background** (jangan di-swipe keluar).
5. Jangan sampai HP restart otomatis.

Kalau ini tidak di-set, device tetap offline walau bot sempurna.

## Healthcheck (fondasi notif "host mati")

Bot membuka `GET /healthz` di port `8080`:
```json
{"ready": true, "device_online": true, "device_name": "Lantai 2"}
```
Nanti bisa ditambah **GitHub Actions cron** yang ping endpoint ini tiap N menit;
kalau gagal berkali-kali → panggil Telegram `sendMessage` → notif "server mati".
(Host yang mati tidak bisa mengirim pesannya sendiri, jadi harus dari luar.)

## Catatan penting

- **Refresh token ≠ device online.** Token refresh menjaga akses API; device tetap harus
  hidup di sisi HP/komputer.
- Kalau queue dikirim saat device offline, lagu tetap tercatat di queue lokal (SQLite)
  dan notifikasi statusnya dikirim ke kamu.
- `ALLOWED_TELEGRAM_IDS` kosong = bot terbuka untuk siapa saja. **Isi selalu.**
