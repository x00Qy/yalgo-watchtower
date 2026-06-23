"""
Main polling loop. Runs every 5 minutes. Coordinates price fetching and alert engine.
Auto-stops at 3:30 PM IST (market close).
"""
import time
from datetime import datetime
from watchtower.price_fetcher import fetch_prices
from watchtower.alert_engine import AlertEngine

MARKET_CLOSE = (15, 30)


def _market_closed() -> bool:
    now = datetime.now()
    return (now.hour, now.minute) >= MARKET_CLOSE


def run_poller(watchlist: dict, interval_seconds: int = 300) -> None:
    engine = AlertEngine(watchlist)
    while True:
        if _market_closed():
            print("\n[watchtower] Market closed — shutting down.")
            break
        now_str = datetime.now().strftime("%H:%M:%S")
        print(f"\n[{now_str}] polling {len(watchlist)} symbols")
        try:
            symbols = list(watchlist.keys())
            prices, failures = fetch_prices(symbols)
            if failures:
                print(f"  ! failed: {', '.join(failures)}")
            if not prices:
                print("  ! no prices fetched — skipping")
                time.sleep(interval_seconds)
                continue
            results = engine.process_prices(prices)
            if results:
                print(f"  ✓ {len(results)} alert(s) fired")
            else:
                print("  ✓ no alerts")
        except Exception as e:
            print(f"  ! error: {e}")
        time.sleep(interval_seconds)