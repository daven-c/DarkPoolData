"""Startup + runtime diagnostics surfaced via /dashboard/health.

A single thread-safe `Diagnostics` instance is created in the FastAPI lifespan,
populated as boot progresses (API key check, universe seed, streamer mode,
prior-day backfill), and read by the health endpoint so the frontend can show
a clear degraded-state banner instead of silently rendering an empty dashboard.

Anything that mutates a field calls `set(...)` under the lock so multi-threaded
seed/backfill writers don't race the request handler. `snapshot()` is what the
endpoint emits; it also derives a top-level severity (`ok` / `warn` / `error`)
plus a human-readable message so the frontend doesn't have to duplicate the
decision logic.
"""

import threading
import time
from typing import Any, Dict, List, Optional


# Severity ladder used by /health and the frontend banner.
SEVERITY_OK = "ok"          # green: live + connected + receiving events
SEVERITY_WARN = "warn"      # amber: simulating, or waiting on first event, or seed still running
SEVERITY_ERROR = "error"    # red: engine cannot produce signals (no key + no sim, or feed silent for too long)


class Diagnostics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: Dict[str, Any] = {
            "mode": "off",                       # "live" | "simulate" | "off"
            "api_key_configured": False,
            "universe_size": 0,
            "universe_source": "empty",          # "live" | "simulate" | "empty"
            "prior_day_seed": "skipped",         # "pending" | "complete" | "failed" | "skipped"
            "boot_warnings": [],                 # human-readable strings; survives until restart
            "started_at": time.time(),
        }

    def set(self, **fields: Any) -> None:
        with self._lock:
            self._data.update(fields)

    def add_warning(self, message: str) -> None:
        with self._lock:
            warnings: List[str] = self._data.setdefault("boot_warnings", [])
            if message not in warnings:
                warnings.append(message)

    def snapshot(self, last_event_ts: Optional[float] = None, market_status: Optional[str] = None) -> Dict[str, Any]:
        """Build the payload exposed via /dashboard/health.

        `last_event_ts` and `market_status` are passed in by the endpoint so the
        severity calculation can fold in the engine's freshness and the upstream
        session state without this module needing to know about either.
        """
        with self._lock:
            data = dict(self._data)
            warnings = list(data.get("boot_warnings", []))

        now = time.time()
        seconds_since_last_event = (now - last_event_ts) if last_event_ts else None
        first_event_received = last_event_ts is not None

        severity, message = _classify(
            mode=data["mode"],
            seconds_since_last_event=seconds_since_last_event,
            first_event_received=first_event_received,
            market_status=market_status,
            warnings=warnings,
        )

        data.update(
            seconds_since_last_event=round(seconds_since_last_event, 1) if seconds_since_last_event else None,
            first_event_received=first_event_received,
            severity=severity,
            message=message,
        )
        return data


# Silence thresholds (seconds). Tuned per mode: simulate runs at ~20/s by default,
# so a 30s gap means the thread died; live can be quiet during low-volume minutes,
# so we allow 5 minutes before raising the alarm.
_SILENCE_S_SIMULATE = 30.0
_SILENCE_S_LIVE = 300.0


def _classify(
    mode: str,
    seconds_since_last_event: Optional[float],
    first_event_received: bool,
    market_status: Optional[str],
    warnings: List[str],
) -> tuple[str, str]:
    """Decide overall severity + a one-line message for the banner."""
    if mode == "off":
        return SEVERITY_ERROR, "Engine offline: no API key set and simulation disabled. Set MASSIVE_API_KEY or SIMULATE_STREAM=true."

    if mode == "simulate":
        if seconds_since_last_event is not None and seconds_since_last_event > _SILENCE_S_SIMULATE:
            return SEVERITY_ERROR, f"Simulation mode but no synthetic events for {int(seconds_since_last_event)}s — MockStreamer may have died."
        return SEVERITY_WARN, "Simulation mode — engine driven by synthetic data, not the live market."

    # mode == "live"
    if not first_event_received:
        # WS connected but nothing received yet. Only loud if the market is open.
        if market_status == "open":
            return SEVERITY_WARN, "Live feed connected but no trades received yet — waiting on the first tick."
        return SEVERITY_WARN, "Live feed connected, waiting for the first trade (market may be closed)."

    if seconds_since_last_event is not None and market_status == "open" and seconds_since_last_event > _SILENCE_S_LIVE:
        return SEVERITY_ERROR, f"Live feed silent for {int(seconds_since_last_event // 60)} min during market hours — connection may have dropped."

    if warnings:
        return SEVERITY_WARN, warnings[0]

    return SEVERITY_OK, "Engine healthy."
