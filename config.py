import os
from dotenv import load_dotenv
import yaml

load_dotenv()  # load variables from .env if present


def load_config(path=None):
    path = path or os.path.join(os.path.dirname(__file__), "config.yaml")
    config = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

    # override/add Twitch settings from environment variables when provided
    env_map = {
        'TWITCH_CLIENT_ID': ('chat', 'twitch', 'client_id'),
        'TWITCH_CLIENT_SECRET': ('chat', 'twitch', 'client_secret'),
        'TWITCH_IRC_TOKEN': ('chat', 'twitch', 'irc_token'),
        'TWITCH_BOT_USERNAME': ('chat', 'twitch', 'bot_username'),
        'TWITCH_STREAMER_LOGIN': ('chat', 'twitch', 'streamer_login'),
    }

    for env_key, path_tuple in env_map.items():
        val = os.getenv(env_key)
        if val is None:
            continue
        # ensure nested dicts exist
        d = config
        for key in path_tuple[:-1]:
            d = d.setdefault(key, {})
        d[path_tuple[-1]] = val

    return config
