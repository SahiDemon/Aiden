"""
Helper script to generate a Spotify refresh token using Authorization Code flow.

Usage:
    python tools/spotify_refresh_token_helper.py

Requires SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET environment variables.
"""
import http.server
import os
import threading
import urllib.parse
import webbrowser
from typing import Optional

import requests

CLIENT_ID = ("")
CLIENT_SECRET = ("")
REDIRECT_URI = "http://127.0.0.1:8888/callback"
SCOPES = "user-read-playback-state user-modify-playback-state user-read-currently-playing"


class SpotifyCallbackHandler(http.server.BaseHTTPRequestHandler):
    auth_code: Optional[str] = None
    wait_event: Optional[threading.Event] = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")
            return
        params = urllib.parse.parse_qs(parsed.query)
        code = params.get("code", [None])[0]
        if not code:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Authorization code missing.")
            return

        SpotifyCallbackHandler.auth_code = code
        if SpotifyCallbackHandler.wait_event:
            SpotifyCallbackHandler.wait_event.set()
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"You can close this window and return to the CLI.")

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
    server = start_http_server(wait_event)
    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
    }
    auth_url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode(params)
    print("Opening browser for Spotify authorization...")
    webbrowser.open(auth_url)

    print("Waiting for authorization code...")
    wait_event.wait()

    code = SpotifyCallbackHandler.auth_code
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
    print("\nSave this refresh token in your .env as SPOTIFY_REFRESH_TOKEN:\n")
    print(refresh_token)

    server.shutdown()


if __name__ == "__main__":
    main()
