"""RapidAPI price provider — STUB.

TODO: Real implementation pending user obtaining RapidAPI key and confirming
      the specific API endpoint / subscription plan for NSE India stock prices.
      For now, this stub raises ProviderNotConfigured if RAPIDAPI_KEY is missing.
"""
import os
from watchtower.price_providers.base import PriceProvider, PriceQuote, ProviderNotConfigured


class RapidAPIProvider(PriceProvider):
    """RapidAPI provider (stub — awaiting real API confirmation)."""

    def __init__(self):
        self._api_key = os.getenv("RAPIDAPI_KEY")
        if not self._api_key:
            raise ProviderNotConfigured(
                "RapidAPI not configured: set RAPIDAPI_KEY in .env"
            )

    def fetch_batch(self, symbols: list[str]) -> dict[str, PriceQuote]:
        """Not yet implemented — will be built once API access is confirmed."""
        raise ProviderNotConfigured(
            "RapidAPI provider is a stub awaiting real API implementation. "
            "Set RAPIDAPI_KEY and confirm the NSE stock price endpoint before enabling."
        )
