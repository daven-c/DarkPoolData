"""Tests for the startup/runtime Diagnostics severity classifier.

Run: pytest backend/app/rules/tests/test_diagnostics.py
"""

import time

from backend.app.services.diagnostics import (
    SEVERITY_ERROR,
    SEVERITY_OK,
    SEVERITY_WARN,
    Diagnostics,
)


def test_default_state_is_off_and_errors():
    d = Diagnostics()
    snap = d.snapshot()
    assert snap["mode"] == "off"
    assert snap["severity"] == SEVERITY_ERROR
    assert "no API key" in snap["message"].lower() or "engine offline" in snap["message"].lower()
    assert snap["first_event_received"] is False
    assert snap["seconds_since_last_event"] is None


def test_simulate_mode_is_warn_with_recent_events():
    d = Diagnostics()
    d.set(mode="simulate", universe_source="simulate", universe_size=10)
    snap = d.snapshot(last_event_ts=time.time() - 1)
    assert snap["severity"] == SEVERITY_WARN
    assert "simulation" in snap["message"].lower()
    assert snap["first_event_received"] is True


def test_simulate_mode_silence_escalates_to_error():
    d = Diagnostics()
    d.set(mode="simulate")
    # 60s > 30s simulation threshold → error
    snap = d.snapshot(last_event_ts=time.time() - 60)
    assert snap["severity"] == SEVERITY_ERROR
    assert "mockstreamer" in snap["message"].lower() or "synthetic" in snap["message"].lower()


def test_live_mode_silent_during_open_market_is_error():
    d = Diagnostics()
    d.set(mode="live", api_key_configured=True, universe_size=1000)
    # 10 min of silence while market is open → red
    snap = d.snapshot(last_event_ts=time.time() - 600, market_status="open")
    assert snap["severity"] == SEVERITY_ERROR
    assert "silent" in snap["message"].lower() or "connection" in snap["message"].lower()


def test_live_mode_silent_when_market_closed_is_ok():
    d = Diagnostics()
    d.set(mode="live", api_key_configured=True, universe_size=1000)
    snap = d.snapshot(last_event_ts=time.time() - 600, market_status="closed")
    assert snap["severity"] == SEVERITY_OK


def test_live_mode_waiting_for_first_tick_is_warn():
    d = Diagnostics()
    d.set(mode="live")
    snap = d.snapshot(last_event_ts=None, market_status="open")
    assert snap["severity"] == SEVERITY_WARN
    assert "waiting" in snap["message"].lower() or "first" in snap["message"].lower()


def test_live_mode_healthy_when_events_flowing():
    d = Diagnostics()
    d.set(mode="live", api_key_configured=True)
    snap = d.snapshot(last_event_ts=time.time() - 2, market_status="open")
    assert snap["severity"] == SEVERITY_OK
    assert snap["message"] == "Engine healthy."


def test_boot_warning_demotes_ok_to_warn():
    d = Diagnostics()
    d.set(mode="live")
    d.add_warning("Prior-day backfill failed: timeout. Daily-change percentages will be missing.")
    snap = d.snapshot(last_event_ts=time.time() - 1, market_status="open")
    assert snap["severity"] == SEVERITY_WARN
    assert "prior-day" in snap["message"].lower()
    assert snap["boot_warnings"] == [
        "Prior-day backfill failed: timeout. Daily-change percentages will be missing."
    ]


def test_add_warning_is_idempotent():
    d = Diagnostics()
    d.add_warning("same")
    d.add_warning("same")
    d.add_warning("different")
    snap = d.snapshot()
    assert snap["boot_warnings"] == ["same", "different"]


def test_seconds_since_last_event_rounded():
    d = Diagnostics()
    d.set(mode="simulate")
    snap = d.snapshot(last_event_ts=time.time() - 3.456)
    assert isinstance(snap["seconds_since_last_event"], float)
    assert 3.0 <= snap["seconds_since_last_event"] <= 4.0
