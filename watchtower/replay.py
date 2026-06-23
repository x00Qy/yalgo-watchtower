"""Historical replay / backtest harness for YALGO Watchtower Phase 1.
Replays OHLCV candle data row-by-row, using the `close` price as the
poll price for simplicity.  Feeds each price through evaluate_poll() in
chronological order, accumulating all AlertEvents.
"""
import csv
from datetime import datetime
from typing import List, Dict, Any, Optional
from watchtower.classifier import (
    evaluate_poll,
    StockState,
    AlertEvent,
)
from watchtower.config_loader import get_stock_config


def parse_csv_row(row: dict) -> tuple:
    """Parse a single OHLCV row into (timestamp, close_price).
    Expects columns: timestamp, open, high, low, close, volume
    Timestamp format: ISO 8601 or YYYY-MM-DD HH:MM:SS
    """
    ts_raw = row["timestamp"]
    # Try ISO format first, then common alternatives
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            ts = datetime.strptime(ts_raw, fmt)
            break
        except ValueError:
            continue
    else:
        raise ValueError(f"Cannot parse timestamp: {ts_raw}")
    close = float(row["close"])
    return ts, close


def replay_csv(
    csv_path: str,
    stock_symbol: str,
    stock_config: dict,
    initial_state: Optional[StockState] = None,
) -> tuple:
    """Replay a CSV of historical candles through the alert engine.
    Args:
        csv_path: Path to OHLCV CSV (columns: timestamp,open,high,low,close,volume)
        stock_symbol: Stock symbol string
        stock_config: Dict with "support" and "resistance" lists
        initial_state: Optional existing StockState to continue from
    Returns:
        (all_alerts: List[AlertEvent], final_state: StockState)
    """
    state = initial_state if initial_state is not None else StockState()
    all_alerts: List[AlertEvent] = []
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts, close_price = parse_csv_row(row)
            alerts = evaluate_poll(
                stock_symbol=stock_symbol,
                current_price=close_price,
                stock_state=state,
                levels_config=stock_config,
                current_time=ts,
            )
            all_alerts.extend(alerts)
    return all_alerts, state


def _format_plain_english(a: AlertEvent) -> str:
    """Turn one AlertEvent into a single, easy-to-read sentence.

    Examples:
      09:25  RELIANCE is approaching support 2850 (price 2930, 2.8% away)
      09:45  RELIANCE TOUCHED support 2850 (price 2850)
      09:50  RELIANCE made a fast move near support 2850 (price 2886, 1.3% away)
    """
    time_str = a.timestamp.strftime("%H:%M")
    level_desc = f"{a.level_type} {a.level:g}"

    if a.alert_reason == "touch":
        # If price is essentially at the level, don't repeat the distance
        # (0.0% away reads as noise); only show distance if it's meaningfully
        # off-level (i.e. "touch" fired because of a breach further away).
        if a.distance_pct < 0.05:
            return f"{time_str}  {a.stock} TOUCHED {level_desc} (price {a.current_price:g})"
        return (
            f"{time_str}  {a.stock} TOUCHED {level_desc} "
            f"(price {a.current_price:g}, {a.distance_pct:.1f}% away)"
        )

    if a.alert_reason == "approaching":
        return (
            f"{time_str}  {a.stock} is approaching {level_desc} "
            f"(price {a.current_price:g}, {a.distance_pct:.1f}% away)"
        )

    if a.alert_reason == "override":
        return (
            f"{time_str}  {a.stock} made a fast move near {level_desc} "
            f"(price {a.current_price:g}, {a.distance_pct:.1f}% away)"
        )

    # Fallback for any future alert_reason we haven't special-cased yet
    return (
        f"{time_str}  {a.stock} {a.alert_reason} on {level_desc} "
        f"(price {a.current_price:g}, {a.distance_pct:.1f}% away)"
    )


def print_replay_summary(
    alerts: List[AlertEvent],
    stock_symbol: str,
    verbose: bool = False,
) -> None:
    """Print a clean, human-readable summary of replay results.

    Args:
        alerts: list of AlertEvents from replay_csv()
        stock_symbol: e.g. "RELIANCE"
        verbose: if False (default), print a simple plain-English one-line-per-alert
                 feed. If True, print the original detailed/aligned debug format
                 with raw distance percentages and fixed-width columns.
    """
    print("=" * 70)
    print(f"  REPLAY SUMMARY — {stock_symbol}")
    print("=" * 70)

    if not alerts:
        print("  No alerts fired during this replay period.")
        print("=" * 70)
        return

    counts = {"touch": 0, "approaching": 0, "override": 0}
    for a in alerts:
        counts[a.alert_reason] = counts.get(a.alert_reason, 0) + 1

    print(f"  {len(alerts)} alerts total "
          f"({counts['touch']} touches, {counts['approaching']} approaches, "
          f"{counts['override']} fast-move overrides)")
    print()

    if verbose:
        print("  Chronological alert log (verbose):")
        print("  " + "-" * 66)
        for a in alerts:
            print(
                f"  {a.timestamp.strftime('%Y-%m-%d %H:%M')}  |  "
                f"{a.stock:8s}  {a.level_type:10s} {a.level:8.2f}  |  "
                f"reason={a.alert_reason:11s}  price={a.current_price:8.2f}  "
                f"dist={a.distance_pct:5.2f}%"
            )
    else:
        print("  What would have happened:")
        for a in alerts:
            print("  " + _format_plain_english(a))

    print("=" * 70)