"""Tests for the usage contract types."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from bull.Modules.usage.Contracts import UsageCheck, UsageSample, UsageVerdict

T = datetime(2026, 11, 7, 12, 0, 0, tzinfo=UTC)


def test_verdict_values_are_their_names() -> None:
    assert {v.name: v.value for v in UsageVerdict} == {
        "OK": "OK",
        "PAUSE": "PAUSE",
        "UNKNOWN": "UNKNOWN",
    }


def test_sample_holds_its_fields() -> None:
    s = UsageSample(T, 1.0, None, None, T)
    assert (s.time, s.five_hour, s.weekly, s.five_hour_resets, s.weekly_resets) == (
        T,
        1.0,
        None,
        None,
        T,
    )


def test_sample_context_defaults_to_none() -> None:
    assert UsageSample(T, 1.0, 2.0, None, None).context is None


def test_sample_holds_a_context() -> None:
    assert UsageSample(T, 1.0, 2.0, None, None, context=38.0).context == 38.0
    assert UsageSample(T, None, None, None, None, 12.5).context == 12.5


def test_sample_with_a_different_context_is_not_equal() -> None:
    a = UsageSample(T, 1.0, 2.0, None, None, context=1.0)
    assert a != UsageSample(T, 1.0, 2.0, None, None)


def test_sample_is_frozen() -> None:
    s = UsageSample(T, 1.0, 2.0, None, None)
    with pytest.raises(FrozenInstanceError):
        s.five_hour = 3.0  # type: ignore[misc]


def test_check_holds_its_fields_and_is_frozen() -> None:
    c = UsageCheck(UsageVerdict.PAUSE, "why", T)
    assert (c.verdict, c.reason, c.resets_at) == (UsageVerdict.PAUSE, "why", T)
    with pytest.raises(FrozenInstanceError):
        c.reason = "x"  # type: ignore[misc]
