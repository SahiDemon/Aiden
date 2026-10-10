"""
Helper script to generate a Spotify refresh token using Authorization Code flow.

Usage:
    python tools/spotify_refresh_token_helper.py

Requires SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET environment variables.
"""
import http.server
import os
import secrets
import threading
import urllib.parse
import webbrowser
from typing import Optional
from pathlib import Path

import requests
from dotenv import load_dotenv, set_key

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_FILE)

CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "")
REDIRECT_URI = "http://127.0.0.1:8888/callback"
SCOPES = "user-read-playback-state user-modify-playback-state user-read-currently-playing"


class SpotifyCallbackHandler(http.server.BaseHTTPRequestHandler):
    auth_code: Optional[str] = None
    wait_event: Optional[threading.Event] = None
    state: str = ""

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")
            return
        params = urllib.parse.parse_qs(parsed.query)
        if not secrets.compare_digest(params.get("state", [""])[0], self.state):
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Invalid authorization state.")
            return
        code = params.get("code", [None])[0]
        if not code:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Authorization code missing.")
            if SpotifyCallbackHandler.wait_event:
                SpotifyCallbackHandler.wait_event.set()
            return

        SpotifyCallbackHandler.auth_code = code
        if SpotifyCallbackHandler.wait_event:
            SpotifyCallbackHandler.wait_event.set()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b"""<!doctype html><html><head><meta charset="utf-8">
<title>Spotify connected</title></head><body>
<h1>Spotify authorization received</h1>
<p>This tab will close automatically. If it stays open, you can close it.</p>
<script>
history.replaceState(null, '', '/callback');
setTimeout(() => window.close(), 500);
</script></body></html>""")

    def log_message(self, format, *args):
        return  # Suppress default logging


def start_http_server(wait_event: threading.Event):
    SpotifyCallbackHandler.wait_event = wait_event
    server = http.server.HTTPServer(("127.0.0.1", 8888), SpotifyCallbackHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        print("Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET environment variables before running this script.")
        return

    wait_event = threading.Event()
    SpotifyCallbackHandler.auth_code = None
    SpotifyCallbackHandler.state = secrets.token_urlsafe(32)
    server = start_http_server(wait_event)
    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "state": SpotifyCallbackHandler.state,
    }
    auth_url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode(params)
    print("Opening browser for Spotify authorization...")
    webbrowser.open(auth_url)

    print("Waiting for authorization code...")
    try:
        completed = wait_event.wait(120)
    finally:
        server.shutdown()
        server.server_close()

    code = SpotifyCallbackHandler.auth_code
    if not completed or not code:
        print("Spotify authorization was not completed. No credentials were changed.")
        return
    print("Authorization code received. Exchanging for tokens...")
    token_response = requests.post(
        "https://accounts.spotify.com/api/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
        },
        auth=(CLIENT_ID, CLIENT_SECRET),
        timeout=10,
    )
    token_response.raise_for_status()
    data = token_response.json()
    refresh_token = data.get("refresh_token")
    if not refresh_token:
        print("Spotify returned no refresh token. No credentials were changed.")
        return
    set_key(str(ENV_FILE), "SPOTIFY_REFRESH_TOKEN", refresh_token)
    print("Spotify reconnected. Refresh token saved to .env without displaying credentials.")


if __name__ == "__main__":
    main()
