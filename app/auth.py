"""Login OAuth Spotify sekali. Jalankan: python -m app.auth

Ada 2 mode:

MODE A (otomatis, default):
  Server kecil hidup di http://127.0.0.1:8888/callback DULU, lalu kamu buka
  URL login di browser. Spotify redirect balik ke server itu, script nangkep
  ?code= dan menukarnya jadi token.

MODE B (paste manual) -- berguna di Docker/WSL atau kalau browser & bot beda host:
  Jalankan:  python -m app.auth --manual
  Buka URL yang diberikan, login, lalu walau browser gagal connect, COPY URL
  di address bar (yang isinya ?code=...) dan tempel ke terminal.

Hasil: data/token.json (refresh token) yang dipakai bot selamanya.
"""
from __future__ import annotations

import base64
import json
import logging
import secrets
import sys
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

from .config import load_settings

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("auth")

_result: dict[str, str] = {}


class _Callback(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        _result.update({k: v[0] for k, v in params.items()})
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        if "code" in params:
            self.wfile.write(
                "<h2>Login berhasil. Balik ke terminal.</h2>".encode("utf-8")
            )
        else:
            msg = params.get("error", ["unknown"])[0]
            self.wfile.write(f"<h2>Login gagal: {msg}</h2>".encode("utf-8"))

    def log_message(self, *args) -> None:  # silence http log
        pass


def _build_auth_url(settings, state: str) -> str:
    return "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode(
        {
            "client_id": settings.spotify_client_id,
            "response_type": "code",
            "redirect_uri": settings.spotify_redirect_uri,
            "scope": " ".join(settings.spotify_scopes),
            "state": state,
            "show_dialog": "true",  # paksa tampil dialog login lagi
        }
    )


def _exchange_code(settings, code: str) -> dict:
    basic = base64.b64encode(
        f"{settings.spotify_client_id}:{settings.spotify_client_secret}".encode()
    ).decode()
    data = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.spotify_redirect_uri,
        }
    ).encode()
    req = urllib.request.Request(
        "https://accounts.spotify.com/api/token",
        data=data,
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def _save_token(settings, payload: dict) -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.token_path.write_text(
        json.dumps(
            {
                "access_token": payload["access_token"],
                "refresh_token": payload["refresh_token"],
                "expires_at": 0,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    log.info("Token tersimpan di %s. Selesai.", settings.token_path)


def _parse_redirect(raw: str) -> dict[str, str]:
    """Ambil code/state dari URL redirect atau dari string apapun."""
    raw = raw.strip().strip('"')
    # kalau yang ditempel cuma code mentah
    if "code=" not in raw and "http" not in raw:
        return {"code": raw}
    q = urllib.parse.urlparse(raw).query
    return {k: v[0] for k, v in urllib.parse.parse_qs(q).items()}


def run_manual(settings) -> None:
    state = secrets.token_urlsafe(16)
    auth_url = _build_auth_url(settings, state)
    log.info(
        "\n1) Buka URL ini di browser, login Spotify:\n\n%s\n\n"
        "2) Setelah login, browser mungkin gagal connect (itu normal).\n"
        "   COPY seluruh URL di address bar (yang ada ?code=...),\n"
        "   lalu tempel di sini dan tekan Enter.\n",
        auth_url,
    )
    raw = input("Tempel URL/code: ").strip()
    params = _parse_redirect(raw)

    if params.get("error"):
        raise SystemExit(f"Login ditolak: {params['error']}")
    if "code" not in params:
        raise SystemExit("Tidak menemukan 'code' di input kamu.")
    if params.get("state") and params["state"] != state:
        log.warning("State tidak cocok (mungkin URL dari login yang lama). Tetap lanjut.")

    payload = _exchange_code(settings, params["code"])
    _save_token(settings, payload)


def run_server(settings) -> None:
    redirect = urllib.parse.urlparse(settings.spotify_redirect_uri)
    host = redirect.hostname or "127.0.0.1"
    port = redirect.port or 8888

    state = secrets.token_urlsafe(16)
    auth_url = _build_auth_url(settings, state)

    # Server hidup DULU, baru buka browser supaya redirect tidak ditolak.
    server = HTTPServer((host, port), _Callback)
    log.info("Server callback hidup di %s", settings.spotify_redirect_uri)
    log.info("Buka URL ini di browser:\n\n%s\n", auth_url)
    try:
        webbrowser.open(auth_url)
    except Exception:
        pass

    log.info("Menunggu kamu login di browser ...")
    server.handle_request()  # tunggu 1 request
    server.server_close()

    if _result.get("error"):
        raise SystemExit(f"Login ditolak: {_result['error']}")
    if _result.get("state") != state:
        raise SystemExit("State tidak cocok. Coba lagi.")
    if "code" not in _result:
        raise SystemExit(f"Tidak dapat code: {_result}")

    payload = _exchange_code(settings, _result["code"])
    _save_token(settings, payload)


def main() -> None:
    settings = load_settings()
    if not settings.spotify_client_id or not settings.spotify_client_secret:
        raise SystemExit(
            "SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET belum diisi di .env"
        )

    manual = "--manual" in sys.argv or "-m" in sys.argv
    log.info("Mulai login Spotify (mode %s).", "MANUAL" if manual else "SERVER")
    if manual:
        run_manual(settings)
    else:
        run_server(settings)


if __name__ == "__main__":
    main()
