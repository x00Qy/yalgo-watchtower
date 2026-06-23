"""Configuration loader for YALGO Watchtower.
Loads and validates watchlist.json with explicit error messages.
"""
import json
import os
from typing import Any


class ConfigError(Exception):
    """Raised when watchlist.json is malformed or missing."""
    pass


def load_watchlist(config_path: str = None) -> dict:
    """Load and validate watchlist.json.
    Args:
        config_path: Path to watchlist.json. Defaults to
                     config/watchlist.json relative to project root.
    Returns:
        A dict with validated structure: {"stocks": {SYMBOL: {"support": [...], "resistance": [...]}}}
    Raises:
        ConfigError: If file missing, unreadable, or structurally invalid.
    """
    if config_path is None:
        # Resolve relative to this file's location (watchtower/)
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(base, "config", "watchlist.json")
    if not os.path.exists(config_path):
        raise ConfigError(f"watchlist.json not found at: {config_path}")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError as e:
        raise ConfigError(f"Invalid JSON in watchlist.json: {e}")
    except Exception as e:
        raise ConfigError(f"Cannot read watchlist.json: {e}")
    # Validate top-level shape
    if not isinstance(raw, dict):
        raise ConfigError("watchlist.json must be a JSON object (dict).")
    if "stocks" not in raw:
        raise ConfigError('watchlist.json must have a top-level "stocks" key.')
    stocks = raw["stocks"]
    if not isinstance(stocks, dict):
        raise ConfigError('"stocks" must be a dict mapping stock symbols to config.')
    for symbol, stock_config in stocks.items():
        if not isinstance(stock_config, dict):
            raise ConfigError(f'Stock "{symbol}" config must be a dict.')
        for required_key in ("support", "resistance"):
            if required_key not in stock_config:
                raise ConfigError(
                    f'Stock "{symbol}" missing required key "{required_key}".'
                )
            levels = stock_config[required_key]
            if not isinstance(levels, list):
                raise ConfigError(
                    f'Stock "{symbol}" "{required_key}" must be a list of level objects.'
                )
            for idx, level_obj in enumerate(levels):
                if not isinstance(level_obj, dict):
                    raise ConfigError(
                        f'Stock "{symbol}" "{required_key}"[{idx}] must be an object.'
                    )
                if "level" not in level_obj:
                    raise ConfigError(
                        f'Stock "{symbol}" "{required_key}"[{idx}] missing "level" key.'
                    )
                if not isinstance(level_obj["level"], (int, float)):
                    raise ConfigError(
                        f'Stock "{symbol}" "{required_key}"[{idx}] "level" must be numeric.'
                    )
                # "note" is optional but if present must be a string
                if "note" in level_obj and not isinstance(level_obj["note"], str):
                    raise ConfigError(
                        f'Stock "{symbol}" "{required_key}"[{idx}] "note" must be a string.'
                    )
    return raw


def get_stock_config(watchlist: dict, symbol: str) -> dict:
    """Return the config dict for a single stock symbol, or raise ConfigError."""
    stocks = watchlist.get("stocks", {})
    if symbol not in stocks:
        raise ConfigError(f'Stock "{symbol}" not found in watchlist.json.')
    return stocks[symbol]