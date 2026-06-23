"""Price fetcher — fallback chain orchestrator.

Chain order: TwelveData (primary) → RapidAPI (fallback 1) → AngelOne (fallback 2)

fetch_prices() returns (dict[symbol, PriceQuote], list[str failures]).
Results are cached for CACHE_TTL_SECONDS (30s by default).
Only symbols not already in cache are passed to providers.
Partial results from each provider are accumulated before moving to next.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

from watchtower.price_providers.base import (
    PriceProvider, PriceQuote, ProviderNotConfigured, ProviderFetchError,
)
from watchtower.price_providers.twelve_data import TwelveDataProvider
from watchtower.price_providers.rapidapi import RapidAPIProvider
from watchtower.price_providers.angel_one import AngelOneProvider

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 30

# Module-level cache: symbol -> (PriceQuote, fetched_at datetime)
_price_cache: Dict[str, Tuple[PriceQuote, datetime]] = {}

def fetch_prices(
    symbols: list[str],
) -> Tuple[Dict[str, PriceQuote], List[str]]:
    """Fetch prices for symbols using the fallback chain.

    Returns:
        (prices, failures)
        prices   — dict of symbol -> PriceQuote for all successfully fetched symbols
        failures — list of human-readable strings for symbols that couldn't be fetched
    """
    if not symbols:
        return {}, []

    # Deduplicate, preserving order
    seen = set()
    unique = []
    for s in symbols:
        if s not in seen:
            seen.add(s)
            unique.append(s)
    symbols = unique

    # Serve from cache where possible
    results: Dict[str, PriceQuote] = {}
    now = datetime.utcnow()
    remaining = []

    for sym in symbols:
        if sym in _price_cache:
            quote, fetched_at = _price_cache[sym]
            age = (now - fetched_at).total_seconds()
            if age < CACHE_TTL_SECONDS:
                results[sym] = quote
                continue
        remaining.append(sym)

    if not remaining:
        return results, []

    # Build provider chain lazily at call time so unit test mocks are respected.
    # Importing the module-level names here (not a pre-built list) means
    # unittest.mock.patch('watchtower.price_fetcher.TwelveDataProvider', ...)
    # correctly intercepts instantiation.
    import watchtower.price_fetcher as _self
    provider_classes = [
        _self.TwelveDataProvider,
        _self.RapidAPIProvider,
        _self.AngelOneProvider,
    ]

    # Work through provider chain
    for ProviderClass in provider_classes:
        if not remaining:
            break

        # Capture name before instantiation — ProviderClass may be a Mock in tests
        # and Mock objects raise AttributeError on __name__ after side_effect fires.
        provider_name = getattr(ProviderClass, "__name__", repr(ProviderClass))

        # Attempt to instantiate (may raise ProviderNotConfigured)
        try:
            provider: PriceProvider = ProviderClass()
        except ProviderNotConfigured as e:
            logger.debug("Provider %s not configured, skipping: %s", provider_name, e)
            continue
        except Exception as e:
            logger.warning("Provider %s init error: %s", provider_name, e)
            continue

        # Attempt fetch
        try:
            batch = provider.fetch_batch(remaining)
        except ProviderNotConfigured as e:
            logger.debug("Provider %s not configured during fetch, skipping: %s", ProviderClass.__name__, e)
            continue
        except ProviderFetchError as e:
            logger.warning("Provider %s fetch error: %s", ProviderClass.__name__, e)
            continue
        except Exception as e:
            logger.warning("Provider %s unexpected error: %s", ProviderClass.__name__, e)
            continue

        # Accumulate results and update cache
        fetch_time = datetime.utcnow()
        for sym, quote in batch.items():
            results[sym] = quote
            _price_cache[sym] = (quote, fetch_time)

        # Only pass unfilled symbols to next provider
        remaining = [s for s in remaining if s not in results]

    # Anything still remaining is a failure
    failures = [f"No price data available for {sym}" for sym in remaining]

    return results, failures
