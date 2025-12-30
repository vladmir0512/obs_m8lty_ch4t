#!/usr/bin/env python3
"""Minimal TLS IRC listener to verify Twitch IRC messages are received for the bot account.

Usage:
  Set TWITCH_IRC_TOKEN and TWITCH_BOT_USERNAME and TWITCH_STREAMER_LOGIN in your environment or .env, then run:
    python scripts/irc_listener.py

It will connect to Twitch IRC (ssl) and print raw IRC lines and parsed PRIVMSG chat messages for 2 minutes.
"""
import os
import socket
import ssl
import time
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('TWITCH_IRC_TOKEN')
NICK = os.getenv('TWITCH_BOT_USERNAME')
CHANNEL = os.getenv('TWITCH_STREAMER_LOGIN')

if not TOKEN or not NICK or not CHANNEL:
    print('Please set TWITCH_IRC_TOKEN, TWITCH_BOT_USERNAME and TWITCH_STREAMER_LOGIN in your environment or .env')
    raise SystemExit(1)

HOST = 'irc.chat.twitch.tv'
PORT = 6697

print(f'Connecting to {HOST}:{PORT} as {NICK}, joining #{CHANNEL}...')

context = ssl.create_default_context()
try:
    print('Resolving host...')
    addr = socket.getaddrinfo(HOST, PORT)
    print('Resolved address:', addr[0][4])
except Exception as e:
    print('DNS resolution failed:', e)

try:
    with socket.create_connection((HOST, PORT), timeout=10) as sock:
        print('TCP connected, starting TLS handshake...')
        with context.wrap_socket(sock, server_hostname=HOST) as ssock:
            print('TLS handshake completed, sending IRC login...')
            def send_line(l):
                ssock.send((l + '\r\n').encode('utf-8'))
            # PASS expects the token either 'oauth:...' or 'OAuth ...' but IRC wants 'oauth:...'
            try:
                send_line(f'PASS {TOKEN}')
                send_line(f'NICK {NICK}')
                send_line(f'JOIN #{CHANNEL}')
            except Exception as e:
                print('Failed to send initial lines:', e)
                raise

            start = time.time()
            try:
                ssock.settimeout(1.0)
                while True:
                    if time.time() - start > 120:
                        print('Timeout reached; exiting')
                        break
                    try:
                        data = ssock.recv(4096)
                        if not data:
                            print('Connection closed by server')
                            break
                        for line in data.decode('utf-8', errors='replace').split('\r\n'):
                            if not line:
                                continue
                            print('RAW:', line)
                            # PING/PONG handling
                            if line.startswith('PING'):
                                try:
                                    send_line('PONG :tmi.twitch.tv')
                                    print('Sent PONG')
                                except Exception as e:
                                    print('Failed to send PONG:', e)
                            # Parse PRIVMSG
                            if 'PRIVMSG' in line:
                                # :user!user@user.tmi.twitch.tv PRIVMSG #channel :message
                                try:
                                    prefix, rest = line.split(' PRIVMSG ', 1)
                                    user = prefix.split('!')[0].lstrip(':')
                                    chan, msg = rest.split(' :', 1)
                                    print(f'CHAT {chan} {user}: {msg}')
                                except Exception as e:
                                    print('PARSE ERR', e)
                    except socket.timeout:
                        continue
            except KeyboardInterrupt:
                print('Interrupted by user')
except Exception as e:
    print('Failed to connect or run listener:', e)
print('Done')
