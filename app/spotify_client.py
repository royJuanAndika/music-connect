"""Wrapper tipis Spotify Web API: OAuth token refresh + endpoint yang dipakai bot."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import httpx

from .config import Settings

log = logging.getLogger(__name__)

API = "https://api.spotify.com/v1"
ACCOUNTS = "https://accounts.spotify.com"


class SpotifyError(RuntimeError):
    """Error umum saat manggil Spotify API."""


class NoActiveDevice(SpotifyError):
    """Playback diperintah tapi tidak ada device aktif."""


class SpotifyClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = httpx.Client(timeout=15.0)
        self._access_token: str | None = None
        self._expires_at: float = 0.0
        self._refresh_token: str | None = None

    # ---------- OAuth ----------
    def load_token(self) -> None:
        path: Path = self.settings.token_path
        if not path.exists():
            raise SpotifyError(
                f"Token Spotify belum ada di {path}. Jalankan `python -m app.auth` dulu."
            )
        data = json.loads(path.read_text(encoding="utf-8"))
        self._refresh_token = data.get("refresh_token")
        if not self._refresh_token:
            raise SpotifyError("token.json tidak punya refresh_token. Login ulang.")

    def save_token(self, access_token: str, refresh_token: str, expires_in: int) -> None:
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._expires_at = time.time() + expires_in - 30  # buffer
        self.settings.token_path.write_text(
            json.dumps(
                {
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "expires_at": self._expires_at,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def _is_expired(self) -> bool:
        return not self._access_token or time.time() >= self._expires_at

    def _refresh(self) -> None:
        if not self._refresh_token:
            raise SpotifyError("Tidak ada refresh token. Login ulang dengan app.auth.")
        resp = self._client.post(
            f"{ACCOUNTS}/api/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
                "client_id": self.settings.spotify_client_id,
                "client_secret": self.settings.spotify_client_secret,
            },
        )
        if resp.status_code != 200:
            raise SpotifyError(f"Gagal refresh token: {resp.status_code} {resp.text}")
        payload = resp.json()
        # Spotify kadang tidak mengirim refresh_token baru -> pakai yang lama.
        self.save_token(
            payload["access_token"],
            payload.get("refresh_token", self._refresh_token),
            payload.get("expires_in", 3600),
        )
        log.info("Access token Spotify di-refresh.")

    def _headers(self) -> dict[str, str]:
        if self._is_expired():
            self._refresh()
        return {"Authorization": f"Bearer {self._access_token}"}

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        url = path if path.startswith("http") else f"{API}{path}"
        # coba sekali, kalau 401 refresh lalu ulang
        resp = self._client.request(method, url, headers=self._headers(), **kwargs)
        if resp.status_code == 401:
            self._access_token = None
            resp = self._client.request(method, url, headers=self._headers(), **kwargs)
        return resp

    def _json_or_error(self, resp: httpx.Response) -> dict:
        if resp.status_code == 204:
            return {}
        if resp.status_code >= 400:
            raise SpotifyError(f"Spotify {resp.status_code}: {resp.text}")
        if not resp.content:
            return {}
        return resp.json()

    # ---------- Devices ----------
    def get_devices(self) -> list[dict]:
        resp = self._request("GET", "/me/player/devices")
        data = self._json_or_error(resp)
        return data.get("devices", [])

    def find_device_by_name(self, name: str) -> dict | None:
        if not name:
            return None
        target = name.strip().lower()
        for d in self.get_devices():
            if d.get("name", "").strip().lower() == target:
                return d
        # fallback: cocok sebagian
        for d in self.get_devices():
            if target in d.get("name", "").strip().lower():
                return d
        return None

    # ---------- Search ----------
    def search_tracks(self, query: str, limit: int = 5) -> list[dict]:
        resp = self._request(
            "GET",
            "/search",
            params={"q": query, "type": "track", "limit": limit},
        )
        data = self._json_or_error(resp)
        return data.get("tracks", {}).get("items", [])

    # ---------- Playback ----------
    def get_currently_playing(self) -> dict | None:
        resp = self._request("GET", "/me/player/currently-playing")
        if resp.status_code == 204 or not resp.content:
            return None
        return self._json_or_error(resp)

    def add_to_queue(self, uri: str, device_id: str | None = None) -> None:
        # Spotify: URI dikirim sebagai QUERY PARAMETER, bukan body.
        params = {"uri": uri}
        if device_id:
            params["device_id"] = device_id
        resp = self._request("POST", "/me/player/queue", params=params)
        if resp.status_code not in (200, 204):
            if resp.status_code == 404:
                raise NoActiveDevice("Tidak ada device aktif untuk menambah queue.")
            raise SpotifyError(f"Gagal add to queue: {resp.status_code} {resp.text}")

    def play_track(self, uri: str, device_id: str | None = None) -> None:
        params = {"device_id": device_id} if device_id else None
        resp = self._request("PUT", "/me/player/play", params=params, json={"uris": [uri]})
        if resp.status_code not in (200, 204):
            if resp.status_code == 404:
                raise NoActiveDevice("Device tidak ditemukan / tidak aktif.")
            raise SpotifyError(f"Gagal play: {resp.status_code} {resp.text}")

    def pause(self) -> None:
        resp = self._request("PUT", "/me/player/pause")
        if resp.status_code not in (200, 204):
            raise SpotifyError(f"Gagal pause: {resp.status_code} {resp.text}")

    def resume(self, device_id: str | None = None) -> None:
        params = {"device_id": device_id} if device_id else None
        resp = self._request("PUT", "/me/player/play", params=params, json=None)
        if resp.status_code not in (200, 204):
            raise SpotifyError(f"Gagal resume: {resp.status_code} {resp.text}")

    def next_track(self, device_id: str | None = None) -> None:
        params = {"device_id": device_id} if device_id else None
        resp = self._request("POST", "/me/player/next", params=params)
        if resp.status_code not in (200, 204):
            raise SpotifyError(f"Gagal next: {resp.status_code} {resp.text}")

    def transfer_playback(self, device_id: str, play: bool = False) -> None:
        resp = self._request(
            "PUT", "/me/player", json={"device_ids": [device_id], "play": play}
        )
        if resp.status_code not in (200, 204):
            raise SpotifyError(f"Gagal transfer: {resp.status_code} {resp.text}")

    def close(self) -> None:
        self._client.close()
