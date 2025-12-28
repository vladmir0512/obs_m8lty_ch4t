#!/usr/bin/env python3
"""show_chat.py — Simple CLI tailer for obs_multichat structured logs

Usage:
  python show_chat.py [-f|--follow] [-n N] [--channel NAME] [--author NAME]

Features:
- Reads `logs/obs_multichat.log` (JSON lines created by the app)
- Prints only records where `message == 'chat.message'`
- Filters by channel or author when provided
- `--follow` mode behaves like `tail -f`
"""

import argparse
import json
import os
import time
from datetime import datetime

LOG_PATH = os.path.join(os.path.dirname(__file__), "logs", "obs_multichat.log")


def format_record(rec: dict) -> str:
    ts = rec.get("asctime") or rec.get("timestamp") or datetime.utcnow().isoformat()
    channel = rec.get("channel", "?")
    author = rec.get("author", "?")
    content = rec.get("content", "")
    return f"{ts} [{channel}] {author}: {content}"


def tail(file, n=10):
    """Return last n lines of file as list."""
    try:
        with open(file, "rb") as f:
            # Seek near end and read backwards
            f.seek(0, os.SEEK_END)
            end = f.tell()
            size = 1024
            data = b""
            while end > 0 and data.count(b"\n") <= n:
                read_from = max(0, end - size)
                f.seek(read_from)
                data = f.read(end - read_from) + data
                end = read_from
                size *= 2
            lines = data.splitlines()
            return [l.decode("utf-8", errors="replace") for l in lines[-n:]]
    except FileNotFoundError:
        return []


def follow(file, callback, filters, tail_lines=10, sleep=0.5):
    # print tail first
    for line in tail(file, tail_lines):
        callback(line, filters)
    try:
        with open(file, "r", encoding="utf-8", errors="replace") as f:
            f.seek(0, os.SEEK_END)
            while True:
                line = f.readline()
                if not line:
                    time.sleep(sleep)
                    continue
                callback(line, filters)
    except KeyboardInterrupt:
        print("\nStopping follow.")


def process_line(line: str, filters: dict):
    line = line.strip()
    if not line:
        return
    try:
        obj = json.loads(line)
    except Exception:
        return
    if obj.get("message") != "chat.message":
        return
    if filters.get("channel") and obj.get("channel") != filters["channel"]:
        return
    if filters.get("author") and obj.get("author") != filters["author"]:
        return
    print(format_record(obj))


def main():
    p = argparse.ArgumentParser(description="Tail and format chat messages from logs/obs_multichat.log")
    p.add_argument("-f", "--follow", action="store_true", help="Follow new log lines (like tail -f)")
    p.add_argument("-n", "--lines", type=int, default=10, help="Number of lines to show from the end")
    p.add_argument("--channel", help="Filter by channel name")
    p.add_argument("--author", help="Filter by author name")
    args = p.parse_args()

    if not os.path.exists(LOG_PATH):
        print(f"Log file not found: {LOG_PATH}")
        raise SystemExit(1)

    filters = {k: v for k, v in (("channel", args.channel), ("author", args.author)) if v}

    if args.follow:
        follow(LOG_PATH, process_line, filters, tail_lines=args.lines)
    else:
        for line in tail(LOG_PATH, args.lines):
            process_line(line, filters)


if __name__ == "__main__":
    main()
