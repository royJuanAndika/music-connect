"""Baca konfigurasi dari environment / .env."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# load .env kalau ada (di lokal). Di Docker biasanya pakai env_file.
load_dotenv()


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
    telegram_bot_token: str
    allowed_telegram_ids: tuple[int, ...]
    allowed_group_ids: tuple[int, ...]
    spotify_client_id: str
    spotify_client_secret: str
    spotify_redirect_uri: str
    device_name: str
    poll_interval_seconds: int
    health_port: int
    data_dir: Path
    notify_chat_id: int | None
    # LLM (OpenRouter) - opsional. Kalau kosong, fitur NLP dimatikan.
    openrouter_api_key: str = ""
    openrouter_model: str = "openrouter/free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # scopes yang dibutuhkan untuk kontrol playback + baca state
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


def load_settings() -> Settings:
    data_dir = Path(os.getenv("DATA_DIR", "data"))

    def required(name: str) -> str:
        val = os.getenv(name, "").strip()
        if not val:
            raise ValueError(f"Environment wajib belum diisi: {name}")
        return val

    notify_raw = os.getenv("NOTIFY_CHAT_ID", "").strip()
    notify_chat_id: int | None = None
    if notify_raw:
        try:
            notify_chat_id = int(notify_raw)
        except ValueError:
            raise ValueError(f"NOTIFY_CHAT_ID bukan angka: {notify_raw!r}")

    return Settings(
        telegram_bot_token=required("TELEGRAM_BOT_TOKEN"),
        allowed_telegram_ids=tuple(_split_ids(os.getenv("ALLOWED_TELEGRAM_IDS", ""))),
        allowed_group_ids=tuple(_split_ids(os.getenv("ALLOWED_GROUP_IDS", ""))),
        spotify_client_id=required("SPOTIFY_CLIENT_ID"),
        spotify_client_secret=required("SPOTIFY_CLIENT_SECRET"),
        spotify_redirect_uri=os.getenv(
            "SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback"
        ),
        device_name=os.getenv("DEVICE_NAME", "").strip(),
        poll_interval_seconds=int(os.getenv("POLL_INTERVAL_SECONDS", "20")),
        health_port=int(os.getenv("HEALTH_PORT", "8080")),
        data_dir=data_dir,
        notify_chat_id=notify_chat_id,
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY", "").strip(),
        openrouter_model=os.getenv(
            "OPENROUTER_MODEL", "openrouter/free"
        ).strip(),
        openrouter_base_url=os.getenv(
            "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
        ).strip(),
    )
