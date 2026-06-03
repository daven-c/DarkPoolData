"""Tests for the MarketStatusCache TTL + fallback behavior.

Run: pytest backend/app/rules/tests/test_market_status.py
"""

import asyncio
import time

import pytest

from backend.app.services.market_status import MarketStatusCache


class _CountingService:
    def __init__(self, payload):
        self.calls = 0
        self.payload = payload

    def get_market_status(self):
        self.calls += 1
        return dict(self.payload)


class _FailingService:
    def __init__(self):
        self.calls = 0

    def get_market_status(self):
        self.calls += 1
        # MassiveService.get_market_status() already catches and returns
        # an "unknown" dict — mimic that contract here.
        return {"market": "unknown", "server_time": None, "exchanges": {}, "currencies": {}}


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


def test_cache_serves_within_ttl():
    svc = _CountingService({"market": "open", "server_time": "2026-06-03T14:30:00Z",
                            "exchanges": {}, "currencies": {}})
    cache = MarketStatusCache(service=svc, ttl_s=60)

    async def go():
        a = await cache.get()
        b = await cache.get()
        c = await cache.get()
        return a, b, c

    a, b, c = _run(go())
    assert svc.calls == 1, "TTL not respected — upstream hit more than once"
    assert a["market"] == "open"
    assert b["market"] == "open"
    assert c["market"] == "open"
    assert a["checked_at"] is not None


def test_cache_refreshes_after_ttl():
    svc = _CountingService({"market": "open", "server_time": None,
                            "exchanges": {}, "currencies": {}})
    cache = MarketStatusCache(service=svc, ttl_s=0)  # always stale

    async def go():
        await cache.get()
        await cache.get()
        await cache.get()

    _run(go())
    assert svc.calls == 3, f"expected 3 refreshes with TTL=0, got {svc.calls}"


def test_force_refresh_clears_freshness():
    svc = _CountingService({"market": "open", "server_time": None,
                            "exchanges": {}, "currencies": {}})
    cache = MarketStatusCache(service=svc, ttl_s=3600)

    async def go():
        await cache.get()
        cache.force_refresh()
        await cache.get()

    _run(go())
    assert svc.calls == 2


def test_unknown_fallback_when_upstream_fails():
    svc = _FailingService()
    cache = MarketStatusCache(service=svc, ttl_s=60)

    async def go():
        return await cache.get()

    result = _run(go())
    assert result["market"] == "unknown"
    assert result["checked_at"] is not None  # we did attempt
    assert result["fetched_at"] is None       # but never succeeded
    assert svc.calls == 1


def test_concurrent_reads_single_flight():
    """20 concurrent get() calls on a cold cache should only trigger one upstream fetch."""
    svc = _CountingService({"market": "closed", "server_time": None,
                            "exchanges": {}, "currencies": {}})
    cache = MarketStatusCache(service=svc, ttl_s=60)

    async def go():
        return await asyncio.gather(*(cache.get() for _ in range(20)))

    results = _run(go())
    assert svc.calls == 1
    assert all(r["market"] == "closed" for r in results)
