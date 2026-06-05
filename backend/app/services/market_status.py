"""In-memory TTL cache for the Massive market-status endpoint.

The upstream call is rate-limited and the value only changes at session
boundaries (open / close / extended-hours flips), so we don't want to hit
it on every /health poll. A simple async-safe single-flight cache fits.
"""

import asyncio
import time
from typing import Any, Dict, Optional

from backend.app.core.config import settings


_UNKNOWN: Dict[str, Any] = {
    "market": "unknown",
    "server_time": None,
    "exchanges": {},
    "currencies": {},
    "early_hours": None,
    "after_hours": None,
}


class MarketStatusCache:
    def __init__(self, service: Optional[Any] = None, ttl_s: Optional[int] = None):
        if service is None:
            # Lazy import so this module is usable in environments where the
            # massive SDK isn't installed (e.g. unit tests with a stub).
            from backend.app.services.massive import MassiveService
            service = MassiveService()
        self._service = service
        self._ttl_s = ttl_s if ttl_s is not None else settings.MARKET_STATUS_CACHE_TTL_S
        self._lock = asyncio.Lock()
        self._value: Dict[str, Any] = dict(_UNKNOWN)
        self._fetched_at: float = 0.0  # epoch seconds of last successful upstream fetch
        self._checked_at: float = 0.0  # epoch seconds of last attempt (success or fallback)

    def _fresh(self, now: float) -> bool:
        return self._checked_at > 0 and (now - self._checked_at) < self._ttl_s

    async def get(self) -> Dict[str, Any]:
        """Return the cached status, refreshing if stale. Single-flight under the lock."""
        now = time.time()
        if self._fresh(now):
            return self._snapshot()

        async with self._lock:
            now = time.time()
            if self._fresh(now):
                return self._snapshot()
            await self._refresh_locked()
            return self._snapshot()

    async def _refresh_locked(self) -> None:
        # Offload the blocking SDK call so we don't stall the event loop.
        data = await asyncio.to_thread(self._service.get_market_status)
        self._checked_at = time.time()
        if data.get("market") and data["market"] != "unknown":
            self._fetched_at = self._checked_at
            self._value = data
        else:
            # Upstream failed — surface "unknown" but still respect TTL on retries.
            self._value = dict(_UNKNOWN)

    def force_refresh(self) -> None:
        """Reset cache so the next get() refetches. Test hook."""
        self._checked_at = 0.0
        self._fetched_at = 0.0

    def _snapshot(self) -> Dict[str, Any]:
        return {
            **self._value,
            "checked_at": self._checked_at or None,
            "fetched_at": self._fetched_at or None,
        }


_default_cache: Optional[MarketStatusCache] = None


def get_default_cache() -> MarketStatusCache:
    global _default_cache
    if _default_cache is None:
        _default_cache = MarketStatusCache()
    return _default_cache


def reset_default_cache() -> None:
    """Test hook — clear the module-level singleton."""
    global _default_cache
    _default_cache = None
