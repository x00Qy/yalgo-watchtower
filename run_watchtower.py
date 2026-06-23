#!/usr/bin/env python3
"""
YALGO Watchtower — main entrypoint.
Usage: python run_watchtower.py
"""
import json
import os
import sys
from dotenv import load_dotenv
from watchtower.poller import run_poller


def main():
    load_dotenv()
    ntfy_topic = os.getenv("NTFY_TOPIC", "")
    with open("config/watchlist.json", "r") as f:
        raw = json.load(f)
    # watchlist.json wraps everything under a "stocks" key
    watchlist = raw.get("stocks", raw)
    n = len(watchlist)
    banner = (
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "YALGO Watchtower — started\n"
        f"Watching {n} symbols | Poll interval: 5 min\n"
        f"ntfy topic: {ntfy_topic}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    print(banner)
    try:
        run_poller(watchlist, interval_seconds=300)
    except KeyboardInterrupt:
        print("\n[watchtower] Stopped by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()