"""Semua command Telegram."""
from __future__ import annotations

import functools
import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from .config import Settings
from .device_watchdog import DeviceWatchdog
from .queue_store import QueueItem, QueueStore
from .spotify_client import NoActiveDevice, SpotifyClient, SpotifyError
from .tools import ToolContext

log = logging.getLogger(__name__)


def _cmd(func):
    """Log saat command benar-benar ke-handle (termasuk mention @bot)."""

    @functools.wraps(func)
    async def wrapper(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        chat = update.effective_chat
        user = update.effective_user
        log.info(
            "CMD %s dipanggil chat=%s(%s) user=%s",
            func.__name__,
            chat.id if chat else None,
            chat.type if chat else None,
            user.id if user else None,
        )
        return await func(self, update, ctx)

    return wrapper

HELP = (
    "*Spotify Bot* \u2014 kontrol pemutar lewat Spotify Connect.\n\n"
    "/search <judul> \u2014 cari lagu (5 hasil)\n"
    "/queue <judul atau nomor> \u2014 tambah ke queue\n"
    "/q <...> \u2014 alias /queue\n"
    "/list \u2014 lihat isi queue\n"
    "/remove <nomor> \u2014 hapus lagu dari queue\n"
    "/now \u2014 lagu yang sedang diputar\n"
    "/next \u2014 lagu berikutnya\n"
    "/pause \u2014 jeda\n"
    "/resume \u2014 lanjut\n"
    "/device \u2014 status device pemutar\n"
    "/status \u2014 ringkasan bot\n"
    "/clearqueue \u2014 kosongkan queue lokal\n"
    "/routines \u2014 daftar routine tersimpan\n"
    "/routine <nama> \u2014 putar routine\n"
    "/ask <teks> \u2014 tanya asisten AI\n"
    "/help \u2014 pesan ini\n\n"
    "\U0001f4ac Atau cukup ketik biasa (bahasa natural), contoh:\n"
    "\u2022 \"putar lagu Hindia\"\n"
    "\u2022 \"tambahin everything you are\"\n"
    "\u2022 \"lagi main apa sekarang?\"\n"
    "\u2022 \"hapus lagu nomor 2 dari queue\"\n\n"
    "\U0001f4ce *Di grup:* tag bot atau reply pesan bot, baru dia jawab.\n"
    "Contoh: _@bot putar lagu Hindia_  atau reply \"morning routine\"."
)


def _fmt_duration(ms: int) -> str:
    if not ms:
        return "--:--"
    total = ms // 1000
    return f"{total // 60}:{total % 60:02d}"


def _fmt_item(idx: int, it: QueueItem) -> str:
    return (
        f"{idx}. *{_escape(it.title)}* \u2014 {_escape(it.artist)} "
        f"`{_fmt_duration(it.duration_ms)}` (oleh {_escape(it.requested_by)})"
    )


def _escape(text: str) -> str:
    # escape markdown v1 sederhana supaya judul aneh tidak merusak pesan
    for ch in ("_", "*", "[", "`"):
        text = text.replace(ch, f"\\{ch}")
    return text


class Handlers:
    def __init__(
        self,
        settings: Settings,
        spotify: SpotifyClient,
        queue: QueueStore,
        watchdog: DeviceWatchdog,
        llm=None,
        memory=None,
    ) -> None:
        self.settings = settings
        self.spotify = spotify
        self.queue = queue
        self.watchdog = watchdog
        self.llm = llm  # LLMClient | None
        self.memory = memory  # MemoryStore | None

    # ---- guard ----
    def _allowed(self, update: Update) -> bool:
        """Aturan akses:
        - Di GRUP : bebas, siapa pun anggota grup boleh (biar temen tinggal masuk grup).
        - Di DM   : cuma ALLOWED_TELEGRAM_IDS (kamu).
        - Kalau chat-nya grup tapi ada GROUP_ID_ALLOWLIST, cek grupnya termasuk atau tidak.
        """
        chat = update.effective_chat
        if chat is None:
            return False
        if chat.type in ("group", "supergroup"):
            allowed_groups = self.settings.allowed_group_ids
            if allowed_groups and chat.id not in allowed_groups:
                log.info("DENY grup %s (tidak di ALLOWED_GROUP_IDS)", chat.id)
                return False
            return True

        # DM / private: pakai allowlist user
        user = update.effective_user
        if user is None:
            return False
        if not self.settings.allowed_telegram_ids:
            return True  # allowlist kosong -> izinkan semua (hati-hati)
        return user.id in self.settings.allowed_telegram_ids

    async def _deny(self, update: Update) -> None:
        msg = update.effective_message
        if msg is None:
            return
        if (update.effective_chat and update.effective_chat.type in ("group", "supergroup")):
            await msg.reply_text("Grup ini belum diizinkan memakai bot ini.")
        else:
            await msg.reply_text(
                "Maaf, di chat pribadi cuma admin yang boleh.\n"
                "Tambahin bot ke grup biar semua orang bisa queue."
            )

    # ---- commands ----
    @_cmd
    async def cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return await self._deny(update)
        await update.message.reply_text(HELP, parse_mode=ParseMode.MARKDOWN)

    @_cmd
    async def cmd_help(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await self.cmd_start(update, ctx)

    @_cmd
    async def cmd_whoami(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Tampilkan chat id + user id (buat daftar grup / debug)."""
        chat = update.effective_chat
        user = update.effective_user
        await update.message.reply_text(
            f"Chat: `{chat.id}` ({chat.type})\n"
            f"User: `{user.id if user else '?'}` "
            f"({user.first_name if user else '?'})",
            parse_mode=ParseMode.MARKDOWN,
        )

    @_cmd
    async def cmd_status(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return await self._deny(update)
        dev = "\u2705 online" if self.watchdog.online else "\u26a0\ufe0f offline"
        n = self.queue.count(update.effective_chat.id)
        await update.message.reply_text(
            f"Device *{self.settings.device_name or '?'}*: {dev}\n"
            f"Queue lokal: {n} lagu\n"
            f"Refetch device tiap {self.settings.poll_interval_seconds}s",
            parse_mode=ParseMode.MARKDOWN,
        )

    @_cmd
    async def cmd_device(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return await self._deny(update)
        try:
            devices = await _to_thread(self.spotify.get_devices)
        except SpotifyError as exc:
            return await update.message.reply_text(f"Gagal ambil device: {exc}")
        if not devices:
            return await update.message.reply_text(
                "Tidak ada device Spotify Connect yang terlihat sekarang."
            )
        lines = ["*Device terlihat di akun:*"]
        for d in devices:
            mark = " \u2190 target" if d.get("name") == self.settings.device_name else ""
            active = " (aktif)" if d.get("is_active") else ""
            lines.append(
                f"\u2022 {_escape(d.get('name','?'))}{active}{mark} "
                f"[{d.get('type','?')}]"
            )
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

    @_cmd
    async def cmd_search(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return await self._deny(update)
        query = " ".join(ctx.args).strip()
        if not query:
            return await update.message.reply_text("Pakai: /search <judul lagu>")
        try:
            tracks = await _to_thread(self.spotify.search_tracks, query)
        except SpotifyError as exc:
            return await update.message.reply_text(f"Gagal search: {exc}")
        if not tracks:
            return await update.message.reply_text("Tidak ada hasil.")
        ctx.chat_data["last_search"] = tracks
        lines = [f"*Hasil untuk:* {_escape(query)}"]
        for i, t in enumerate(tracks, 1):
            artists = ", ".join(a["name"] for a in t["artists"])
            lines.append(
                f"{i}. *{_escape(t['name'])}* \u2014 {_escape(artists)} "
                f"`{_fmt_duration(t.get('duration_ms', 0))}`"
            )
        lines.append("\nTambah dengan: `/queue <nomor>`")
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

    @_cmd
    async def cmd_queue(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return await self._deny(update)
        arg = " ".join(ctx.args).strip()
        if not arg:
            return await update.message.reply_text(
                "Pakai: /queue <judul lagu> atau /queue <nomor dari /search>"
            )

        user = update.effective_user
        who = user.first_name or str(user.id)

        # kalau argumen angka -> pakai hasil search terakhir
        track = None
        if arg.isdigit():
            tracks = ctx.chat_data.get("last_search") or []
            idx = int(arg) - 1
            if 0 <= idx < len(tracks):
                track = tracks[idx]
            else:
                return await update.message.reply_text(
                    "Nomor itu tidak ada di hasil /search terakhir."
                )
        else:
            try:
                tracks = await _to_thread(self.spotify.search_tracks, arg, 1)
            except SpotifyError as exc:
                return await update.message.reply_text(f"Gagal search: {exc}")
            if not tracks:
                return await update.message.reply_text("Lagu tidak ditemukan.")
            track = tracks[0]

        artists = ", ".join(a["name"] for a in track["artists"])
        title = track["name"]
        uri = track["uri"]

        # simpan ke queue lokal
        self.queue.add(
            chat_id=update.effective_chat.id,
            track_uri=uri,
            title=title,
            artist=artists,
            duration_ms=track.get("duration_ms", 0),
            requested_by=who,
        )

        # kirim ke queue Spotify (best-effort; kalau device offline, tetap tercatat lokal)
        device_id = self.watchdog.current_device_id()
        spotify_note = ""
        try:
            await _to_thread(self.spotify.add_to_queue, uri, device_id)
            spotify_note = "\u2705 ditambahkan ke queue Spotify"
        except NoActiveDevice:
            # device_id gagal -> coba pakai device aktif apa pun
            try:
                await _to_thread(self.spotify.add_to_queue, uri, None)
                spotify_note = "\u2705 ditambahkan ke queue Spotify (device aktif)"
            except (NoActiveDevice, SpotifyError):
                spotify_note = (
                    "\u26a0\ufe0f device offline; tersimpan di queue lokal, "
                    "akan diputar setelah device online"
                )
        except SpotifyError as exc:
            spotify_note = f"\u26a0\ufe0f gagal ke Spotify ({exc}); tersimpan lokal"

        pos = self.queue.count(update.effective_chat.id)
        await update.message.reply_text(
            f"Ditambahkan: *{_escape(title)}* \u2014 {_escape(artists)}\n"
            f"Posisi queue lokal: {pos}\n{spotify_note}",
            parse_mode=ParseMode.MARKDOWN,
        )

    @_cmd
    async def cmd_list(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return await self._deny(update)
        items = self.queue.list(update.effective_chat.id)
        if not items:
            return await update.message.reply_text("Queue kosong.")
        lines = ["*Queue sekarang:*"]
        for i, it in enumerate(items, 1):
            lines.append(_fmt_item(i, it))
        lines.append("\nHapus dengan: `/remove <nomor>`")
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

    @_cmd
    async def cmd_remove(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return await self._deny(update)
        arg = " ".join(ctx.args).strip()
        if not arg:
            return await update.message.reply_text("Pakai: /remove <nomor> (lihat /list)")
        items = self.queue.list(update.effective_chat.id)
        if not items:
            return await update.message.reply_text("Queue kosong, tidak ada yang bisa dihapus.")

        # dukung beberapa nomor sekaligus: /remove 1 3 5
        nums: list[int] = []
        for part in arg.replace(",", " ").split():
            if not part.isdigit():
                return await update.message.reply_text(
                    f"Nomor tidak valid: {part!r}. Pakai angka, contoh: /remove 2"
                )
            nums.append(int(part))

        removed: list[str] = []
        invalid: list[int] = []
        for n in nums:
            if 1 <= n <= len(items):
                it = items[n - 1]
                if self.queue.remove(it.id):
                    removed.append(f"{n}. {_escape(it.title)} \u2014 {_escape(it.artist)}")
            else:
                invalid.append(n)

        reply = []
        if removed:
            reply.append("*Dihapus dari queue:*")
            reply.extend("\u2022 " + r for r in removed)
        if invalid:
            reply.append(
                f"\u26a0\ufe0f Nomor di luar rentang (1\u2013{len(items)}): "
                + ", ".join(str(x) for x in invalid)
            )
        await update.message.reply_text("\n".join(reply), parse_mode=ParseMode.MARKDOWN)

    @_cmd
    async def cmd_now(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return await self._deny(update)
        try:
            playing = await _to_thread(self.spotify.get_currently_playing)
        except SpotifyError as exc:
            return await update.message.reply_text(f"Gagal cek lagu: {exc}")
        if not playing or not playing.get("item"):
            return await update.message.reply_text("Tidak ada lagu yang diputar.")
        item = playing["item"]
        artists = ", ".join(a["name"] for a in item["artists"])
        state = "playing" if playing.get("is_playing") else "paused"
        await update.message.reply_text(
            f"*{_escape(item['name'])}* \u2014 {_escape(artists)}\n"
            f"({state}) \u2022 `{_fmt_duration(item.get('duration_ms', 0))}`",
            parse_mode=ParseMode.MARKDOWN,
        )

    @_cmd
    async def cmd_next(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        return await self._control(update, "next")

    @_cmd
    async def cmd_pause(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        return await self._control(update, "pause")

    @_cmd
    async def cmd_resume(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        return await self._control(update, "resume")

    async def _control(self, update: Update, action: str) -> None:
        if not self._allowed(update):
            return await self._deny(update)
        device_id = self.watchdog.current_device_id()
        try:
            if action == "next":
                await _to_thread(self.spotify.next_track, device_id)
            elif action == "pause":
                await _to_thread(self.spotify.pause)
            elif action == "resume":
                await _to_thread(self.spotify.resume, device_id)
        except NoActiveDevice:
            return await update.message.reply_text("Device tidak aktif.")
        except SpotifyError as exc:
            return await update.message.reply_text(f"Gagal {action}: {exc}")
        await update.message.reply_text(f"OK: {action}.")

    @_cmd
    async def cmd_clearqueue(
        self, update: Update, ctx: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not self._allowed(update):
            return await self._deny(update)
        n = self.queue.clear(update.effective_chat.id)
        await update.message.reply_text(f"Queue lokal dikosongkan ({n} lagu).")

    @_cmd
    async def cmd_routines(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return await self._deny(update)
        if self.memory is None:
            return await update.message.reply_text("Fitur memory tidak aktif.")
        routines = self.memory.list_all()
        if not routines:
            return await update.message.reply_text(
                "Belum ada routine tersimpan.\n"
                "Contoh: ketik _simpan morning routine: slipknot, nirvana_"
            )
        lines = ["\U0001f4be *Routine tersimpan:*"]
        for r in routines:
            lines.append(f"\u2022 *{_escape(r.name)}* \u2014 {len(r.queries)} lagu")
        lines.append("\nPutar dengan: _hey, <nama routine>_ atau `/routine <nama>`")
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

    @_cmd
    async def cmd_routine(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Putar routine langsung tanpa LLM: /routine morning routine"""
        if not self._allowed(update):
            return await self._deny(update)
        if self.memory is None:
            return await update.message.reply_text("Fitur memory tidak aktif.")
        name = " ".join(ctx.args).strip()
        if not name:
            return await update.message.reply_text("Pakai: /routine <nama routine>")
        r = self.memory.get(name)
        if r is None:
            return await update.message.reply_text(f"Routine '{name}' tidak ditemukan.")
        device_id = self.watchdog.current_device_id()
        added = 0
        for q in r.queries:
            try:
                tracks = await _to_thread(self.spotify.search_tracks, q, 1)
            except SpotifyError:
                continue
            if not tracks:
                continue
            t = tracks[0]
            artists = ", ".join(a["name"] for a in t["artists"])
            self.queue.add(
                chat_id=update.effective_chat.id,
                track_uri=t["uri"],
                title=t["name"],
                artist=artists,
                duration_ms=t.get("duration_ms", 0),
                requested_by=update.effective_user.first_name or "?",
            )
            try:
                await _to_thread(self.spotify.add_to_queue, t["uri"], device_id)
            except (NoActiveDevice, SpotifyError):
                pass
            added += 1
        await update.message.reply_text(
            f"\u2705 Routine *{_escape(r.name)}* diputar \u2014 {added} lagu masuk queue.",
            parse_mode=ParseMode.MARKDOWN,
        )

    @_cmd
    async def cmd_ask(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Pesan teks biasa (bukan command) -> diproses LLM dengan tool calling.

        Aturan respons:
        - DM           : selalu dibalas.
        - Grup         : HANYA dibalas kalau bot di-mention (@bot) atau
                         pesan di-reply ke pesan bot. Biar gak berisik.
        - /ask <teks>  : selalu dibalas (eksplisit).
        """
        if not self._allowed(update):
            return await self._deny(update)

        if self.llm is None or not getattr(self.llm, "enabled", False):
            return  # LLM mati -> diamkan

        msg = update.message
        if msg is None:
            return

        chat = update.effective_chat
        bot_username = (ctx.bot.username or "").lower()
        bot_id = ctx.bot.id

        mention = f"@{bot_username}" if bot_username else "@bot"

        # /ask <teks> (eksplisit) -> selalu jawab
        is_explicit = bool(ctx.args)
        if is_explicit:
            text = " ".join(ctx.args).strip()
        else:
            text = (msg.text or msg.caption or "").strip()

            # apakah bot di-mention (@bot) atau pesan di-reply ke bot?
            mentioned = bool(
                bot_username and mention in text.lower()
            )
            replied_to_bot = bool(
                msg.reply_to_message
                and msg.reply_to_message.from_user
                and msg.reply_to_message.from_user.id == bot_id
            )

            is_group = chat.type in ("group", "supergroup")
            if is_group and not (mentioned or replied_to_bot):
                return  # di grup tanpa mention/reply -> diam

            # buang mention dari teks
            if bot_username and mentioned:
                import re as _re

                text = _re.sub(
                    rf"@{_re.escape(bot_username)}", "", text, flags=_re.IGNORECASE
                ).strip()

        if not text:
            # di-mention tanpa teks -> kasih hint
            if chat.type in ("group", "supergroup"):
                await msg.reply_text(
                    "Halo! Mau dengerin apa? Contoh: _putar lagu Hindia_ atau "
                    "_hai, morning routine_",
                    parse_mode=ParseMode.MARKDOWN,
                )
            return

        user = update.effective_user
        who = (user.first_name if user else "") or str(user.id if user else "?")

        tool_ctx = ToolContext(
            settings=self.settings,
            spotify=self.spotify,
            queue=self.queue,
            watchdog=self.watchdog,
            chat_id=chat.id,
            requested_by=who,
            memory=self.memory,
        )

        # indikator "sedang mengetik"
        try:
            await ctx.bot.send_chat_action(chat_id=chat.id, action="typing")
        except Exception:
            pass

        try:
            answer = await self.llm.run(text, tool_ctx)
        except Exception as exc:
            log.warning("LLM error: %s", exc)
            return await msg.reply_text(
                "Waduh, asisten AI-nya sedang error. Coba lagi sebentar ya."
            )

        if answer:
            await msg.reply_text(answer)


async def _to_thread(fn, *args):
    import asyncio

    return await asyncio.to_thread(fn, *args)
