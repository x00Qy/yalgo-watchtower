"""Unit tests for price_fetcher fallback chain logic.

Uses mocked/fake providers — no real network calls.
Run with: python -m unittest tests.test_price_fetcher -v
"""
import sys
import os
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from watchtower.price_fetcher import fetch_prices, _price_cache, CACHE_TTL_SECONDS
from watchtower.price_providers.base import (
    PriceProvider, PriceQuote, ProviderNotConfigured, ProviderFetchError,
)


class FakeProviderAll(PriceProvider):
    def __init__(self, prices: dict):
        self.prices = prices
        self.call_count = 0
        self.last_symbols = []

    def fetch_batch(self, symbols: list[str]) -> dict[str, PriceQuote]:
        self.call_count += 1
        self.last_symbols = list(symbols)
        result = {}
        for sym in symbols:
            if sym in self.prices:
                result[sym] = PriceQuote(
                    symbol=sym,
                    price=self.prices[sym],
                    timestamp=datetime.utcnow(),
                    source="FakeAll",
                )
        return result


class FakeProviderPartial(PriceProvider):
    def __init__(self, prices: dict):
        self.prices = prices
        self.call_count = 0
        self.last_symbols = []

    def fetch_batch(self, symbols: list[str]) -> dict[str, PriceQuote]:
        self.call_count += 1
        self.last_symbols = list(symbols)
        result = {}
        for sym in symbols:
            if sym in self.prices:
                result[sym] = PriceQuote(
                    symbol=sym,
                    price=self.prices[sym],
                    timestamp=datetime.utcnow(),
                    source="FakePartial",
                )
        return result


class FakeProviderFetchError(PriceProvider):
    def fetch_batch(self, symbols: list[str]) -> dict[str, PriceQuote]:
        raise ProviderFetchError("Network down")


class FakeProviderEmpty(PriceProvider):
    def fetch_batch(self, symbols: list[str]) -> dict[str, PriceQuote]:
        return {}


def _clear_cache():
    _price_cache.clear()


