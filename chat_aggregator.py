import asyncio
import os
import time
import logging
import re
from twitchio.ext import commands
from twitch_auth import refresh_access_token, write_tokens_to_env, read_tokens_from_env

logger = logging.getLogger(__name__)


def _sanitize_content(content: str) -> str:
    """Sanitize chat content for logging/UI.
    - Remove URLs
    - Collapse whitespace
    - Trim to a reasonable length
    """
    if not content:
        return ""
    # remove common URL patterns
    content = re.sub(r"https?://\S+", "", content)
    content = re.sub(r"www\.\S+", "", content)
    # collapse whitespace
    content = re.sub(r"\s+", " ", content).strip()
    # limit length
    max_len = 1000
    if len(content) > max_len:
        content = content[:max_len-3] + "..."
    return content

class ChatAggregator:
    def __init__(self, cfg=None):
        self.cfg = cfg or {}
        self.tasks = []

    async def stop(self):
        """Gracefully stop all running tasks started by ChatAggregator."""
        print("ChatAggregator stopping...")
        # Cancel background tasks
        for t in list(self.tasks):
            try:
                t.cancel()
            except Exception:
                pass
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()
        print("ChatAggregator stopped.")

    async def start(self):
        logger.info("ChatAggregator starting...")
        # Twitch
        twitch_cfg = self.cfg.get("twitch", {})
        irc_token = twitch_cfg.get("irc_token") or os.getenv("TWITCH_IRC_TOKEN")
        bot_username = twitch_cfg.get("bot_username") or os.getenv("TWITCH_BOT_USERNAME")
        streamer = twitch_cfg.get("streamer_login") or os.getenv("TWITCH_STREAMER_LOGIN")

        # debug: log presence without exposing full secrets
        token_present = bool(irc_token)
        token_preview = ("oauth:" + irc_token[-6:]) if token_present and irc_token.startswith("oauth:") else ("<set>" if token_present else "<missing>")
        logger.debug("Twitch config: token=%s, bot=%s, streamer=%s", token_preview, bot_username, streamer)

        client_id = twitch_cfg.get("client_id") or os.getenv("TWITCH_CLIENT_ID")
        client_secret = twitch_cfg.get("client_secret") or os.getenv("TWITCH_CLIENT_SECRET")

        # retry/backoff settings (can be set via env)
        retry_base = int(os.getenv("TWITCH_RETRY_BASE", "5"))
        retry_max = int(os.getenv("TWITCH_RETRY_MAX", "300"))
        retry_max_attempts = os.getenv("TWITCH_RETRY_MAX_ATTEMPTS")
        retry_max_attempts = int(retry_max_attempts) if retry_max_attempts and retry_max_attempts.isdigit() else None

        if irc_token and streamer:
            # event used to notify manager that tokens were refreshed
            self._token_refreshed_event = asyncio.Event()

            # create a managed task that restarts the bot on failure with exponential backoff
            self.tasks.append(asyncio.create_task(self._manage_twitch_bot(irc_token, bot_username or "twitch-bot", [streamer], client_id, client_secret, retry_base, retry_max, retry_max_attempts, self._token_refreshed_event)))
            logger.info("Twitch bot task created (managed) for channel: %s", streamer)

            # if refresh token present, start background refresher task
            refresh_token = twitch_cfg.get("refresh_token") or os.getenv("TWITCH_REFRESH_TOKEN")
            expires_at = twitch_cfg.get("expires_at") or os.getenv("TWITCH_TOKEN_EXPIRES_AT")
            try:
                expires_at = int(expires_at) if expires_at else None
            except Exception:
                expires_at = None
            if refresh_token and client_id and client_secret:
                self.tasks.append(asyncio.create_task(self._twitch_token_refresher(client_id, client_secret, self._token_refreshed_event)))
                logger.info("Twitch token refresher task created")

            # Start raw IRC fallback listener to ensure we receive PRIVMSG events
            # This is now ALWAYS enabled as a reliable fallback since twitchio events may not fire
            self.tasks.append(asyncio.create_task(self._irc_fallback(irc_token, bot_username or "twitch-bot", streamer)))
            logger.info("Twitch IRC fallback task created (raw IRC listener)")
        else:
            logger.warning("Twitch config incomplete or missing; skipping Twitch chat.")

    async def _manage_twitch_bot(self, token, nick, channels, client_id, client_secret, retry_base, retry_max, retry_max_attempts, token_refreshed_event: asyncio.Event):
        import random, traceback
        attempt = 0
        backoff = retry_base
        current_token = token
        while True:
            attempt += 1
            bot = None
            try:
                logger.info("[twitch] starting bot (attempt %d)", attempt)
                bot = self._make_twitch_bot(current_token, nick, channels, client_id, client_secret, bot_id=None)
                # run bot.start() in a task so we can also wait for token refresh events
                bot_task = asyncio.create_task(bot.start())

                # wait for either bot to finish or token refresh event
                token_wait_task = asyncio.create_task(token_refreshed_event.wait())
                done, pending = await asyncio.wait({bot_task, token_wait_task}, return_when=asyncio.FIRST_COMPLETED)

                # handle token refresh signal
                if token_wait_task in done and token_refreshed_event.is_set():
                    logger.info("[twitch] token refresh detected, restarting bot with new token")
                    token_refreshed_event.clear()
                    # close bot and cancel its task if still running
                    if not bot_task.done():
                        try:
                            await bot.close()
                        except Exception:
                            pass
                        bot_task.cancel()
                        try:
                            await bot_task
                        except Exception:
                            pass
                    # read updated token
                    tokens = read_tokens_from_env()
                    new_token = tokens.get("access_token")
                    if new_token:
                        current_token = new_token
                    else:
                        logger.warning("[twitch] token refreshed but access token missing in env")
                    # reset counters
                    attempt = 0
                    backoff = retry_base
                    # continue to start bot with new token
                    continue

                # otherwise bot_task completed (disconnect or error)
                if bot_task in done:
                    try:
                        await bot_task
                    except Exception as exc:
                        logger.exception("[twitch] bot raised: %s", exc)
                        # ensure resources closed
                        try:
                            await bot.close()
                        except Exception:
                            pass
                        if retry_max_attempts and attempt >= retry_max_attempts:
                            logger.info("[twitch] reached max retry attempts (%d), giving up", retry_max_attempts)
                            break
                        sleep_time = backoff + random.random() * min(5, backoff)
                        logger.info("[twitch] retrying in %.1fs (backoff %ds)", sleep_time, backoff)
                        await asyncio.sleep(sleep_time)
                        backoff = min(backoff * 2, retry_max)
                    else:
                        logger.info("[twitch] bot stopped gracefully, will restart after short delay")
                        attempt = 0
                        backoff = retry_base
                        await asyncio.sleep(1)

            except asyncio.CancelledError:
                logger.info("[twitch] manage task cancelled")
                # ensure bot's resources are cleaned up
                if bot is not None:
                    try:
                        await bot.close()
                    except Exception:
                        pass
                raise
            except Exception as exc:
                logger.exception("[twitch] bot crashed: %s", exc)
                # try to close bot session to avoid unclosed client session
                if bot is not None:
                    try:
                        await bot.close()
                    except Exception:
                        pass
                if retry_max_attempts and attempt >= retry_max_attempts:
                    logger.info("[twitch] reached max retry attempts (%d), giving up", retry_max_attempts)
                    break
                sleep_time = backoff + random.random() * min(5, backoff)
                logger.info("[twitch] retrying in %.1fs (backoff %ds)", sleep_time, backoff)
                await asyncio.sleep(sleep_time)
                backoff = min(backoff * 2, retry_max)

    async def _twitch_token_refresher(self, client_id, client_secret, token_refreshed_event: asyncio.Event):
        """Background task to refresh Twitch access token when it nears expiry."""
        logger.info("[twitch] token refresher started")
        while True:
            tokens = read_tokens_from_env()
            refresh_token = tokens.get("refresh_token")
            expires_at = tokens.get("expires_at")
            now = int(time.time())
            if not refresh_token or not expires_at:
                # nothing to refresh, sleep and check later
                await asyncio.sleep(60)
                continue
            # refresh when less than 60 seconds left
            to_sleep = max(10, expires_at - now - 60)
            if to_sleep > 0:
                await asyncio.sleep(to_sleep)
                continue
            try:
                logger.info("[twitch] refreshing access token using refresh_token")
                data = refresh_access_token(client_id, client_secret, refresh_token)
                access_token = data.get("access_token")
                new_refresh = data.get("refresh_token") or refresh_token
                expires_in = data.get("expires_in", 3600)
                write_tokens_to_env(access_token, new_refresh, expires_in)
                logger.info("[twitch] token refreshed and saved to .env")
                # signal manager to reconnect with new token
                try:
                    token_refreshed_event.set()
                except Exception:
                    logger.exception("Failed to set token_refreshed_event")
                # optionally restart process to pick up new token if configured
                restart_flag = os.getenv("TWITCH_RESTART_ON_REFRESH", "false").lower()
                if restart_flag in ("1","true","yes"):
                    logger.info("[twitch] TWITCH_RESTART_ON_REFRESH set; exiting to allow supervisor to restart")
                    os._exit(0)
            except Exception as exc:
                logger.exception("[twitch] token refresh failed: %s", exc)
                await asyncio.sleep(30)

        if self.tasks:
            await asyncio.gather(*self.tasks)
        else:
            print("No chat backends configured; idle loop.")
            while True:
                await asyncio.sleep(3600)

    def _make_twitch_bot(self, token, nick, channels, client_id=None, client_secret=None, bot_id=None):
        outer = self

        # Try to fetch bot_id using Helix API if possible
        if bot_id is None:
            try:
                import requests
                if client_id and token and nick:
                    headers = {"Client-Id": client_id, "Authorization": f"Bearer {token.replace('oauth:', '')}"}
                    resp = requests.get("https://api.twitch.tv/helix/users", params={"login": nick}, headers=headers, timeout=5)
                    logger.debug(f"Helix API call for bot_id: status={resp.status_code}")
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("data"):
                            bot_id = data["data"][0].get("id")
                            logger.info(f"Retrieved bot_id: {bot_id}")
                        else:
                            logger.warning("Helix API returned no data")
                    else:
                        logger.warning(f"Helix API error: {resp.status_code}")
            except Exception as e:
                logger.warning(f"Failed to get bot_id from Helix: {e}")
                bot_id = None
        
        logger.debug(f"Final bot_id: {bot_id}")

        class Bot(commands.Bot):
            def __init__(self, token, nick, channels, client_id=None, client_secret=None, bot_id=None):
                # twitchio requires client_secret and bot_id in newer versions
                kwargs = {}
                if client_id:
                    kwargs['client_id'] = client_id
                if client_secret:
                    kwargs['client_secret'] = client_secret
                if bot_id:
                    kwargs['bot_id'] = bot_id
                logger.debug(f"Bot init with kwargs: {kwargs}")
                super().__init__(irc_token=token, nick=nick, prefix="!", initial_channels=channels, **kwargs)

            async def event_ready(self):
                # avoid accessing attributes that may not exist across twitchio versions
                bot_ident = getattr(self, 'nick', None) or getattr(self, 'name', None) or getattr(self, 'user', '<bot>')
                logger.info("Twitch bot connected", extra={"bot": bot_ident, "channels": channels})

            async def event_message(self, message):
                # low-level debug: log raw message object to help diagnosing missing events
                try:
                    logger.debug("raw message received", extra={"repr": repr(message), "attrs": {k: getattr(message, k, None) for k in dir(message) if k.startswith("content") or k in ("tags","echo")}})
                except Exception:
                    logger.debug("raw message received (could not introspect)")

                # ignore messages sent by the bot itself
                if getattr(message, 'echo', False):
                    logger.debug("Ignoring message.echo == True", extra={"author": getattr(message.author, 'name', None)})
                    return

                # echo to console if enabled (helpful for quick checks)
                if os.getenv("TWITCH_ECHO_MESSAGES", "true").lower() in ("1", "true", "yes"):
                    try:
                        print(f"[{getattr(message.channel, 'name', message.channel)}] {getattr(message.author, 'name', message.author)}: {getattr(message, 'content', '')}")
                    except Exception:
                        print(repr(message))

                # call module-level helper so logic is testable without bot instantiation
                log_chat_message(message)

            async def event_join(self, channel, user):
                try:
                    logger.debug("event_join", extra={"channel": getattr(channel, 'name', str(channel)), "user": getattr(user, 'name', str(user))})
                except Exception:
                    logger.debug("event_join received")

            async def event_part(self, channel, user):
                try:
                    logger.debug("event_part", extra={"channel": getattr(channel, 'name', str(channel)), "user": getattr(user, 'name', str(user))})
                except Exception:
                    logger.debug("event_part received")

            @commands.command(name="ping")
            async def ping(self, ctx: commands.Context):
                """Simple command to test bot responsiveness."""
                try:
                    await ctx.send("pong")
                except Exception:
                    logger.exception("Failed to send ping response")

        # return an instance of the Bot class
        return Bot(token, nick, channels, client_id=client_id, client_secret=client_secret, bot_id=bot_id)

    async def _irc_fallback(self, token, nick, channel):
        """Raw IRC fallback listener using asyncio streams. Connects directly to Twitch IRC over TLS and forwards PRIVMSG to log_chat_message.
        This runs in parallel with the twitchio bot and ensures we always receive chat messages.
        """
        import ssl, asyncio, random
        backoff = 5
        max_backoff = 300
        while True:
            try:
                logger.info("[irc-fallback] connecting to irc.chat.twitch.tv:6697 as %s, joining #%s", nick, channel)
                ssl_ctx = ssl.create_default_context()
                reader, writer = await asyncio.open_connection('irc.chat.twitch.tv', 6697, ssl=ssl_ctx)

                # send login
                writer.write(f"PASS {token}\r\n".encode('utf-8'))
                writer.write(f"NICK {nick}\r\n".encode('utf-8'))
                writer.write(f"JOIN #{channel}\r\n".encode('utf-8'))
                await writer.drain()

                logger.info("[irc-fallback] connected and joined channel")
                backoff = 5

                while True:
                    line = await reader.readline()
                    if not line:
                        logger.warning("[irc-fallback] connection closed by server")
                        break
                    text = line.decode('utf-8', errors='replace').strip()
                    logger.debug("[irc-fallback] RAW: %s", text[:400])
                    # PING/PONG
                    if text.startswith('PING'):
                        try:
                            writer.write('PONG :tmi.twitch.tv\r\n'.encode('utf-8'))
                            await writer.drain()
                            logger.debug('[irc-fallback] sent PONG')
                        except Exception:
                            logger.exception('[irc-fallback] failed to send PONG')
                        continue
                    if 'PRIVMSG' in text:
                        try:
                            # :user!user@user.tmi.twitch.tv PRIVMSG #channel :message
                            prefix, rest = text.split(' PRIVMSG ', 1)
                            user = prefix.split('!')[0].lstrip(':')
                            chan, msg = rest.split(' :', 1)
                            # build a minimal message-like object
                            import types
                            message = types.SimpleNamespace()
                            message.channel = types.SimpleNamespace(name=chan.lstrip('#'))
                            message.author = types.SimpleNamespace(name=user)
                            message.content = msg
                            message.tags = {}
                            message.echo = False
                            logger.debug('[irc-fallback] parsed PRIVMSG from %s: %s', user, msg[:200])
                            # forward to structured logger
                            try:
                                log_chat_message(message)
                            except Exception:
                                logger.exception('[irc-fallback] failed to log chat message')
                        except Exception:
                            logger.exception('[irc-fallback] failed to parse PRIVMSG')
            except asyncio.CancelledError:
                logger.info('[irc-fallback] cancelled')
                return
            except Exception:
                logger.exception('[irc-fallback] connection error, retrying')
            # backoff
            sleep = backoff + random.random() * min(5, backoff)
            logger.info('[irc-fallback] reconnecting in %.1fs (backoff %ds)', sleep, backoff)
            await asyncio.sleep(sleep)
            backoff = min(backoff * 2, max_backoff)


def log_chat_message(message):
    """Log a chat message in a structured way. Extracts/normalizes fields and writes to logger."""
    # basic debug to help diagnose missing events
    try:
        raw_content = getattr(message, 'content', '')
        logger.debug("log_chat_message invoked", extra={"raw_content_preview": raw_content[:200], "echo": getattr(message, 'echo', None)})
    except Exception:
        logger.debug("log_chat_message invoked (could not read message attributes)")

    channel = getattr(message.channel, 'name', str(message.channel))
    author = getattr(message.author, 'name', str(message.author))
    author_id = getattr(message.author, 'id', None) or getattr(message.author, 'user_id', None)
    tags = getattr(message, 'tags', {}) or {}
    raw_content = getattr(message, 'content', '')
    content = _sanitize_content(raw_content)

    logger.info("chat.message", extra={
        "channel": channel,
        "author": author,
        "author_id": str(author_id) if author_id is not None else None,
        "content": content,
        "tags": tags
    })

