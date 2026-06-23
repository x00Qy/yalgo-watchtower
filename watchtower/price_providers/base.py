"""Base classes and exceptions for price providers."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


class ProviderNotConfigured(Exception):
    """Raised when a provider is missing required env vars / config."""


class ProviderFetchError(Exception):
    """Raised when a provider is configured but a fetch attempt fails."""


@dataclass
class PriceQuote:
    symbol: str
    price: float
    timestamp: datetime
    source: str = ""
    raw_data: Dict[str, Any] = field(default_factory=dict)


class PriceProvider(ABC):
    @abstractmethod
    def fetch_batch(self, symbols: list[str]) -> dict[str, PriceQuote]:
        ...
