import os
import requests
from dotenv import load_dotenv

load_dotenv()

token = os.getenv("TWITCH_IRC_TOKEN")
if not token:
    print("TWITCH_IRC_TOKEN not set in .env")
    raise SystemExit(1)

bearer = token.replace("oauth:", "")
resp = requests.get("https://id.twitch.tv/oauth2/validate", headers={"Authorization": f"OAuth {bearer}"}, timeout=10)
if resp.status_code != 200:
    print("Validation failed:", resp.status_code, resp.text)
    raise SystemExit(1)

print(resp.json())
