import requests
import time
import os
from typing import Optional

TOKEN_URL = "https://id.twitch.tv/oauth2/token"


def exchange_code_for_token(client_id: str, client_secret: str, code: str, redirect_uri: str) -> dict:
    """Exchange authorization code for access and refresh tokens."""
    resp = requests.post(TOKEN_URL, data={
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }, timeout=10)
    resp.raise_for_status()
    return resp.json()


def refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> dict:
    """Refresh an access token using a refresh token."""
    resp = requests.post(TOKEN_URL, data={
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
    }, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _read_env(path: Optional[str] = None) -> dict:
    path = path or os.path.join(os.path.dirname(__file__), ".env")
    data = {}
    if not os.path.exists(path):
        return data
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                data[k] = v
    return data


def _write_env(updates: dict, path: Optional[str] = None):
    path = path or os.path.join(os.path.dirname(__file__), ".env")
    data = _read_env(path)
    data.update({k: str(v) for k, v in updates.items()})
    lines = [f"{k}={v}" for k, v in data.items()]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def write_tokens_to_env(access_token: str, refresh_token: str, expires_in: int):
    """Write TWITCH related tokens to the local .env file."""
    expires_at = int(time.time()) + int(expires_in)
    updates = {
        "TWITCH_IRC_TOKEN": f"oauth:{access_token}",
        "TWITCH_REFRESH_TOKEN": refresh_token,
        "TWITCH_TOKEN_EXPIRES_AT": str(expires_at),
    }
    _write_env(updates)


def read_tokens_from_env():
    d = _read_env()
    return {
        "access_token": d.get("TWITCH_IRC_TOKEN"),
        "refresh_token": d.get("TWITCH_REFRESH_TOKEN"),
        "expires_at": int(d.get("TWITCH_TOKEN_EXPIRES_AT")) if d.get("TWITCH_TOKEN_EXPIRES_AT") else None,
    }
