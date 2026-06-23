#!/usr/bin/env python3
"""CLI entry point to run historical replay for a single stock.
Usage:
    python run_replay.py RELIANCE data/reliance_sample.csv
    python run_replay.py RELIANCE data/reliance_sample.csv --verbose
"""
import sys
import os

# Ensure watchtower package is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from watchtower.config_loader import load_watchlist, get_stock_config, ConfigError
from watchtower.replay import replay_csv, print_replay_summary


def main():
    args = [a for a in sys.argv[1:] if a != "--verbose"]
    verbose = "--verbose" in sys.argv[1:]

    if len(args) < 2:
        print("Usage: python run_replay.py <STOCK_SYMBOL> <CSV_PATH> [--verbose]")
        print("  Example: python run_replay.py RELIANCE data/reliance_sample.csv")
        print("  Example: python run_replay.py RELIANCE data/reliance_sample.csv --verbose")
        sys.exit(1)

    stock_symbol = args[0].upper()
    csv_path = args[1]

    if not os.path.exists(csv_path):
        print(f"Error: CSV file not found: {csv_path}")
        sys.exit(1)

    try:
        watchlist = load_watchlist()
        stock_config = get_stock_config(watchlist, stock_symbol)
    except ConfigError as e:
        print(f"Config error: {e}")
        sys.exit(1)

    print(f"Loading historical data for {stock_symbol} from {csv_path}...")
    alerts, final_state = replay_csv(csv_path, stock_symbol, stock_config)

    print_replay_summary(alerts, stock_symbol, verbose=verbose)

    if verbose:
        # Optional: print final state for debugging (verbose mode only --
        # this is internal bookkeeping detail, not useful in the simple view)
        print("\n  Final per-level state:")
        for key, lvl_state in final_state.level_states.items():
            cd = lvl_state.cooldown_until.isoformat() if lvl_state.cooldown_until else "None"
            print(f"    {key}: state={lvl_state.last_known_distance_state:11s} cooldown_until={cd} zone_consumed={lvl_state.zone_entry_consumed}")
        print()


if __name__ == "__main__":
    main()