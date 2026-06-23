"""
Main polling loop. Runs every 5 minutes. Coordinates price fetching and alert engine.
Auto-stops at 3:30 PM IST (market close).
"""
import time
from datetime import datetime
from watchtower.price_fetcher import fetch_prices
from watchtower.alert_engine import AlertEngine

MARKET_CLOSE = (15, 30)  # 3:30 PM IST


def _market_closed() -> bool:
    now = datetime.now()
    return (now.hour, now.minute) >= MARKET_CLOSE


def run_poller(watchlist: dict, interval_seconds: int = 300) -> None:
    engine = AlertEngine(watchlist)
    while True:
        if _market_closed():
            print("[poller] Market closed (past 3:30 PM) — shutting down.")
            break
        try:
            now_str = datetime.now().strftime("%H:%M:%S")
            print(f"[poller] {now_str} — polling {len(watchlist)} symbols")
            symbols = list(watchlist.keys())
            prices, failures = fetch_prices(symbols)
            if failures:
                print(f"[poller] Failed to fetch: {', '.join(failures)}")
            if not prices:
                print("[poller] No prices fetched — skipping this poll")
                time.sleep(interval_seconds)
                continue
            results = engine.process_prices(prices)
            print(f"[poller] Poll done — {len(results)} alert(s) fired")
        except Exception as e:
            print(f"[poller] Unexpected error: {e}")
        time.sleep(interval_seconds)