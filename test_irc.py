#!/usr/bin/env python3
"""Test script to verify IRC fallback is working and capturing messages."""

import asyncio
import os
import sys
from dotenv import load_dotenv

load_dotenv()

async def test_irc_listener():
    """Simple test to connect to Twitch IRC and listen for messages."""
    import ssl
    
    token = os.getenv("TWITCH_IRC_TOKEN")
    nick = os.getenv("TWITCH_BOT_USERNAME", "vj_gamess")
    channel = os.getenv("TWITCH_STREAMER_LOGIN", "vj_games")
    
    if not token:
        print("ERROR: TWITCH_IRC_TOKEN not set in .env")
        return
    
    print(f"Connecting to Twitch IRC as {nick} to join #{channel}...")
    
    ssl_ctx = ssl.create_default_context()
    reader, writer = await asyncio.open_connection('irc.chat.twitch.tv', 6697, ssl=ssl_ctx)
    
    # Send login
    writer.write(f"PASS {token}\r\n".encode('utf-8'))
    writer.write(f"NICK {nick}\r\n".encode('utf-8'))
    writer.write(f"JOIN #{channel}\r\n".encode('utf-8'))
    await writer.drain()
    
    print("Connected! Listening for messages for 30 seconds...")
    print("If someone chats in the stream, you should see it here.")
    print("Press Ctrl+C to stop early.")
    
    start_time = asyncio.get_event_loop().time()
    
    try:
        while True:
            # Check timeout
            if asyncio.get_event_loop().time() - start_time > 30:
                print("30 seconds elapsed - stopping test")
                break
            
            # Read with timeout
            try:
                line = await asyncio.wait_for(reader.readline(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            
            if not line:
                print("Connection closed by server")
                break
            
            text = line.decode('utf-8', errors='replace').strip()
            
            # PING/PONG
            if text.startswith('PING'):
                writer.write('PONG :tmi.twitch.tv\r\n'.encode('utf-8'))
                await writer.drain()
                print("Sent PONG")
                continue
            
            # PRIVMSG - this is a chat message!
            if 'PRIVMSG' in text:
                try:
                    prefix, rest = text.split(' PRIVMSG ', 1)
                    user = prefix.split('!')[0].lstrip(':')
                    chan, msg = rest.split(' :', 1)
                    print(f"CHAT [{chan}] {user}: {msg}")
                except Exception as e:
                    print(f"Error parsing: {text} - {e}")
            else:
                # Show other events for debugging
                if 'JOIN' in text or 'PART' in text:
                    print(f"EVENT: {text}")
    
    except KeyboardInterrupt:
        print("\nStopped by user")
    finally:
        writer.close()
        await writer.wait_closed()
        print("Disconnected")

if __name__ == "__main__":
    asyncio.run(test_irc_listener())
