"""Yahoo Finance price provider — fallback for stocks Angel One can't serve."""
import logging
from datetime import datetime, timezone

import yfinance as yf

from watchtower.price_providers.base import (
    PriceProvider, PriceQuote, ProviderFetchError,
)

logger = logging.getLogger(__name__)


class YahooFinanceProvider(PriceProvider):
    """Fetches prices via yfinance. No auth required.
    
    Appends .NS (NSE) suffix to all symbols.
    Falls back to .BO (BSE) if NSE returns no data.
    """

    def fetch_batch(self, symbols: list[str]) -> dict[str, PriceQuote]:
        results = {}
        for sym in symbols:
            price = self._fetch_one(sym)
            if price is not None:
                results[sym] = PriceQuote(
                    symbol=sym,
                    price=price,
                    timestamp=datetime.now(timezone.utc),
                    source="yahoo_finance",
                )
        return results

    def _fetch_one(self, symbol: str) -> float | None:
        for suffix in [".NS", ".BO"]:
            try:
                ticker = yf.Ticker(f"{symbol}{suffix}")
                info = dict(ticker.fast_info)
                price = info.get("lastPrice") or info.get("last_price")
                if price and float(price) > 0:
                    logger.debug("Yahoo Finance: %s%s -> %.2f", symbol, suffix, price)
                    return float(price)
            except Exception as e:
                logger.debug("Yahoo Finance error for %s%s: %s", symbol, suffix, e)
        return None