class TestPriceFetcher(unittest.TestCase):

    def setUp(self):
        _clear_cache()

    @patch("watchtower.price_fetcher.TwelveDataProvider")
    @patch("watchtower.price_fetcher.RapidAPIProvider")
    @patch("watchtower.price_fetcher.AngelOneProvider")
    def test_first_provider_all_success_others_not_called(self, MockAngel, MockRapid, MockTwelve):
        twelve = FakeProviderAll({"RELIANCE": 3000.0, "TCS": 4000.0})
        MockTwelve.return_value = twelve
        MockRapid.side_effect = ProviderNotConfigured("not configured")
        MockAngel.side_effect = ProviderNotConfigured("not configured")

        prices, failures = fetch_prices(["RELIANCE", "TCS"])

        self.assertEqual(len(prices), 2)
        self.assertEqual(prices["RELIANCE"].price, 3000.0)
        self.assertEqual(prices["TCS"].price, 4000.0)
        self.assertEqual(len(failures), 0)
        self.assertEqual(twelve.call_count, 1)
        self.assertEqual(set(twelve.last_symbols), {"RELIANCE", "TCS"})
        MockRapid.assert_not_called()
        MockAngel.assert_not_called()

    @patch("watchtower.price_fetcher.TwelveDataProvider")
    @patch("watchtower.price_fetcher.RapidAPIProvider")
    @patch("watchtower.price_fetcher.AngelOneProvider")
    def test_first_not_configured_skips_to_second(self, MockAngel, MockRapid, MockTwelve):
        MockTwelve.side_effect = ProviderNotConfigured("no key")
        rapid = FakeProviderAll({"RELIANCE": 3000.0})
        MockRapid.return_value = rapid
        MockAngel.side_effect = ProviderNotConfigured("not configured")

        prices, failures = fetch_prices(["RELIANCE"])

        self.assertEqual(len(prices), 1)
        self.assertEqual(prices["RELIANCE"].price, 3000.0)
        self.assertEqual(len(failures), 0)
        self.assertEqual(rapid.call_count, 1)

    @patch("watchtower.price_fetcher.TwelveDataProvider")
    @patch("watchtower.price_fetcher.RapidAPIProvider")
    @patch("watchtower.price_fetcher.AngelOneProvider")
    def test_first_fetch_error_skips_to_second(self, MockAngel, MockRapid, MockTwelve):
        MockTwelve.side_effect = ProviderFetchError("rate limited")
        rapid = FakeProviderAll({"RELIANCE": 3000.0})
        MockRapid.return_value = rapid
        MockAngel.side_effect = ProviderNotConfigured("not configured")

        prices, failures = fetch_prices(["RELIANCE"])

        self.assertEqual(len(prices), 1)
        self.assertEqual(prices["RELIANCE"].price, 3000.0)
        self.assertEqual(len(failures), 0)
        self.assertEqual(rapid.call_count, 1)

    @patch("watchtower.price_fetcher.TwelveDataProvider")
    @patch("watchtower.price_fetcher.RapidAPIProvider")
    @patch("watchtower.price_fetcher.AngelOneProvider")
    def test_partial_success_passes_remaining(self, MockAngel, MockRapid, MockTwelve):
        twelve = FakeProviderPartial({"RELIANCE": 3000.0, "TCS": 4000.0, "INFY": 1500.0})
        MockTwelve.return_value = twelve
        rapid = FakeProviderPartial({"HDFCBANK": 1600.0, "KOTAKBANK": 1800.0})
        MockRapid.return_value = rapid
        MockAngel.side_effect = ProviderNotConfigured("not configured")

        prices, failures = fetch_prices(["RELIANCE", "TCS", "INFY", "HDFCBANK", "KOTAKBANK"])

        self.assertEqual(len(prices), 5)
        self.assertEqual(prices["RELIANCE"].price, 3000.0)
        self.assertEqual(prices["HDFCBANK"].price, 1600.0)
        self.assertEqual(set(twelve.last_symbols), {"RELIANCE", "TCS", "INFY", "HDFCBANK", "KOTAKBANK"})
        self.assertEqual(set(rapid.last_symbols), {"HDFCBANK", "KOTAKBANK"})

    @patch("watchtower.price_fetcher.TwelveDataProvider")
    @patch("watchtower.price_fetcher.RapidAPIProvider")
    @patch("watchtower.price_fetcher.AngelOneProvider")
    def test_all_exhausted_returns_partial_and_failures(self, MockAngel, MockRapid, MockTwelve):
        MockTwelve.side_effect = ProviderNotConfigured("no key")
        MockRapid.side_effect = ProviderFetchError("network down")
        MockAngel.return_value = FakeProviderPartial({"RELIANCE": 3000.0})

        prices, failures = fetch_prices(["RELIANCE", "TCS"])

        self.assertEqual(len(prices), 1)
        self.assertIn("RELIANCE", prices)
        self.assertEqual(len(failures), 1)
        self.assertIn("TCS", failures[0])

    @patch("watchtower.price_fetcher.TwelveDataProvider")
    @patch("watchtower.price_fetcher.RapidAPIProvider")
    @patch("watchtower.price_fetcher.AngelOneProvider")
    def test_cache_hit_avoids_provider_calls(self, MockAngel, MockRapid, MockTwelve):
        twelve = FakeProviderAll({"RELIANCE": 3000.0})
        MockTwelve.return_value = twelve
        MockRapid.side_effect = ProviderNotConfigured("not configured")
        MockAngel.side_effect = ProviderNotConfigured("not configured")

        prices1, _ = fetch_prices(["RELIANCE"])
        self.assertEqual(twelve.call_count, 1)

        prices2, _ = fetch_prices(["RELIANCE"])
        self.assertEqual(twelve.call_count, 1)
        self.assertEqual(prices2["RELIANCE"].price, 3000.0)

    @patch("watchtower.price_fetcher.TwelveDataProvider")
    @patch("watchtower.price_fetcher.RapidAPIProvider")
    @patch("watchtower.price_fetcher.AngelOneProvider")
    def test_cache_expiry_recalls_providers(self, MockAngel, MockRapid, MockTwelve):
        twelve = FakeProviderAll({"RELIANCE": 3000.0})
        MockTwelve.return_value = twelve
        MockRapid.side_effect = ProviderNotConfigured("not configured")
        MockAngel.side_effect = ProviderNotConfigured("not configured")

        fetch_prices(["RELIANCE"])
        self.assertEqual(twelve.call_count, 1)

        from watchtower.price_fetcher import _price_cache
        sym = "RELIANCE"
        if sym in _price_cache:
            quote, ts = _price_cache[sym]
            _price_cache[sym] = (quote, ts - timedelta(seconds=CACHE_TTL_SECONDS + 1))

        fetch_prices(["RELIANCE"])
        self.assertEqual(twelve.call_count, 2)

    @patch.dict(os.environ, {}, clear=True)
    def test_angel_one_not_configured_raises(self):
        from watchtower.price_providers.angel_one import AngelOneProvider
        with self.assertRaises(ProviderNotConfigured) as ctx:
            AngelOneProvider()
        self.assertIn("Angel One not configured", str(ctx.exception))

    def test_empty_symbols_returns_empty(self):
        prices, failures = fetch_prices([])
        self.assertEqual(prices, {})
        self.assertEqual(failures, [])

    @patch("watchtower.price_fetcher.TwelveDataProvider")
    @patch("watchtower.price_fetcher.RapidAPIProvider")
    @patch("watchtower.price_fetcher.AngelOneProvider")
    def test_duplicate_symbols_deduplicated(self, MockAngel, MockRapid, MockTwelve):
        twelve = FakeProviderAll({"RELIANCE": 3000.0})
        MockTwelve.return_value = twelve
        MockRapid.side_effect = ProviderNotConfigured("not configured")
        MockAngel.side_effect = ProviderNotConfigured("not configured")

        prices, failures = fetch_prices(["RELIANCE", "RELIANCE", "RELIANCE"])
        self.assertEqual(len(prices), 1)
        self.assertEqual(twelve.call_count, 1)
        self.assertEqual(twelve.last_symbols, ["RELIANCE"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
