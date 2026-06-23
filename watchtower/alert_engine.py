"""
Stateful alert engine. Wraps classifier.py per symbol per level.
Manages per-stock StockState across polls. Fires notifier on actionable alerts.
"""
from datetime import datetime
from watchtower.classifier import evaluate_poll, StockState, AlertEvent
from watchtower.price_providers.base import PriceQuote
from watchtower.notifier import send_alert


def _levels_config(watchlist_entry: dict) -> dict:
    """Normalise watchlist entry to classifier levels_config format.

    Handles both formats:
      - already dicts: [{"level": 1280, "note": ""}, ...]  → pass through as-is
      - raw numbers:   [1280, 1250]                        → wrap as [{"level": 1280}, ...]
    """
    result = {}
    for direction in ("support", "resistance"):
        levels = []
        for lv in watchlist_entry.get(direction, []):
            if isinstance(lv, dict):
                levels.append({"level": float(lv["level"])})
            else:
                levels.append({"level": float(lv)})
        result[direction] = levels
    return result


class AlertEngine:
    def __init__(self, watchlist: dict):
        self.watchlist = watchlist
        self.stock_states: dict[str, StockState] = {
            symbol: StockState() for symbol in watchlist
        }

    def process_prices(self, prices: dict[str, PriceQuote]) -> list[AlertEvent]:
        all_events: list[AlertEvent] = []
        for symbol in self.watchlist:
            if symbol not in prices:
                continue
            price = prices[symbol].price
            state = self.stock_states[symbol]
            levels_cfg = _levels_config(self.watchlist[symbol])
            events = evaluate_poll(
                stock_symbol=symbol,
                current_price=price,
                stock_state=state,
                levels_config=levels_cfg,
                current_time=datetime.now(),
            )
            for event in events:
                send_alert(event, symbol)
                print(f"  → {symbol} {event.alert_reason.upper()} {event.level_type} {event.level} @ ₹{price:.2f}")
            all_events.extend(events)
        return all_events