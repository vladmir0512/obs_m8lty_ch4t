# obs_multichat — MVP

Простой стартовый шаблон для агрегатора чатов и мультистрима (MVP).

Установка и запуск (Windows PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Настройка окружения:

1. Скопируйте шаблон `.env.example` в `.env` и заполните свои значения (не коммитить `.env`).

```powershell
cp .env.example .env
# Отредактируйте .env в любом редакторе
```

Запуск приложения:

```powershell
python main.py
```

Файлы:
- `requirements.txt` — зависимости
- `main.py` — точка входа
- `chat_aggregator.py` — модуль агрегатора чатов (заглушка)
- `stream_manager.py` — модуль мультистрима (заглушка)
- `metadata_updater.py` — обновление метаданных (заглушка)
- `config.yaml` — конфигурация (fallback)
Дальше: подключить реальные API (Twitch/YouTube), реализовать входы/аутентификацию и интеграцию с OBS.

Twitch reconnection / retry settings (env variables):

- `TWITCH_RETRY_BASE` — base backoff in seconds (default 5)
- `TWITCH_RETRY_MAX` — maximum backoff in seconds (default 300)
- `TWITCH_RETRY_MAX_ATTEMPTS` — maximum retry attempts (default none / infinite)

The Twitch bot will automatically retry on crashes/disconnects using exponential backoff.

OAuth helper and token refresh

- Use the helper to perform authorization and store tokens locally:

```powershell
python scripts\twitch_oauth.py
```

This will open your browser, let you authorize the bot account and then save `TWITCH_IRC_TOKEN`, `TWITCH_REFRESH_TOKEN` and `TWITCH_TOKEN_EXPIRES_AT` into `.env`.

- The app includes a background token refresher that will refresh the access token when it is near expiry. It will update `.env` with the new tokens and log refresh events to the log file.

- Optional: if you want the process to exit and let an external supervisor restart the app when a refresh happens, set:

```
TWITCH_RESTART_ON_REFRESH=true
```

Graceful shutdown

- The app now handles SIGINT/SIGTERM and performs a graceful shutdown: it cancels background tasks, stops chat aggregator tasks, and attempts to close running resources before exit.
- To test: run the app and press Ctrl+C — you should see a clean shutdown sequence in the logs.
