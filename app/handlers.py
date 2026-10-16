"""Semua command Telegram."""
from __future__ import annotations

import functools
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
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
    "📻 *Radio Stream AI Bot* \u2014 Stasiun Radio Live & AI Host\n\n"
    "🎵 *Perintah Musik:*\n"
    "• `/search <judul>` \u2014 Cari lagu & pilih via tombol inline\n"
    "• `/request <judul atau link YT>` \u2014 Langsung putar lagu\n"
    "• `/salam <judul> | untuk <target> | <pesan>` \u2014 Request + titip salam\n"
    "• `/now` \u2014 Status lagu, sisa menit, & tombol cepat\n"
    "• `/skip` \u2014 Lewati lagu yang sedang diputar\n"
    "• `/list` \u2014 Lihat antrian & tombol dahulukan (bump)\n"
    "• `/bump <nomor>` \u2014 Dahulukan lagu ke antrian terdepan\n"
    "• `/remove <nomor>` \u2014 Hapus lagu dari antrian\n\n"
    "💬 *Ngobrol dengan AI DJ:*\n"
    "Ketik santai di grup (tag bot / reply pesan bot):\n"
    "_@bot putar lagu Sheila on 7 Dan dan titip salam buat tim IT_\n\n"
    "🌐 *Web Player:* http://localhost:8005"
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
        self.audio_engine = None  # AudioEngine | None
        self.downloader = None  # YouTubeDownloader | None

    def set_radio_components(self, audio_engine, downloader) -> None:
        self.audio_engine = audio_engine
        self.downloader = downloader

    async def handle_callback(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Handler event klik tombol Inline Keyboard."""
        query = update.callback_query
        if not query:
            return

        data = query.data or ""
        user = query.from_user
        who = f"@{user.username}" if user.username else (user.first_name or str(user.id))

        # 1. Action: Refresh now-playing
        if data == "act:refresh":
            await query.answer("Memperbarui status...")
            if self.settings.music_source == "youtube" and self.audio_engine:
                st = self.audio_engine.state
                status_text = "🟢 Sedang Mengudara" if st.is_running else "⚪ Menunggu Siaran"
                host_text = "\n🎙️ *Host AI:* Sedang bicara" if st.is_host_speaking else ""
                shout_text = f"\n💌 *Salam:* \"_{_escape(st.current_shoutout)}_\"" if st.current_shoutout else ""
                duration_text = ""
                if st.is_running and st.duration_sec > 0:
                    el_min, el_sec = divmod(st.elapsed_sec, 60)
                    rem_min, rem_sec = divmod(st.remaining_sec, 60)
                    tot_min, tot_sec = divmod(st.duration_sec, 60)
                    duration_text = (
                        f"\n⏱️ *Durasi:* `{el_min:02d}:{el_sec:02d}` / `{tot_min:02d}:{tot_sec:02d}` "
                        f"(sisa: `-{rem_min:02d}:{rem_sec:02d}`)"
                    )
                keyboard = [
                    [
                        InlineKeyboardButton("⏭ Skip", callback_data="act:skip"),
                        InlineKeyboardButton("📜 Antrian", callback_data="act:list"),
                        InlineKeyboardButton("🔄 Refresh", callback_data="act:refresh"),
                    ]
                ]
                text = (
                    f"*Status Radio:* {status_text}\n"
                    f"*Lagu:* {_escape(st.current_title)} — {_escape(st.current_artist)}"
                    f"{duration_text}{host_text}{shout_text}"
                )
                try:
                    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
                except Exception:
                    pass
            return

        # 2. Action: Skip track
        if data == "act:skip":
            if self.settings.music_source == "youtube" and self.audio_engine:
                if not self.audio_engine.state.is_running:
                    return await query.answer("Tidak ada lagu yang sedang diputar.", show_alert=True)
                cur_title = self.audio_engine.state.current_title
                self.audio_engine.stop()
                await query.answer("Lagu di-skip!")
                if query.message:
                    await query.message.reply_text(
                        f"⏭ *Lagu di-skip oleh {who}:* {_escape(cur_title)}\nMemutar lagu berikutnya...",
                        parse_mode=ParseMode.MARKDOWN,
                    )
            return

        # 3. Action: Lihat antrian
        if data == "act:list":
            await query.answer()
            items = self.queue.list(status="pending")
            if not items:
                if query.message:
                    await query.message.reply_text("Antrian lagu saat ini kosong.")
                return
            lines = ["*Queue sekarang:*"]
            keyboard = []
            for i, it in enumerate(items, 1):
                lines.append(_fmt_item(i, it))
                if i <= 5:
                    short_title = it.title[:20] + "..." if len(it.title) > 23 else it.title
                    keyboard.append([
                        InlineKeyboardButton(f"⚡ #{i} ({short_title})", callback_data=f"act:bump:{it.id}"),
                        InlineKeyboardButton(f"🗑️ #{i}", callback_data=f"act:del:{it.id}"),
                    ])
            lines.append("\n_Pilih tombol untuk mendahulukan (⚡) atau menghapus (🗑️):_")
            if query.message:
                await query.message.reply_text(
                    "\n".join(lines),
                    reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None,
                    parse_mode=ParseMode.MARKDOWN,
                )
            return

        # 3b. Action: Bump track dari tombol
        if data.startswith("act:bump:"):
            item_id = int(data[len("act:bump:"):])
            ok = self.queue.bump_to_front(item_id)
            if ok:
                await query.answer("Lagu didahulukan ke urutan #1!")
                if query.message:
                    await query.message.reply_text(f"⚡ Lagu #{item_id} berhasil didahulukan oleh {who}!")
            else:
                await query.answer("Gagal memindahkan lagu.", show_alert=True)
            return

        # 3c. Action: Delete track dari tombol
        if data.startswith("act:del:"):
            item_id = int(data[len("act:del:"):])
            ok = self.queue.remove(item_id)
            if ok:
                await query.answer("Lagu dihapus dari antrian!")
                if query.message:
                    await query.message.reply_text(f"🗑️ Lagu #{item_id} dihapus dari antrian oleh {who}.")
            else:
                await query.answer("Lagu tidak ditemukan / sudah terhapus.", show_alert=True)
            return

        # 4. Action: Queue track dari tombol search YouTube (qyt:<video_id>)
        if data.startswith("qyt:"):
            video_id = data[len("qyt:"):]
            from .downloader import DownloaderError
            from .queue_store import QueueValidationError

            try:
                self.queue.check_moderation_and_quota(
                    requested_by=who,
                    text_to_check="",
                    banned_words=self.settings.banned_words,
                    max_user_quota=self.settings.max_queue_per_user,
                    max_total_quota=self.settings.max_queue_total,
                    cooldown_sec=self.settings.request_cooldown_sec,
                )
            except QueueValidationError as e:
                return await query.answer(str(e), show_alert=True)

            title = f"YouTube {video_id}"
            artist = "YouTube"
            url = f"https://www.youtube.com/watch?v={video_id}"
            dur_ms = 0

            # Cek di cache pencarian terakhir jika ada
            yt_tracks = ctx.chat_data.get("last_search_yt") or []
            for t in yt_tracks:
                if t.video_id == video_id:
                    title = t.title
                    artist = t.uploader
                    url = t.webpage_url
                    dur_ms = t.duration_sec * 1000
                    break

            if dur_ms == 0 and self.downloader:
                try:
                    meta = await _to_thread(self.downloader.resolve_query, url)
                    title = meta.title
                    artist = meta.uploader
                    dur_ms = meta.duration_sec * 1000
                except DownloaderError:
                    pass

            item_id = self.queue.add(
                chat_id=query.message.chat.id if query.message else 0,
                track_uri=f"yt:{video_id}",
                title=title,
                artist=artist,
                duration_ms=dur_ms,
                requested_by=who,
                source_type="youtube",
                source_url=url,
            )
            pos = self.queue.count(status="pending")
            await query.answer("Lagu berhasil ditambahkan!")
            if query.message:
                await query.message.reply_text(
                    f"📻 Ditambahkan oleh {who}: *{_escape(title)}* — {_escape(artist)}\n"
                    f"Posisi antrian: #{pos}",
                    parse_mode=ParseMode.MARKDOWN,
                )
            return

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
            return await update.message.reply_text("Pakai: `/search <judul lagu>`", parse_mode=ParseMode.MARKDOWN)

        # Mode YouTube
        if self.settings.music_source == "youtube":
            if not self.downloader or not self.downloader.is_available():
                return await update.message.reply_text("Downloader YouTube tidak tersedia.")

            status_msg = await update.message.reply_text(f"🔎 Mencari lagu YouTube untuk: _{_escape(query)}_...", parse_mode=ParseMode.MARKDOWN)

            tracks_meta = await _to_thread(self.downloader.search_multitracks, query, 5)
            if not tracks_meta:
                return await status_msg.edit_text(f"Tidak ada hasil untuk: *{_escape(query)}*", parse_mode=ParseMode.MARKDOWN)

            # Simpan hasil untuk referensi manual /queue <nomor>
            ctx.chat_data["last_search_yt"] = tracks_meta

            lines = [f"🔍 *Hasil pencarian YouTube untuk:* _{_escape(query)}_\n"]
            keyboard = []

            for i, t in enumerate(tracks_meta, 1):
                dur_text = f"{t.duration_sec // 60}:{t.duration_sec % 60:02d}" if t.duration_sec else "--:--"
                lines.append(f"*{i}.* *{_escape(t.title)}* — `{dur_text}`")
                # Tombol per lagu
                short_title = t.title[:25] + "..." if len(t.title) > 28 else t.title
                keyboard.append([
                    InlineKeyboardButton(f"▶️ {i}. {short_title}", callback_data=f"qyt:{t.video_id}")
                ])

            lines.append("\n_Klik tombol di bawah untuk langsung memutar:_")
            reply_markup = InlineKeyboardMarkup(keyboard)
            return await status_msg.edit_text(
                "\n".join(lines),
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN,
            )

        # Mode Spotify (Legacy)
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
        who = (
            f"@{user.username}"
            if user and user.username
            else (user.first_name if user else "Anonim")
        )

        # Mode YouTube
        if self.settings.music_source == "youtube":
            from .downloader import DownloaderError
            from .queue_store import QueueValidationError

            title = arg
            artist = "YouTube"
            uri = f"query:{arg}"
            source_url = ""
            duration_ms = 0

            # Jika memilih via nomor dari /search terakhir
            if arg.isdigit():
                yt_tracks = ctx.chat_data.get("last_search_yt") or []
                idx = int(arg) - 1
                if 0 <= idx < len(yt_tracks):
                    meta = yt_tracks[idx]
                    title = meta.title
                    artist = meta.uploader
                    uri = f"yt:{meta.video_id}"
                    source_url = meta.webpage_url
                    duration_ms = meta.duration_sec * 1000
                else:
                    return await update.message.reply_text("Nomor tidak ada di hasil /search terakhir.")
            else:
                try:
                    self.queue.check_moderation_and_quota(
                        requested_by=who,
                        text_to_check=arg,
                        banned_words=self.settings.banned_words,
                        max_user_quota=self.settings.max_queue_per_user,
                        max_total_quota=self.settings.max_queue_total,
                        cooldown_sec=self.settings.request_cooldown_sec,
                    )
                except QueueValidationError as e:
                    return await update.message.reply_text(f"⚠️ {e}")

                if self.downloader and self.downloader.is_available():
                    try:
                        meta = self.downloader.resolve_query(arg)
                        title = meta.title
                        artist = meta.uploader
                        uri = f"yt:{meta.video_id}"
                        source_url = meta.webpage_url
                        duration_ms = meta.duration_sec * 1000
                    except DownloaderError as e:
                        return await update.message.reply_text(f"⚠️ Gagal resolusi YouTube: {e}")

            self.queue.add(
                chat_id=update.effective_chat.id,
                track_uri=uri,
                title=title,
                artist=artist,
                duration_ms=duration_ms,
                requested_by=who,
                source_type="youtube",
                source_url=source_url,
            )
            pos = self.queue.count(status="pending")
            return await update.message.reply_text(
                f"📻 Ditambahkan ke siaran radio: *{_escape(title)}* — {_escape(artist)}\n"
                f"Posisi antrian: #{pos}",
                parse_mode=ParseMode.MARKDOWN,
            )

        # Mode Spotify (Legacy)
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

        # Simpan ke queue
        if self.settings.music_source == "youtube":
            from .downloader import DownloaderError
            from .queue_store import QueueValidationError

            text_check = query
            try:
                self.queue.check_moderation_and_quota(
                    requested_by=who,
                    text_to_check=text_check,
                    banned_words=self.settings.banned_words,
                    max_user_quota=self.settings.max_queue_per_user,
                    max_total_quota=self.settings.max_queue_total,
                    cooldown_sec=self.settings.request_cooldown_sec,
                )
            except QueueValidationError as e:
                return await update.message.reply_text(f"⚠️ {e}")

            title = query
            artist = "YouTube"
            uri = f"query:{query}"
            source_url = ""

            if self.downloader and self.downloader.is_available():
                try:
                    meta = self.downloader.resolve_query(query)
                    title = meta.title
                    artist = meta.uploader
                    uri = f"yt:{meta.video_id}"
                    source_url = meta.webpage_url
                except DownloaderError as e:
                    return await update.message.reply_text(f"⚠️ Gagal resolusi YouTube: {e}")

            self.queue.add(
                chat_id=update.effective_chat.id,
                track_uri=uri,
                title=title,
                artist=artist,
                duration_ms=0,
                requested_by=who,
                source_type="youtube",
                source_url=source_url,
            )
            pos = self.queue.count(status="pending")
            return await update.message.reply_text(
                f"📻 Ditambahkan ke siaran radio: *{_escape(title)}* — {_escape(artist)}\n"
                f"Posisi queue: {pos}",
                parse_mode=ParseMode.MARKDOWN,
            )

        # simpan ke queue lokal (Spotify)
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
        items = self.queue.list(status="pending")
        if not items:
            return await update.message.reply_text("Antrian lagu saat ini kosong.")

        lines = ["*Queue sekarang:*"]
        keyboard = []
        for i, it in enumerate(items, 1):
            lines.append(_fmt_item(i, it))
            # Tambahkan tombol pintas untuk 5 antrian pertama
            if i <= 5:
                short_title = it.title[:20] + "..." if len(it.title) > 23 else it.title
                keyboard.append([
                    InlineKeyboardButton(f"⚡ Dahulukan #{i} ({short_title})", callback_data=f"act:bump:{it.id}"),
                    InlineKeyboardButton(f"🗑️ Hapus #{i}", callback_data=f"act:del:{it.id}"),
                ])

        lines.append("\n_Gunakan tombol di bawah atau ketik `/bump <nomor>` / `/remove <nomor>`_")
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        await update.message.reply_text("\n".join(lines), reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

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
    async def cmd_salam(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Kirim request dengan titip salam:
        Format 1: /salam <judul> | untuk <target> | <pesan salam>
        Format 2: /salam <judul> | <pesan salam>
        """
        if not self._allowed(update):
            return await self._deny(update)

        raw = " ".join(ctx.args).strip()
        if not raw or "|" not in raw:
            return await update.message.reply_text(
                "Format salah. Gunakan:\n"
                "`/salam <judul lagu> | untuk <target> | <pesan salam>`\n"
                "Atau: `/salam <judul lagu> | <pesan salam>`",
                parse_mode=ParseMode.MARKDOWN,
            )

        parts = [p.strip() for p in raw.split("|") if p.strip()]
        if len(parts) >= 3:
            query = parts[0]
            target_raw = parts[1]
            shoutout = " | ".join(parts[2:])
            # Bersihkan prefix "untuk" jika ada
            shoutout_to = target_raw[5:].strip() if target_raw.lower().startswith("untuk ") else target_raw
        elif len(parts) == 2:
            query = parts[0]
            shoutout_to = "semua pendengar"
            shoutout = parts[1]
        else:
            return await update.message.reply_text("Format tidak valid.")

        if not query:
            return await update.message.reply_text("Judul lagu tidak boleh kosong.")

        if len(shoutout) > self.settings.shoutout_max_chars:
            return await update.message.reply_text(
                f"Pesan salam terlalu panjang. Maksimal {self.settings.shoutout_max_chars} karakter."
            )

        who = (
            f"@{update.effective_user.username}"
            if update.effective_user and update.effective_user.username
            else (update.effective_user.first_name if update.effective_user else "Anonim")
        )

        from .downloader import DownloaderError
        from .queue_store import QueueValidationError

        text_check = f"{query} {shoutout_to} {shoutout}"
        try:
            self.queue.check_moderation_and_quota(
                requested_by=who,
                text_to_check=text_check,
                banned_words=self.settings.banned_words,
                max_user_quota=self.settings.max_queue_per_user,
                max_total_quota=self.settings.max_queue_total,
                cooldown_sec=self.settings.request_cooldown_sec,
            )
        except QueueValidationError as e:
            return await update.message.reply_text(f"⚠️ {e}")

        title = query
        artist = "YouTube"
        uri = f"query:{query}"
        source_url = ""
        duration_ms = 0

        if self.downloader and self.downloader.is_available():
            try:
                meta = self.downloader.resolve_query(query)
                title = meta.title
                artist = meta.uploader
                uri = f"yt:{meta.video_id}"
                source_url = meta.webpage_url
                duration_ms = meta.duration_sec * 1000
            except DownloaderError as e:
                return await update.message.reply_text(f"⚠️ Gagal resolusi YouTube: {e}")

        self.queue.add(
            chat_id=update.effective_chat.id,
            track_uri=uri,
            title=title,
            artist=artist,
            duration_ms=duration_ms,
            requested_by=who,
            source_type="youtube",
            source_url=source_url,
            shoutout_to=shoutout_to,
            shoutout_message=shoutout,
        )
        pos = self.queue.count(status="pending")
        await update.message.reply_text(
            f"📻 *Request & Salam diterima!*\n"
            f"🎵 Lagu: *{_escape(title)}* — {_escape(artist)}\n"
            f"🎯 Untuk: *{_escape(shoutout_to)}*\n"
            f"💌 Salam: \"_{_escape(shoutout)}_\"\n"
            f"🔢 Posisi antrian: #{pos}",
            parse_mode=ParseMode.MARKDOWN,
        )

    @_cmd
    async def cmd_pesan(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Kirim pengumuman suara siaran mandiri (Khusus Admin):
        Format: /pesan untuk <Target> | <Isi Pesan>
        Atau: /pesan <Isi Pesan>
        """
        user = update.effective_user
        if not user or user.id not in self.settings.allowed_telegram_ids:
            return await update.message.reply_text(
                "⛔ *Akses Ditolak:* Perintah siaran pengumuman mandiri (`/pesan`) hanya dapat digunakan oleh Admin.\n"
                "Untuk pendengar, gunakan `/salam <Lagu> | <Pesan>`.",
                parse_mode=ParseMode.MARKDOWN,
            )

        raw = " ".join(ctx.args).strip()
        if not raw:
            return await update.message.reply_text(
                "Gunakan format:\n"
                "`/pesan untuk <Target> | <Isi Pesan>`\n"
                "Atau: `/pesan <Isi Pesan>`",
                parse_mode=ParseMode.MARKDOWN,
            )

        if "|" in raw:
            parts = [p.strip() for p in raw.split("|", 1)]
            target_raw = parts[0]
            shoutout = parts[1]
            shoutout_to = target_raw[5:].strip() if target_raw.lower().startswith("untuk ") else target_raw
        else:
            shoutout_to = "semua pendengar"
            shoutout = raw

        who = f"@{user.username}" if user.username else (user.first_name or "Admin")

        item_id = self.queue.add(
            chat_id=update.effective_chat.id if update.effective_chat else 0,
            track_uri=f"msg:{item_id if 'item_id' in locals() else 'announcement'}",
            title="📢 Pengumuman Radio",
            artist=f"Admin {who}",
            duration_ms=0,
            requested_by=who,
            source_type="message",
            shoutout_to=shoutout_to,
            shoutout_message=shoutout,
        )
        pos = self.queue.count(status="pending")
        await update.message.reply_text(
            f"📢 *Pengumuman Admin Disiarkan!*\n"
            f"🎯 Untuk: *{_escape(shoutout_to)}*\n"
            f"💌 Pesan: \"_{_escape(shoutout)}_\"\n"
            f"Penyiar AI akan membacakannya dengan musik latar di antrian #{pos}.",
            parse_mode=ParseMode.MARKDOWN,
        )

    @_cmd
    async def cmd_now(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return await self._deny(update)

        if self.settings.music_source == "youtube" and self.audio_engine:
            st = self.audio_engine.state
            status_text = "🟢 Sedang Mengudara" if st.is_running else "⚪ Menunggu Siaran"
            host_text = "\n🎙️ *Host AI:* Sedang bicara" if st.is_host_speaking else ""
            shout_text = f"\n💌 *Salam:* \"_{_escape(st.current_shoutout)}_\"" if st.current_shoutout else ""

            duration_text = ""
            if st.is_running and st.duration_sec > 0:
                el_min, el_sec = divmod(st.elapsed_sec, 60)
                rem_min, rem_sec = divmod(st.remaining_sec, 60)
                tot_min, tot_sec = divmod(st.duration_sec, 60)
                duration_text = (
                    f"\n⏱️ *Durasi:* `{el_min:02d}:{el_sec:02d}` / `{tot_min:02d}:{tot_sec:02d}` "
                    f"(sisa: `-{rem_min:02d}:{rem_sec:02d}`)"
                )

            # Tombol kontrol cepat
            keyboard = [
                [
                    InlineKeyboardButton("⏭ Skip", callback_data="act:skip"),
                    InlineKeyboardButton("📜 Antrian", callback_data="act:list"),
                    InlineKeyboardButton("🔄 Refresh", callback_data="act:refresh"),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            return await update.message.reply_text(
                f"*Status Radio:* {status_text}\n"
                f"*Lagu:* {_escape(st.current_title)} — {_escape(st.current_artist)}"
                f"{duration_text}{host_text}{shout_text}",
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN,
            )

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
        if not self._allowed(update):
            return await self._deny(update)

        if self.settings.music_source == "youtube" and self.audio_engine:
            if not self.audio_engine.state.is_running:
                return await update.message.reply_text("Tidak ada lagu yang sedang diputar.")
            cur_title = self.audio_engine.state.current_title
            self.audio_engine.stop()
            return await update.message.reply_text(
                f"⏭ *Lagu di-skip:* {_escape(cur_title)}\nMemutar lagu berikutnya di antrian...",
                parse_mode=ParseMode.MARKDOWN,
            )

        return await self._control(update, "next")

    @_cmd
    async def cmd_bump(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Dahulukan lagu dari antrian ke paling depan: /bump <nomor>"""
        if not self._allowed(update):
            return await self._deny(update)

        arg = " ".join(ctx.args).strip()
        if not arg or not arg.isdigit():
            return await update.message.reply_text("Pakai: `/bump <nomor>` (lihat nomor urut di `/list`)", parse_mode=ParseMode.MARKDOWN)

        pos = int(arg)
        items = self.queue.list(status="pending")
        if not items:
            return await update.message.reply_text("Antrian lagu sedang kosong.")

        if pos < 1 or pos > len(items):
            return await update.message.reply_text(f"Nomor tidak valid (1-{len(items)}).")

        target_item = items[pos - 1]
        ok = self.queue.bump_to_front(target_item.id)
        if ok:
            await update.message.reply_text(
                f"⚡ *Lagu didahulukan ke urutan #1:* *{_escape(target_item.title)}* — {_escape(target_item.artist)}\n"
                f"Lagu ini akan diputar langsung setelah lagu sekarang selesai/di-skip.",
                parse_mode=ParseMode.MARKDOWN,
            )
        else:
            await update.message.reply_text("Gagal memindahkan posisi lagu.")

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
