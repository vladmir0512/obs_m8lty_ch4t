import os
import tempfile
import shutil
from config import load_config


def test_load_config_env_overrides(monkeypatch, tmp_path):
    # create a temporary config file
    cfg = tmp_path / "config.yaml"
    cfg.write_text("chat:\n  twitch:\n    streamer_login: fromfile\n")

    # ensure env overrides are used
    monkeypatch.setenv("TWITCH_STREAMER_LOGIN", "env_login")
    # call load_config with explicit path
    data = load_config(str(cfg))
    # load_config also picks up .env overrides; use explicit logic
    # load_config applies environment overrides, so streamer_login should be taken from env
    merged = load_config(str(cfg))
    # TWITCH_STREAMER_LOGIN should be applied to returned config
    assert merged.get("chat", {}).get("twitch", {}).get("streamer_login") == "env_login"
