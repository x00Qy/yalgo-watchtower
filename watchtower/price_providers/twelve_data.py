"""Twelve Data price provider — STUB.

TODO: Real implementation pending user confirmation of free-tier India/NSE coverage.
      Do not implement real Twelve Data logic until the user confirms API access.
      For now, this stub raises ProviderNotConfigured if TWELVE_DATA_API_KEY is missing.
"""
import os
from watchtower.price_providers.base import PriceProvider, PriceQuote, ProviderNotConfigured


class TwelveDataProvider(PriceProvider):
    """Twelve Data provider (stub — awaiting real API confirmation)."""

    def __init__(self):
        self._api_key = os.getenv("TWELVE_DATA_API_KEY")
        if not self._api_key:
            raise ProviderNotConfigured(
                "Twelve Data not configured: set TWELVE_DATA_API_KEY in .env"
            )

    def fetch_batch(self, symbols: list[str]) -> dict[str, PriceQuote]:
        """Not yet implemented — will be built once API access is confirmed."""
        raise ProviderNotConfigured(
            "Twelve Data provider is a stub awaiting real API implementation. "
            "Set TWELVE_DATA_API_KEY and confirm free-tier NSE coverage before enabling."
        )
