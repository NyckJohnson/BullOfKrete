"""Tests for `LiveProvider.parse_statusline` (claude_code)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from bull.Modules.claude_code.plugin import LiveProvider
from bull.Modules.foundation.mocks import MockClock
from bull.Modules.plugin_text.mocks import MockPluginText

NOW = datetime(2026, 11, 17, 9, 30, 0, tzinfo=UTC)


def _provider() -> LiveProvider:
    return LiveProvider(MockPluginText(), clock=MockClock(NOW))


def _raw(**fields: object) -> str:
    return json.dumps(fields)


def test_cwd_is_read_from_cwd_field() -> None:
    result = _provider().parse_statusline(_raw(cwd="/work/app"))
    assert result.cwd == Path("/work/app")


def test_cwd_falls_back_to_workspace_current_dir() -> None:
    result = _provider().parse_statusline(
        _raw(workspace={"current_dir": "/work/other"})
    )
    assert result.cwd == Path("/work/other")


def test_cwd_field_wins_over_workspace_current_dir() -> None:
    raw = _raw(cwd="/work/a", workspace={"current_dir": "/work/b"})
    assert _provider().parse_statusline(raw).cwd == Path("/work/a")


def test_used_percentages_map_to_five_hour_and_weekly() -> None:
    raw = _raw(
        cwd="/w",
        rate_limits={
            "five_hour": {"used_percentage": 42.5},
            "seven_day": {"used_percentage": 17},
        },
    )
    usage = _provider().parse_statusline(raw).usage
    assert usage is not None
    assert usage.five_hour == 42.5
    assert usage.weekly == 17


def test_resets_at_epoch_seconds_become_datetimes() -> None:
    five = 1_800_000_000
    week = 1_800_100_000
    raw = _raw(
        cwd="/w",
        rate_limits={
            "five_hour": {"used_percentage": 1, "resets_at": five},
            "seven_day": {"used_percentage": 2, "resets_at": week},
        },
    )
    usage = _provider().parse_statusline(raw).usage
    assert usage is not None
    assert usage.five_hour_resets == datetime.fromtimestamp(five, tz=UTC)
    assert usage.weekly_resets == datetime.fromtimestamp(week, tz=UTC)


def test_resets_at_iso_8601_becomes_datetimes() -> None:
    raw = _raw(
        cwd="/w",
        rate_limits={
            "five_hour": {
                "used_percentage": 1,
                "resets_at": "2026-11-17T14:00:00+00:00",
            },
            "seven_day": {"used_percentage": 2, "resets_at": "2026-11-20T08:00:00Z"},
        },
    )
    usage = _provider().parse_statusline(raw).usage
    assert usage is not None
    assert usage.five_hour_resets == datetime(2026, 11, 17, 14, 0, 0, tzinfo=UTC)
    assert usage.weekly_resets == datetime(2026, 11, 20, 8, 0, 0, tzinfo=UTC)


@pytest.mark.parametrize("bad", ["not a time", "", None, [1], {"a": 1}])
def test_unreadable_resets_at_gives_none_for_that_reset(bad: object) -> None:
    raw = _raw(
        cwd="/w",
        rate_limits={
            "five_hour": {"used_percentage": 10, "resets_at": bad},
            "seven_day": {"used_percentage": 20, "resets_at": 1_800_000_000},
        },
    )
    usage = _provider().parse_statusline(raw).usage
    assert usage is not None
    assert usage.five_hour == 10
    assert usage.five_hour_resets is None
    assert usage.weekly_resets == datetime.fromtimestamp(1_800_000_000, tz=UTC)


def test_only_five_hour_window_leaves_weekly_none() -> None:
    raw = _raw(cwd="/w", rate_limits={"five_hour": {"used_percentage": 33}})
    usage = _provider().parse_statusline(raw).usage
    assert usage is not None
    assert usage.five_hour == 33
    assert usage.weekly is None
    assert usage.weekly_resets is None


def test_only_seven_day_window_leaves_five_hour_none() -> None:
    raw = _raw(cwd="/w", rate_limits={"seven_day": {"used_percentage": 64}})
    usage = _provider().parse_statusline(raw).usage
    assert usage is not None
    assert usage.weekly == 64
    assert usage.five_hour is None
    assert usage.five_hour_resets is None


def test_no_rate_limits_gives_no_usage() -> None:
    result = _provider().parse_statusline(_raw(cwd="/work/app"))
    assert result.usage is None
    assert result.cwd == Path("/work/app")


@pytest.mark.parametrize(
    "limits",
    [
        {},
        {"five_hour": {}, "seven_day": {}},
        {
            "five_hour": {"resets_at": 1_800_000_000},
            "seven_day": {"resets_at": 1_800_000_000},
        },
    ],
)
def test_no_used_percentage_in_either_window_gives_no_usage(limits: object) -> None:
    result = _provider().parse_statusline(_raw(cwd="/w", rate_limits=limits))
    assert result.usage is None


def test_sample_time_is_the_clocks_now() -> None:
    raw = _raw(cwd="/w", rate_limits={"five_hour": {"used_percentage": 5}})
    usage = _provider().parse_statusline(raw).usage
    assert usage is not None
    assert usage.time == NOW


@pytest.mark.parametrize("raw", ["", "{not json", "null", "[1, 2]"])
def test_malformed_json_gives_dot_cwd_and_no_usage(raw: str) -> None:
    result = _provider().parse_statusline(raw)
    assert result.cwd == Path(".")
    assert result.usage is None


@pytest.mark.parametrize("bad", [True, False, 1e20, -1e20, 10**30])
def test_boolean_or_out_of_range_resets_at_gives_none_but_sample_is_made(
    bad: object,
) -> None:
    raw = _raw(
        cwd="/w",
        rate_limits={
            "five_hour": {"used_percentage": 10, "resets_at": bad},
            "seven_day": {"used_percentage": 20, "resets_at": bad},
        },
    )
    usage = _provider().parse_statusline(raw).usage
    assert usage is not None
    assert usage.five_hour == 10
    assert usage.weekly == 20
    assert usage.five_hour_resets is None
    assert usage.weekly_resets is None


# --- context window use (feature: context-use-in-the-status-line) ---


@pytest.mark.parametrize("value", [37, 37.5, 0, 100])
def test_context_used_percentage_maps_to_sample_context(value: float) -> None:
    raw = _raw(cwd="/w", context_window={"used_percentage": value})
    usage = _provider().parse_statusline(raw).usage
    assert usage is not None
    assert usage.context == value


def test_context_and_rate_limits_are_both_present() -> None:
    raw = _raw(
        cwd="/w",
        context_window={"used_percentage": 55.5},
        rate_limits={
            "five_hour": {"used_percentage": 10},
            "seven_day": {"used_percentage": 20},
        },
    )
    usage = _provider().parse_statusline(raw).usage
    assert usage is not None
    assert usage.context == 55.5
    assert usage.five_hour == 10
    assert usage.weekly == 20


def test_context_only_makes_a_sample_without_rate_limits() -> None:
    raw = _raw(cwd="/w", context_window={"used_percentage": 12})
    usage = _provider().parse_statusline(raw).usage
    assert usage is not None
    assert usage.context == 12
    assert usage.five_hour is None
    assert usage.weekly is None
    assert usage.time == NOW


def test_rate_limits_only_leaves_context_none() -> None:
    raw = _raw(cwd="/w", rate_limits={"five_hour": {"used_percentage": 5}})
    usage = _provider().parse_statusline(raw).usage
    assert usage is not None
    assert usage.context is None


@pytest.mark.parametrize(
    "window",
    [
        {"used_percentage": None},
        {},
        {"used_percentage": "50"},
        {"used_percentage": True},
        {"used_percentage": False},
        {"used_percentage": [1]},
        "not an object",
        5,
        None,
        [1, 2],
    ],
)
def test_unreadable_context_gives_none_and_no_sample_without_rate_limits(
    window: object,
) -> None:
    raw = _raw(cwd="/w", context_window=window)
    assert _provider().parse_statusline(raw).usage is None


@pytest.mark.parametrize(
    "window",
    [
        {"used_percentage": None},
        {"used_percentage": "50"},
        {"used_percentage": True},
        "not an object",
    ],
)
def test_unreadable_context_leaves_none_when_rate_limits_exist(
    window: object,
) -> None:
    raw = _raw(
        cwd="/w",
        context_window=window,
        rate_limits={"five_hour": {"used_percentage": 8}},
    )
    usage = _provider().parse_statusline(raw).usage
    assert usage is not None
    assert usage.five_hour == 8
    assert usage.context is None


def test_absent_context_window_gives_none_context() -> None:
    raw = _raw(cwd="/w", rate_limits={"seven_day": {"used_percentage": 9}})
    usage = _provider().parse_statusline(raw).usage
    assert usage is not None
    assert usage.context is None


def test_token_counts_are_not_used_to_work_out_context() -> None:
    window = {
        "used_percentage": None,
        "total_input_tokens": 50_000,
        "context_window_size": 200_000,
        "current_usage": {"input_tokens": 50_000, "output_tokens": 10},
    }
    raw = _raw(cwd="/w", context_window=window)
    assert _provider().parse_statusline(raw).usage is None
    with_limits = _raw(
        cwd="/w",
        context_window=window,
        rate_limits={"five_hour": {"used_percentage": 3}},
    )
    usage = _provider().parse_statusline(with_limits).usage
    assert usage is not None
    assert usage.context is None


# --- non-finite used_percentage is unreadable (feature: context-use-in-the-status-line) ---

NON_FINITE = ["NaN", "Infinity", "-Infinity", "1" + "0" * 400]
FIVE_RESET = 1_800_000_000


@pytest.mark.parametrize("token", NON_FINITE)
def test_non_finite_context_is_none_when_five_hour_is_readable(token: str) -> None:
    raw = (
        '{"cwd": "/w", "context_window": {"used_percentage": ' + token + "},"
        ' "rate_limits": {"five_hour": {"used_percentage": 30}}}'
    )
    usage = _provider().parse_statusline(raw).usage
    assert usage is not None
    assert usage.context is None
    assert usage.five_hour == 30


@pytest.mark.parametrize("token", NON_FINITE)
def test_non_finite_context_alone_gives_no_usage(token: str) -> None:
    raw = '{"cwd": "/w", "context_window": {"used_percentage": ' + token + "}}"
    assert _provider().parse_statusline(raw).usage is None


@pytest.mark.parametrize("token", NON_FINITE)
def test_non_finite_five_hour_percentage_is_none_but_reset_is_read(token: str) -> None:
    raw = (
        '{"cwd": "/w", "rate_limits": {"five_hour": {"used_percentage": '
        + token
        + f', "resets_at": {FIVE_RESET}}}'
        ', "seven_day": {"used_percentage": 20}}}'
    )
    usage = _provider().parse_statusline(raw).usage
    assert usage is not None
    assert usage.five_hour is None
    assert usage.five_hour_resets == datetime.fromtimestamp(FIVE_RESET, tz=UTC)
    assert usage.weekly == 20


@pytest.mark.parametrize("token", NON_FINITE)
def test_non_finite_seven_day_percentage_is_none_but_reset_is_read(token: str) -> None:
    raw = (
        '{"cwd": "/w", "rate_limits": {"five_hour": {"used_percentage": 10},'
        ' "seven_day": {"used_percentage": '
        + token
        + f', "resets_at": {FIVE_RESET}}}}}}}'
    )
    usage = _provider().parse_statusline(raw).usage
    assert usage is not None
    assert usage.weekly is None
    assert usage.weekly_resets == datetime.fromtimestamp(FIVE_RESET, tz=UTC)
    assert usage.five_hour == 10
