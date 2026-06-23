"""Angel One SmartAPI price provider.

Faithful Python port of the user's proven TypeScript P2 code.
Session caching, TOTP via pyotp, batch quote API, symbol token resolution.
"""
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
import requests

import pyotp

from watchtower.price_providers.base import (
    PriceProvider, PriceQuote, ProviderNotConfigured, ProviderFetchError,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://apiconnect.angelone.in"

# Module-level session cache (same lifetime semantics as P2 TypeScript)
_session: Optional[Dict[str, Any]] = None


def _load_symbol_tokens() -> Dict[str, str]:
    """Load the symbol -> token cache from symbol_tokens.json."""
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(base, "watchtower", "symbol_tokens.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


_SYMBOL_TOKENS = _load_symbol_tokens()


def _get_sanity_ranges() -> Dict[str, tuple]:
    """Load configurable price sanity ranges."""
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(base, "watchtower", "price_sanity_ranges.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
            return {k: tuple(v) for k, v in raw.items()}
    except Exception:
        return {}


_SANITY_RANGES = _get_sanity_ranges()


def _generate_totp(secret: str) -> str:
    clean = secret.replace(" ", "").upper()
    return pyotp.TOTP(clean).now()


def _get_session(
    api_key: str, client_id: str, mpin: str, totp_secret: str
) -> Optional[Dict[str, Any]]:
    global _session
    now_ms = int(datetime.utcnow().timestamp() * 1000)
    if _session and now_ms < _session.get("expiresAt", 0) - 30 * 60 * 1000:
        return _session

    try:
        totp = _generate_totp(totp_secret)
        payload = {"clientcode": client_id, "password": mpin, "totp": totp}
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-UserType": "USER",
            "X-SourceID": "WEB",
            "X-ClientLocalIP": "127.0.0.1",
            "X-ClientPublicIP": "127.0.0.1",
            "X-MACAddress": "00:00:00:00:00:00",
            "X-PrivateKey": api_key,
        }
        resp = requests.post(
            f"{BASE_URL}/rest/auth/angelbroking/user/v1/loginByPassword",
            json=payload,
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("data", {}).get("jwtToken"):
            logger.error("Angel One login failed: %s", data.get("message", "Unknown"))
            return None

        _session = {
            "jwtToken": data["data"]["jwtToken"],
            "refreshToken": data["data"]["refreshToken"],
            "feedToken": data["data"]["feedToken"],
            "expiresAt": now_ms + 8 * 60 * 60 * 1000,
        }
        return _session
    except Exception as e:
        logger.error("Angel One session error: %s", e)
        return None


def _get_symbol_token(symbol: str, api_key: str, jwt_token: str) -> Optional[str]:
    if symbol in _SYMBOL_TOKENS:
        return _SYMBOL_TOKENS[symbol]

    try:
        payload = {"exchange": "NSE", "searchscrip": symbol}
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-UserType": "USER",
            "X-SourceID": "WEB",
            "X-ClientLocalIP": "127.0.0.1",
            "X-ClientPublicIP": "127.0.0.1",
            "X-MACAddress": "00:00:00:00:00:00",
            "X-PrivateKey": api_key,
        }
        resp = requests.post(
            f"{BASE_URL}/rest/secure/angelbroking/order/v1/searchScrip",
            json=payload,
            headers=headers,
            timeout=5,
        )
        resp.raise_for_status()
        scrips = resp.json().get("data", {}).get("scrips", [])
        match = None
        for s in scrips:
            if s.get("tradingsymbol") == f"{symbol}-EQ" and s.get("exch_seg") == "NSE":
                match = s.get("symboltoken")
                break
        if match:
            logger.warning(
                "Symbol %s not found in symbol_tokens.json cache; used live searchScrip lookup. "
                "Consider re-running scripts/lookup_angel_tokens.py to cache it.",
                symbol,
            )
            return match
        return None
    except Exception:
        return None


class AngelOneProvider(PriceProvider):

    def __init__(self):
        self._api_key = os.getenv("ANGEL_ONE_API_KEY")
        self._client_id = os.getenv("ANGEL_ONE_CLIENT_ID")
        self._mpin = os.getenv("ANGEL_ONE_MPIN")
        self._totp_secret = os.getenv("ANGEL_ONE_TOTP_SECRET")

        missing = []
        for name, val in [
            ("ANGEL_ONE_API_KEY", self._api_key),
            ("ANGEL_ONE_CLIENT_ID", self._client_id),
            ("ANGEL_ONE_MPIN", self._mpin),
            ("ANGEL_ONE_TOTP_SECRET", self._totp_secret),
        ]:
            if not val:
                missing.append(name)
        if missing:
            raise ProviderNotConfigured(
                f"Angel One not configured: missing {', '.join(missing)} in .env"
            )

    def fetch_batch(self, symbols: list[str]) -> dict[str, PriceQuote]:
        if not symbols:
            return {}

        session = _get_session(
            self._api_key, self._client_id, self._mpin, self._totp_secret
        )
        if not session:
            raise ProviderFetchError("Angel One session failed — check credentials")

        jwt_token = session["jwtToken"]

        token_map: Dict[str, str] = {}
        for sym in symbols:
            token = _get_symbol_token(sym, self._api_key, jwt_token)
            if token:
                token_map[sym] = token
            else:
                logger.warning("Angel One: could not resolve token for %s", sym)

        if not token_map:
            return {}

        reverse_map = {v: k for k, v in token_map.items()}

        try:
            payload = {
                "mode": "FULL",
                "exchangeTokens": {"NSE": list(token_map.values())},
            }
            headers = {
                "Authorization": f"Bearer {jwt_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-UserType": "USER",
                "X-SourceID": "WEB",
                "X-ClientLocalIP": "127.0.0.1",
                "X-ClientPublicIP": "127.0.0.1",
                "X-MACAddress": "00:00:00:00:00:00",
                "X-PrivateKey": self._api_key,
            }
            resp = requests.post(
                f"{BASE_URL}/rest/secure/angelbroking/market/v1/quote/",
                json=payload,
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            fetched = data.get("data", {}).get("fetched", [])
        except Exception as e:
            raise ProviderFetchError(f"Angel One batch quote failed: {e}")

        results: dict[str, PriceQuote] = {}
        now = datetime.utcnow()

        for item in fetched:
            token = item.get("symbolToken") or item.get("token")
            sym = reverse_map.get(token)
            if not sym:
                continue

            ltp_str = item.get("ltp")
            if ltp_str is None:
                continue
            try:
                ltp = float(ltp_str)
            except (ValueError, TypeError):
                continue
            if ltp <= 0:
                continue

            if sym in _SANITY_RANGES:
                lo, hi = _SANITY_RANGES[sym]
                if not (lo <= ltp <= hi):
                    logger.warning(
                        "AngelOne returned %s @ %.2f, outside sane range [%.2f, %.2f] — rejected",
                        sym, ltp, lo, hi,
                    )
                    continue

            close_str = item.get("close")
            try:
                close = float(close_str) if close_str is not None else ltp
            except (ValueError, TypeError):
                close = ltp

            results[sym] = PriceQuote(
                symbol=sym,
                price=ltp,
                timestamp=now,
                source="AngelOne",
                raw_data={
                    "dayHigh": item.get("high"),
                    "dayLow": item.get("low"),
                    "volume": item.get("tradeVolume"),
                    "close": close,
                    "change": ltp - close,
                    "changePercent": ((ltp - close) / close * 100) if close > 0 else 0,
                },
            )

        return results
