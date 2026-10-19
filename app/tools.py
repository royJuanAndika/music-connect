"""Definisi tool + eksekusi untuk LLM (OpenRouter tool calling).

Setiap tool punya:
  - schema  : deskripsi JSON-schema yang dikirim ke LLM
  - runner  : fungsi yang dijalankan saat LLM memanggil tool itu

Runner menerima `ToolContext` (settings, spotify, queue, watchdog, chat_id,
requested_by) dan mengembalikan dict JSON-serializable sebagai hasil.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from .config import Settings
from .device_watchdog import DeviceWatchdog
from .memory import MemoryStore
from .queue_store import QueueStore
from .spotify_client import NoActiveDevice, SpotifyClient, SpotifyError

log = logging.getLogger(__name__)


@dataclass
class ToolContext:
    settings: Settings
    spotify: SpotifyClient
    queue: QueueStore
    watchdog: DeviceWatchdog
    chat_id: int
    requested_by: str
    memory: MemoryStore | None = None


def _track_brief(t: dict) -> dict:
    return {
        "name": t.get("name"),
        "artists": ", ".join(a.get("name", "") for a in t.get("artists", [])),
        "uri": t.get("uri"),
        "duration_ms": t.get("duration_ms", 0),
    }


# ---------------- runner: search ----------------
def run_search(ctx: ToolContext, query: str, limit: int = 5) -> dict:
    try:
        tracks = ctx.spotify.search_tracks(query, limit=max(1, min(int(limit), 10)))
    except SpotifyError as exc:
        return {"error": str(exc)}
    return {"count": len(tracks), "tracks": [_track_brief(t) for t in tracks]}


# ---------------- runner: queue ----------------
def run_queue(ctx: ToolContext, query: str, shoutout: str = "") -> dict:
    # Mode YouTube (default radio stream)
    if ctx.settings.music_source == "youtube":
        from .downloader import DownloaderError, YouTubeDownloader
        from .queue_store import QueueValidationError

        # Moderasi & kuota
        text_check = f"{query} {shoutout}"
        try:
            ctx.queue.check_moderation_and_quota(
                requested_by=ctx.requested_by,
                text_to_check=text_check,
                banned_words=ctx.settings.banned_words,
                max_user_quota=ctx.settings.max_queue_per_user,
                max_total_quota=ctx.settings.max_queue_total,
                cooldown_sec=ctx.settings.request_cooldown_sec,
            )
        except QueueValidationError as exc:
            return {"error": str(exc)}

        dl = YouTubeDownloader(ctx.settings)
        title = query
        artist = "YouTube"
        uri = f"query:{query}"
        source_url = ""

        if dl.is_available():
            try:
                meta = dl.resolve_query(query)
                title = meta.title
                artist = meta.uploader
                uri = f"yt:{meta.video_id}"
                source_url = meta.webpage_url
            except DownloaderError as exc:
                return {"error": str(exc)}

        item_id = ctx.queue.add(
            chat_id=ctx.chat_id,
            track_uri=uri,
            title=title,
            artist=artist,
            duration_ms=0,
            requested_by=ctx.requested_by,
            source_type="youtube",
            source_url=source_url,
            shoutout_message=shoutout,
        )
        return {
            "queued": {"name": title, "artists": artist, "uri": uri},
            "radio_mode": True,
            "shoutout": shoutout,
            "queue_position": ctx.queue.count(ctx.chat_id),
        }

    # Fallback Spotify (mode lama)
    try:
        tracks = ctx.spotify.search_tracks(query, limit=1)
    except SpotifyError as exc:
        return {"error": str(exc)}
    if not tracks:
        return {"error": f"Lagu '{query}' tidak ditemukan."}
    track = tracks[0]
    brief = _track_brief(track)

    ctx.queue.add(
        chat_id=ctx.chat_id,
        track_uri=brief["uri"],
        title=brief["name"],
        artist=brief["artists"],
        duration_ms=brief["duration_ms"],
        requested_by=ctx.requested_by,
    )

    device_id = ctx.watchdog.current_device_id()
    spotify_ok = False
    note = ""
    try:
        ctx.spotify.add_to_queue(brief["uri"], device_id)
        spotify_ok = True
    except NoActiveDevice:
        try:
            ctx.spotify.add_to_queue(brief["uri"], None)
            spotify_ok = True
        except (NoActiveDevice, SpotifyError):
            note = "device offline; tersimpan di queue lokal"
    except SpotifyError as exc:
        note = f"gagal ke Spotify ({exc}); tersimpan lokal"

    return {
        "queued": brief,
        "spotify_ok": spotify_ok,
        "note": note,
        "queue_position": ctx.queue.count(ctx.chat_id),
    }


# ---------------- runner: list ----------------
def run_list(ctx: ToolContext) -> dict:
    items = ctx.queue.list(ctx.chat_id)
    return {
        "count": len(items),
        "tracks": [
            {
                "position": i,
                "title": it.title,
                "artist": it.artist,
                "requested_by": it.requested_by,
            }
            for i, it in enumerate(items, 1)
        ],
    }


# ---------------- runner: remove ----------------
def run_remove(ctx: ToolContext, positions: list[int]) -> dict:
    items = ctx.queue.list(ctx.chat_id)
    if not items:
        return {"error": "Queue kosong."}
    removed: list[str] = []
    invalid: list[int] = []
    for n in positions:
        try:
            n = int(n)
        except (TypeError, ValueError):
            invalid.append(n)  # type: ignore[arg-type]
            continue
        if 1 <= n <= len(items):
            it = items[n - 1]
            if ctx.queue.remove(it.id):
                removed.append(f"{n}. {it.title} — {it.artist}")
        else:
            invalid.append(n)
    return {"removed": removed, "invalid": invalid, "remaining": ctx.queue.count(ctx.chat_id)}


# ---------------- runner: now playing ----------------
def run_now(ctx: ToolContext) -> dict:
    try:
        cur = ctx.spotify.get_currently_playing()
    except SpotifyError as exc:
        return {"error": str(exc)}
    if not cur or not cur.get("item"):
        return {"playing": None}
    item = cur["item"]
    return {
        "playing": _track_brief(item),
        "is_playing": cur.get("is_playing", False),
    }


# ---------------- runner: device status ----------------
def run_device_status(ctx: ToolContext) -> dict:
    try:
        devices = ctx.spotify.get_devices()
    except SpotifyError as exc:
        return {"error": str(exc)}
    target = ctx.settings.device_name
    return {
        "target_device": target,
        "target_online": ctx.watchdog.online,
        "devices": [
            {"name": d.get("name"), "is_active": d.get("is_active"), "type": d.get("type")}
            for d in devices
        ],
    }


# ---------------- runner: playback control ----------------
def run_next(ctx: ToolContext) -> dict:
    try:
        ctx.spotify.next_track(ctx.watchdog.current_device_id())
    except (NoActiveDevice, SpotifyError) as exc:
        return {"error": str(exc)}
    return {"ok": True, "action": "next"}


def run_pause(ctx: ToolContext) -> dict:
    try:
        ctx.spotify.pause()
    except SpotifyError as exc:
        return {"error": str(exc)}
    return {"ok": True, "action": "pause"}


def run_resume(ctx: ToolContext) -> dict:
    try:
        ctx.spotify.resume(ctx.watchdog.current_device_id())
    except SpotifyError as exc:
        return {"error": str(exc)}
    return {"ok": True, "action": "resume"}


# ---------------- runner: memory / routines ----------------
def _require_memory(ctx: ToolContext) -> MemoryStore | dict:
    if ctx.memory is None:
        return {"error": "Fitur memory tidak aktif."}
    return ctx.memory


def run_save_routine(
    ctx: ToolContext, name: str, tracks: list[str], description: str = ""
) -> dict:
    mem = _require_memory(ctx)
    if isinstance(mem, dict):
        return mem
    if not tracks:
        return {"error": "Tidak ada lagu untuk disimpan."}
    r = mem.save(
        name=name,
        queries=tracks,
        description=description,
        created_by=ctx.requested_by,
    )
    return {
        "saved": r.name,
        "slug": r.slug,
        "tracks": r.queries,
        "total": len(r.queries),
    }


def run_list_routines(ctx: ToolContext) -> dict:
    mem = _require_memory(ctx)
    if isinstance(mem, dict):
        return mem
    routines = mem.list_all()
    return {
        "count": len(routines),
        "routines": [
            {"name": r.name, "tracks": r.queries, "description": r.description}
            for r in routines
        ],
    }


def run_play_routine(ctx: ToolContext, name: str) -> dict:
    mem = _require_memory(ctx)
    if isinstance(mem, dict):
        return mem
    r = mem.get(name)
    if r is None:
        return {"error": f"Routine '{name}' tidak ditemukan."}
    if not r.queries:
        return {"error": f"Routine '{name}' kosong."}

    added: list[dict] = []
    failed: list[str] = []
    device_id = ctx.watchdog.current_device_id()

    for q in r.queries:
        try:
            found = ctx.spotify.search_tracks(q, limit=1)
        except SpotifyError as exc:
            failed.append(f"{q} ({exc})")
            continue
        if not found:
            failed.append(f"{q} (tidak ketemu)")
            continue
        brief = _track_brief(found[0])
        ctx.queue.add(
            chat_id=ctx.chat_id,
            track_uri=brief["uri"],
            title=brief["name"],
            artist=brief["artists"],
            duration_ms=brief["duration_ms"],
            requested_by=ctx.requested_by,
        )
        try:
            ctx.spotify.add_to_queue(brief["uri"], device_id)
        except NoActiveDevice:
            try:
                ctx.spotify.add_to_queue(brief["uri"], None)
            except (NoActiveDevice, SpotifyError):
                pass
        except SpotifyError:
            pass
        added.append({"query": q, "title": brief["name"], "artist": brief["artists"]})

    return {
        "routine": r.name,
        "added_count": len(added),
        "added": added,
        "failed": failed,
        "queue_position": ctx.queue.count(ctx.chat_id),
    }


def run_delete_routine(ctx: ToolContext, name: str) -> dict:
    mem = _require_memory(ctx)
    if isinstance(mem, dict):
        return mem
    ok = mem.delete(name)
    if not ok:
        return {"error": f"Routine '{name}' tidak ditemukan."}
    return {"deleted": name}


# ---------------- runner: catatan bebas (notes) ----------------
def run_save_note(
    ctx: ToolContext, key: str, content: str, category: str = ""
) -> dict:
    mem = _require_memory(ctx)
    if isinstance(mem, dict):
        return mem
    if not key.strip():
        return {"error": "Key catatan tidak boleh kosong."}
    n = mem.save_note(
        key=key, content=content, category=category, updated_by=ctx.requested_by
    )
    return {"saved": n.key, "slug": n.slug, "category": n.category, "content": n.content}


def run_get_note(ctx: ToolContext, key: str) -> dict:
    mem = _require_memory(ctx)
    if isinstance(mem, dict):
        return mem
    n = mem.get_note(key)
    if n is None:
        return {"error": f"Catatan '{key}' tidak ditemukan."}
    return {
        "key": n.key,
        "content": n.content,
        "category": n.category,
        "updated_by": n.updated_by,
        "updated_at": n.updated_at,
    }


def run_list_notes(ctx: ToolContext, category: str = "") -> dict:
    mem = _require_memory(ctx)
    if isinstance(mem, dict):
        return mem
    notes = mem.list_notes()
    if category:
        notes = [n for n in notes if n.category.lower() == category.strip().lower()]
    return {
        "count": len(notes),
        "notes": [
            {"key": n.key, "content": n.content, "category": n.category}
            for n in notes
        ],
    }


def run_delete_note(ctx: ToolContext, key: str) -> dict:
    mem = _require_memory(ctx)
    if isinstance(mem, dict):
        return mem
    if not mem.delete_note(key):
        return {"error": f"Catatan '{key}' tidak ditemukan."}
    return {"deleted": key}


# ---------------- registry ----------------
@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    runner: Callable[..., Any]


TOOLS: list[Tool] = [
    Tool(
        name="search_tracks",
        description=(
            "Cari lagu di Spotify berdasarkan judul/artis. "
            "Pakai ini untuk melihat pilihan sebelum menambahkan."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Judul lagu dan/atau artis."},
                "limit": {
                    "type": "integer",
                    "description": "Jumlah hasil (1-10). Default 5.",
                },
            },
            "required": ["query"],
        },
        runner=run_search,
    ),
    Tool(
        name="queue_track",
        description=(
            "Tambahkan lagu ke queue siaran radio. Mendukung judul lagu bebas, URL YouTube, "
            "dan opsi titip salam (shoutout)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Judul/artis lagu atau link YouTube."},
                "shoutout": {"type": "string", "description": "Pesan titip salam opsional untuk Host AI."},
            },
            "required": ["query"],
        },
        runner=run_queue,
    ),
    Tool(
        name="list_queue",
        description="Tampilkan daftar lagu yang sedang ada di queue (dengan nomor urut).",
        parameters={"type": "object", "properties": {}},
        runner=run_list,
    ),
    Tool(
        name="remove_from_queue",
        description=(
            "Hapus lagu dari queue berdasarkan nomor urut (posisi) yang tampil di list_queue."
        ),
        parameters={
            "type": "object",
            "properties": {
                "positions": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Daftar nomor urut lagu yang mau dihapus, contoh [2] atau [1,3].",
                }
            },
            "required": ["positions"],
        },
        runner=run_remove,
    ),
    Tool(
        name="now_playing",
        description="Tampilkan lagu yang sedang diputar saat ini.",
        parameters={"type": "object", "properties": {}},
        runner=run_now,
    ),
    Tool(
        name="device_status",
        description="Cek status device pemutar Spotify dan daftar device yang terlihat.",
        parameters={"type": "object", "properties": {}},
        runner=run_device_status,
    ),
    Tool(
        name="next_track",
        description="Lewati ke lagu berikutnya.",
        parameters={"type": "object", "properties": {}},
        runner=run_next,
    ),
    Tool(
        name="pause",
        description="Jeda pemutaran.",
        parameters={"type": "object", "properties": {}},
        runner=run_pause,
    ),
    Tool(
        name="resume",
        description="Lanjutkan pemutaran.",
        parameters={"type": "object", "properties": {}},
        runner=run_resume,
    ),
    # ---------------- memory / routines ----------------
    Tool(
        name="save_routine",
        description=(
            "Simpan sebuah 'routine' (playlist bernama) ke memory, mis. 'morning routine'. "
            "Pakai ini kalau pengguna bilang 'simpan', 'ingat', 'bikin routine', atau "
            "'catat playlist ...'. tracks berisi daftar lagu (judul/artis)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Nama routine, mis. 'morning routine'.",
                },
                "tracks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Daftar lagu (judul/artis) yang disimpan.",
                },
                "description": {
                    "type": "string",
                    "description": "Deskripsi singkat routine (opsional).",
                },
            },
            "required": ["name", "tracks"],
        },
        runner=run_save_routine,
    ),
    Tool(
        name="list_routines",
        description="Tampilkan semua routine yang tersimpan di memory.",
        parameters={"type": "object", "properties": {}},
        runner=run_list_routines,
    ),
    Tool(
        name="play_routine",
        description=(
            "Putar/queue sebuah routine yang tersimpan. Pakai ini kalau pengguna "
            "menyebut nama routine, mis. 'putar morning routine'."
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Nama routine yang mau diputar."}
            },
            "required": ["name"],
        },
        runner=run_play_routine,
    ),
    Tool(
        name="delete_routine",
        description="Hapus sebuah routine dari memory berdasarkan nama.",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Nama routine yang mau dihapus."}
            },
            "required": ["name"],
        },
        runner=run_delete_routine,
    ),
    # ---------------- catatan bebas (notes) ----------------
    Tool(
        name="save_note",
        description=(
            "Simpan catatan bebas ke memory (bukan playlist). Pakai untuk preferensi "
            "musik seseorang, fakta tentang teman, pengingat, atau info apapun. "
            "Contoh: 'Roy suka metal', 'jangan putar lagu galau pas kerja'. "
            "Kalau key sudah ada, isinya akan ditimpa (update)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "Judul/topik catatan, mis. 'preferensi Roy'.",
                },
                "content": {
                    "type": "string",
                    "description": "Isi catatannya (bebas).",
                },
                "category": {
                    "type": "string",
                    "description": "Kategori opsional, mis. 'preferensi', 'fakta', 'pengingat'.",
                },
            },
            "required": ["key", "content"],
        },
        runner=run_save_note,
    ),
    Tool(
        name="get_note",
        description="Ambil isi satu catatan berdasarkan key/nama.",
        parameters={
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Nama catatan."}
            },
            "required": ["key"],
        },
        runner=run_get_note,
    ),
    Tool(
        name="list_notes",
        description=(
            "Tampilkan semua catatan yang tersimpan. Bisa difilter per kategori. "
            "Pakai ini kalau pengguna tanya 'kamu tau apa soal ...', 'catatan apa aja'."
        ),
        parameters={
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Filter kategori (opsional).",
                }
            },
        },
        runner=run_list_notes,
    ),
    Tool(
        name="delete_note",
        description="Hapus satu catatan berdasarkan key/nama.",
        parameters={
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Nama catatan yang mau dihapus."}
            },
            "required": ["key"],
        },
        runner=run_delete_note,
    ),
]

TOOLS_BY_NAME = {t.name: t for t in TOOLS}


def openai_tool_schemas() -> list[dict]:
    """Format tools untuk OpenAI/OpenRouter chat completions."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in TOOLS
    ]
