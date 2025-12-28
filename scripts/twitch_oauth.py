import threading
import webbrowser
import urllib.parse
import http.server
import socketserver
import os
import sys
import time

# Ensure project root is on sys.path when running this script directly
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Load .env from project root so running this script reads environment variables
from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"))

from twitch_auth import exchange_code_for_token, write_tokens_to_env

REDIRECT_PATH = "/callback"
DEFAULT_PORT = 8080
SCOPES = ["chat:read", "chat:edit", "channel:manage:broadcast"]


class OAuthHandler(http.server.BaseHTTPRequestHandler):
    server_version = "TwitchOAuth/0.1"

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != REDIRECT_PATH:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")
            return
        query = urllib.parse.parse_qs(parsed.query)
        code = query.get("code", [None])[0]
        error = query.get("error", [None])[0]
        content = b""
        if error:
            content = f"Authorization failed: {error}".encode()
            self.send_response(400)
            self.end_headers()
            self.wfile.write(content)
            # store code as None (indicates failure)
            self.server.auth_code = None
            return
        if not code:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Missing code")
            self.server.auth_code = None
            return
        # success
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Authorization received. You can close this tab.")
        self.server.auth_code = code


def run_local_auth(port=DEFAULT_PORT, redirect_uri=None):
    client_id = os.getenv("TWITCH_CLIENT_ID")
    client_secret = os.getenv("TWITCH_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET must be in your environment (.env).")
        sys.exit(1)
    redirect_uri = redirect_uri or f"http://localhost:{port}{REDIRECT_PATH}"

    # Build auth URL with properly encoded scopes (space-separated)
    scope_str = " ".join(SCOPES)
    encoded_scope = urllib.parse.quote(scope_str)
    auth_url = (
        f"https://id.twitch.tv/oauth2/authorize?client_id={urllib.parse.quote(client_id)}&redirect_uri={urllib.parse.quote(redirect_uri)}&response_type=code&scope={encoded_scope}"
    )

    # start HTTP server in thread
    class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
        allow_reuse_address = True

    server = ThreadedHTTPServer(("", port), OAuthHandler)
    server.auth_code = None

    def serve():
        server.serve_forever()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()

    print("Opening browser to:", auth_url)
    webbrowser.open(auth_url)

    # wait for code
    try:
        while server.auth_code is None:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("Interrupted")
        server.shutdown()
        sys.exit(1)

    code = server.auth_code
    server.shutdown()

    print("Exchanging code for token...")
    token_data = exchange_code_for_token(client_id, client_secret, code, redirect_uri)
    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    expires_in = token_data.get("expires_in", 0)
    write_tokens_to_env(access_token, refresh_token, expires_in)
    print("Tokens saved to .env")


if __name__ == "__main__":
    run_local_auth()
