#!/usr/bin/env python3
"""One-time setup script to download Angel One instrument master and cache tokens.

Usage:
    python scripts/lookup_angel_tokens.py

Reads stock symbols from config/watchlist.json, downloads the official instrument master
from Angel One, finds NSE-EQ tokens, and writes them to watchtower/symbol_tokens.json.

Requires network access to margincalculator.angelbroking.com.
"""
import json
import os
import sys
import urllib.request

# Resolve paths relative to this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "watchlist.json")
TOKENS_PATH = os.path.join(PROJECT_ROOT, "watchtower", "symbol_tokens.json")
MASTER_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"


def load_symbols() -> list:
    """Read symbols from watchlist.json."""
    if not os.path.exists(CONFIG_PATH):
        print(f"ERROR: {CONFIG_PATH} not found. Create it first.")
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    symbols = list(data.get("stocks", {}).keys())
    return symbols


def download_master() -> list:
    """Download and parse the Angel One instrument master JSON."""
    print(f"Downloading instrument master from {MASTER_URL} ...")
    try:
        with urllib.request.urlopen(MASTER_URL, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
    except Exception as e:
        print(f"ERROR: Failed to download instrument master: {e}")
        sys.exit(1)

    print("Parsing instrument master ...")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in instrument master: {e}")
        sys.exit(1)

    if not isinstance(data, list):
        print("ERROR: Expected instrument master to be a JSON array.")
        sys.exit(1)

    return data


def find_tokens(symbols: list, master: list):
    """Match symbols to tokens in the instrument master."""
    results = {}
    not_found = []

    for sym in symbols:
        target = f"{sym}-EQ"
        match = None
        for item in master:
            if (
                item.get("symbol") == target
                and item.get("exch_seg") == "NSE"
            ):
                match = item.get("token")
                break
        if match:
            results[sym] = match
            print(f"  {sym:12s} -> {match}")
        else:
            not_found.append(sym)
            print(f"  {sym:12s} -> NOT FOUND")

    return results, not_found


def main():
    symbols = load_symbols()
    print(f"Looking up tokens for {len(symbols)} symbol(s): {', '.join(symbols)}")

    master = download_master()
    print(f"Loaded {len(master)} instruments.")

    results, not_found = find_tokens(symbols, master)

    # Merge with existing tokens (if any)
    existing = {}
    if os.path.exists(TOKENS_PATH):
        try:
            with open(TOKENS_PATH, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            pass

    existing.update(results)

    os.makedirs(os.path.dirname(TOKENS_PATH), exist_ok=True)
    with open(TOKENS_PATH, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)

    print(f"\nWrote {len(existing)} token(s) to {TOKENS_PATH}")
    if not_found:
        print(f"WARNING: {len(not_found)} symbol(s) not found: {', '.join(not_found)}")
        print("         Check symbol names or verify they are listed on NSE.")


if __name__ == "__main__":
    main()
