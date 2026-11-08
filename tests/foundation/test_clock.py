"""Tests for `bull.Modules.foundation.clock`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from bull.Modules.foundation.clock import LiveClock


def test_now_is_timezone_aware() -> None:
    assert LiveClock().now().tzinfo is not None


def test_now_is_utc() -> None:
    assert LiveClock().now().utcoffset() == timedelta(0)


def test_now_is_close_to_system_time() -> None:
    before = datetime.now(UTC)
    now = LiveClock().now()
    after = datetime.now(UTC)
    assert before - timedelta(seconds=1) <= now <= after + timedelta(seconds=1)
