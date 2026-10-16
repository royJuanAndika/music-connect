"""Baca konfigurasi dari environment / .env."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

def _load_env_fallback(path: Path) -> None:
    """Fallback parser .env sederhana jika python-dotenv tidak terpasang."""
    if not path.is_file():
        return
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                if k and k not in os.environ:
                    os.environ[k] = v
    except Exception:
        pass


try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # ponytail: parse local .env without 3rd party dependency
    _load_env_fallback(Path(".env"))
    _load_env_fallback(Path(".env.example"))


def _split_ids(raw: str) -> list[int]:
    ids: list[int] = []
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            raise ValueError(f"ALLOWED_TELEGRAM_IDS ada nilai bukan angka: {part!r}")
    return ids


@dataclass(frozen=True)
class Settings:
    # Mode & Sumber Musik
    music_source: str = "youtube"
    ytdlp_path: str = "bin/yt-dlp.exe"
    yt_audio_format: str = "opus"
    yt_audio_bitrate: int = 128
    yt_search_limit: int = 5
    yt_max_duration_sec: int = 600
    yt_min_duration_sec: int = 30
    yt_allow_text_search: bool = True
    yt_allow_playlist: bool = False
    yt_block_live: bool = True
    yt_cookies_file: str = ""
    yt_proxy: str = ""
    cache_max_gb: float = 10.0
    prefetch_count: int = 2

    # Broadcast Engine & Stream Output
    stream_mode: str = "hls"
    stream_bitrate: str = "128k"
    stream_sample_rate: int = 44100
    stream_channels: int = 2
    hls_segment_seconds: int = 2
    hls_dir: Path = Path("data/hls")
    rtmp_url: str = ""
    rtmp_key: str = ""
    web_port: int = 8000
    ffmpeg_path: str = "bin/ffmpeg.exe"

    # AI Host
    host_enabled: bool = True
    host_language: str = "id"
    host_persona: str = "Santai, ramah, bersahabat layaknya penyiar radio FM anak muda"
    host_mode: str = "every_song"
    host_interval_songs: int = 3
    llm_provider: str = "openrouter"
    llm_model: str = "openrouter/free"
    tts_engine: str = "edge-tts"
    tts_voice: str = "id-ID-ArdiNeural"
    piper_path: str = "bin/piper.exe"
    piper_model: str = "models/id_ID-news-medium.onnx"
    host_max_chars: int = 400
    duck_level: float = 0.25
    duck_attack_ms: int = 200
    duck_release_ms: int = 800

    # Interaksi & Moderasi
    shoutout_enabled: bool = True
    shoutout_max_chars: int = 200
    request_cooldown_sec: int = 30
    max_queue_per_user: int = 3
    max_queue_total: int = 20
    banned_words: tuple[str, ...] = ()
    web_requests_open: bool = True
    telegram_enabled: bool = True

    # Telegram (bisa kosong kalau TELEGRAM_ENABLED=false)
    telegram_bot_token: str = ""
    allowed_telegram_ids: tuple[int, ...] = ()
    allowed_group_ids: tuple[int, ...] = ()

    # Spotify (opsional jika MUSIC_SOURCE=youtube)
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    spotify_redirect_uri: str = "http://127.0.0.1:8888/callback"
    device_name: str = ""

    # Watchdog & Server
    poll_interval_seconds: int = 20
    health_port: int = 8080
    data_dir: Path = Path("data")
    notify_chat_id: int | None = None

    # LLM (OpenRouter)
    openrouter_api_key: str = ""
    openrouter_model: str = "openrouter/free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Scopes Spotify
    spotify_scopes: tuple[str, ...] = field(
        default=(
            "user-read-playback-state",
            "user-modify-playback-state",
            "user-read-currently-playing",
            "user-read-private",
            "user-read-email",
        )
    )

    @property
    def tracks_dir(self) -> Path:
        return self.data_dir / "tracks"

    @property
    def voice_dir(self) -> Path:
        return self.data_dir / "voice"

    @property
    def token_path(self) -> Path:
        return self.data_dir / "token.json"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "queue.db"

    @property
    def memory_dir(self) -> Path:
        return self.data_dir / "memory"

    @property
    def notify_targets(self) -> tuple[int, ...]:
        """Ke mana notif device dikirim."""
        if self.notify_chat_id is not None:
            return (self.notify_chat_id,)
        return self.allowed_telegram_ids

    @property
    def llm_enabled(self) -> bool:
        return bool(self.openrouter_api_key)


def _to_bool(val: str, default: bool = False) -> bool:
    if not val:
        return default
    return val.strip().lower() in ("1", "true", "yes", "y", "on")


def _split_words(raw: str) -> tuple[str, ...]:
    words = [w.strip() for w in raw.replace(";", ",").split(",") if w.strip()]
    return tuple(words)


def load_settings() -> Settings:
    data_dir = Path(os.getenv("DATA_DIR", "data"))
    music_source = os.getenv("MUSIC_SOURCE", "youtube").strip().lower()
    telegram_enabled = _to_bool(os.getenv("TELEGRAM_ENABLED", "true"), default=True)

    def required_if(name: str, condition: bool) -> str:
        val = os.getenv(name, "").strip()
        if condition and not val:
            raise ValueError(f"Environment wajib belum diisi: {name}")
        return val

    notify_raw = os.getenv("NOTIFY_CHAT_ID", "").strip()
    notify_chat_id: int | None = None
    if notify_raw:
        try:
            notify_chat_id = int(notify_raw)
        except ValueError:
            raise ValueError(f"NOTIFY_CHAT_ID bukan angka: {notify_raw!r}")

    hls_dir_raw = os.getenv("HLS_DIR", "").strip()
    hls_dir = Path(hls_dir_raw) if hls_dir_raw else (data_dir / "hls")

    return Settings(
        # Mode & Sumber Musik
        music_source=music_source,
        ytdlp_path=os.getenv("YTDLP_PATH", "bin/yt-dlp.exe").strip(),
        yt_audio_format=os.getenv("YT_AUDIO_FORMAT", "opus").strip(),
        yt_audio_bitrate=int(os.getenv("YT_AUDIO_BITRATE", "128")),
        yt_search_limit=int(os.getenv("YT_SEARCH_LIMIT", "5")),
        yt_max_duration_sec=int(os.getenv("YT_MAX_DURATION_SEC", "600")),
        yt_min_duration_sec=int(os.getenv("YT_MIN_DURATION_SEC", "30")),
        yt_allow_text_search=_to_bool(os.getenv("YT_ALLOW_TEXT_SEARCH", "true"), default=True),
        yt_allow_playlist=_to_bool(os.getenv("YT_ALLOW_PLAYLIST", "false"), default=False),
        yt_block_live=_to_bool(os.getenv("YT_BLOCK_LIVE", "true"), default=True),
        yt_cookies_file=os.getenv("YT_COOKIES_FILE", "").strip(),
        yt_proxy=os.getenv("YT_PROXY", "").strip(),
        cache_max_gb=float(os.getenv("CACHE_MAX_GB", "10.0")),
        prefetch_count=int(os.getenv("PREFETCH_COUNT", "2")),

        # Broadcast Engine & Stream Output
        stream_mode=os.getenv("STREAM_MODE", "hls").strip().lower(),
        stream_bitrate=os.getenv("STREAM_BITRATE", "128k").strip(),
        stream_sample_rate=int(os.getenv("STREAM_SAMPLE_RATE", "44100")),
        stream_channels=int(os.getenv("STREAM_CHANNELS", "2")),
        hls_segment_seconds=int(os.getenv("HLS_SEGMENT_SECONDS", "2")),
        hls_dir=hls_dir,
        rtmp_url=os.getenv("RTMP_URL", "").strip(),
        rtmp_key=os.getenv("RTMP_KEY", "").strip(),
        web_port=int(os.getenv("WEB_PORT", "8000")),
        ffmpeg_path=os.getenv("FFMPEG_PATH", "bin/ffmpeg.exe").strip(),

        # AI Host
        host_enabled=_to_bool(os.getenv("HOST_ENABLED", "true"), default=True),
        host_language=os.getenv("HOST_LANGUAGE", "id").strip(),
        host_persona=os.getenv(
            "HOST_PERSONA",
            "Santai, ramah, bersahabat layaknya penyiar radio FM anak muda",
        ).strip(),
        host_mode=os.getenv("HOST_MODE", "every_song").strip(),
        host_interval_songs=int(os.getenv("HOST_INTERVAL_SONGS", "3")),
        llm_provider=os.getenv("LLM_PROVIDER", "openrouter").strip(),
        llm_model=os.getenv("LLM_MODEL", os.getenv("OPENROUTER_MODEL", "openrouter/free")).strip(),
        tts_engine=os.getenv("TTS_ENGINE", "edge-tts").strip().lower(),
        tts_voice=os.getenv("TTS_VOICE", "id-ID-ArdiNeural").strip(),
        piper_path=os.getenv("PIPER_PATH", "bin/piper.exe").strip(),
        piper_model=os.getenv("PIPER_MODEL", "models/id_ID-news-medium.onnx").strip(),
        host_max_chars=int(os.getenv("HOST_MAX_CHARS", "400")),
        duck_level=float(os.getenv("DUCK_LEVEL", "0.25")),
        duck_attack_ms=int(os.getenv("DUCK_ATTACK_MS", "200")),
        duck_release_ms=int(os.getenv("DUCK_RELEASE_MS", "800")),

        # Interaksi & Moderasi
        shoutout_enabled=_to_bool(os.getenv("SHOUTOUT_ENABLED", "true"), default=True),
        shoutout_max_chars=int(os.getenv("SHOUTOUT_MAX_CHARS", "200")),
        request_cooldown_sec=int(os.getenv("REQUEST_COOLDOWN_SEC", "30")),
        max_queue_per_user=int(os.getenv("MAX_QUEUE_PER_USER", "3")),
        max_queue_total=int(os.getenv("MAX_QUEUE_TOTAL", "20")),
        banned_words=_split_words(os.getenv("BANNED_WORDS", "")),
        web_requests_open=_to_bool(os.getenv("WEB_REQUESTS_OPEN", "true"), default=True),
        telegram_enabled=telegram_enabled,

        # Telegram
        telegram_bot_token=required_if("TELEGRAM_BOT_TOKEN", telegram_enabled),
        allowed_telegram_ids=tuple(_split_ids(os.getenv("ALLOWED_TELEGRAM_IDS", ""))),
        allowed_group_ids=tuple(_split_ids(os.getenv("ALLOWED_GROUP_IDS", ""))),

        # Spotify
        spotify_client_id=required_if("SPOTIFY_CLIENT_ID", music_source == "spotify"),
        spotify_client_secret=required_if("SPOTIFY_CLIENT_SECRET", music_source == "spotify"),
        spotify_redirect_uri=os.getenv(
            "SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback"
        ),
        device_name=os.getenv("DEVICE_NAME", "").strip(),

        # Watchdog & Server
        poll_interval_seconds=int(os.getenv("POLL_INTERVAL_SECONDS", "20")),
        health_port=int(os.getenv("HEALTH_PORT", "8080")),
        data_dir=data_dir,
        notify_chat_id=notify_chat_id,

        # LLM
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY", "").strip(),
        openrouter_model=os.getenv("OPENROUTER_MODEL", "openrouter/free").strip(),
        openrouter_base_url=os.getenv(
            "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
        ).strip(),
    )
