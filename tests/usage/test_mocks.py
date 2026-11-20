"""Tests for the usage mock other modules' tests rely on.

Knobs the mock must offer (chosen here, for the code-writer):
  - `MockUsage(pause_5h=85, pause_weekly=95, now=SAMPLE_USAGE.time)`; the same
    values are public attributes.
  - `sample: UsageSample | None` (default `SAMPLE_USAGE`): what `latest` returns;
    `record` replaces it.
  - `result: UsageCheck | None` (default None): when set, `check` returns it
    verbatim; when None, `check` applies the spec rules to `sample` with the
    thresholds and `now` (no data -> UNKNOWN "no usage data yet"; expired window
    counts 0%; 5-hour >= threshold -> PAUSE "5-hour usage 92% >= 85%" (with the
    real `≥` sign) resets_at = five_hour_resets; else weekly likewise "weekly usage ...";
    else OK with both percentages in the reason).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from bull.Modules.usage.Contracts import Usage, UsageCheck, UsageSample, UsageVerdict
from bull.Modules.usage.mocks import SAMPLE_USAGE, MockUsage


def test_mock_satisfies_the_protocol() -> None:
    usage: Usage = MockUsage()
    assert usage.latest() == SAMPLE_USAGE


def test_default_check_is_ok_with_both_percentages() -> None:
    check = MockUsage().check()
    assert check.verdict is UsageVerdict.OK
    assert "42" in check.reason and "31.5" in check.reason


def test_record_replaces_latest() -> None:
    mock = MockUsage()
    new = replace(SAMPLE_USAGE, five_hour=1.0)
    mock.record(new)
    assert mock.latest() == new


def test_calls_are_logged() -> None:
    mock = MockUsage()
    mock.record(SAMPLE_USAGE)
    mock.latest()
    mock.check()
    assert [name for name, _ in mock.calls] == ["record", "latest", "check"]
    assert mock.calls[0][1] == (SAMPLE_USAGE,)


def test_no_sample_is_unknown() -> None:
    mock = MockUsage()
    mock.sample = None
    check = mock.check()
    assert check.verdict is UsageVerdict.UNKNOWN
    assert check.reason == "no usage data yet"


def test_both_percentages_none_is_unknown() -> None:
    mock = MockUsage()
    mock.sample = replace(SAMPLE_USAGE, five_hour=None, weekly=None)
    assert mock.check().verdict is UsageVerdict.UNKNOWN


def test_five_hour_at_threshold_pauses_with_its_reset() -> None:
    mock = MockUsage()
    mock.sample = replace(SAMPLE_USAGE, five_hour=85.0)
    check = mock.check()
    assert check.verdict is UsageVerdict.PAUSE
    assert check.reason == "5-hour usage 85% ≥ 85%"
    assert check.resets_at == SAMPLE_USAGE.five_hour_resets


def test_weekly_at_threshold_pauses_with_its_reset() -> None:
    mock = MockUsage()
    mock.sample = replace(SAMPLE_USAGE, weekly=95.0)
    check = mock.check()
    assert check.verdict is UsageVerdict.PAUSE
    assert check.reason == "weekly usage 95% ≥ 95%"
    assert check.resets_at == SAMPLE_USAGE.weekly_resets


def test_five_hour_pause_wins_over_weekly() -> None:
    mock = MockUsage()
    mock.sample = replace(SAMPLE_USAGE, five_hour=90.0, weekly=99.0)
    assert mock.check().reason.startswith("5-hour usage")


def test_just_below_threshold_is_ok() -> None:
    mock = MockUsage()
    mock.sample = replace(SAMPLE_USAGE, five_hour=84.9, weekly=94.9)
    assert mock.check().verdict is UsageVerdict.OK


def test_thresholds_are_configurable() -> None:
    mock = MockUsage(pause_5h=40, pause_weekly=95)
    assert mock.check().verdict is UsageVerdict.PAUSE  # 42% >= 40%
    mock = MockUsage(pause_5h=85, pause_weekly=30)
    check = mock.check()
    assert check.verdict is UsageVerdict.PAUSE  # 31.5% >= 30%
    assert check.reason.startswith("weekly usage")


def test_expired_window_counts_as_zero() -> None:
    mock = MockUsage()
    mock.sample = replace(SAMPLE_USAGE, five_hour=99.0, weekly=10.0)
    mock.now = SAMPLE_USAGE.time + timedelta(hours=4)  # five_hour_resets passed
    assert mock.check().verdict is UsageVerdict.OK


def test_now_is_configurable_at_construction() -> None:
    later = SAMPLE_USAGE.time + timedelta(days=30)
    mock = MockUsage(now=later)
    mock.sample = replace(SAMPLE_USAGE, five_hour=99.0, weekly=99.0)
    assert mock.check().verdict is UsageVerdict.OK


def test_one_none_percentage_is_handled() -> None:
    mock = MockUsage()
    mock.sample = replace(SAMPLE_USAGE, five_hour=None, weekly=96.0)
    assert mock.check().verdict is UsageVerdict.PAUSE
    mock.sample = replace(SAMPLE_USAGE, five_hour=90.0, weekly=None)
    assert mock.check().verdict is UsageVerdict.PAUSE
    mock.sample = replace(SAMPLE_USAGE, five_hour=None, weekly=10.0)
    assert mock.check().verdict is UsageVerdict.OK


def test_result_override_wins() -> None:
    mock = MockUsage()
    forced = UsageCheck(UsageVerdict.PAUSE, "forced", None)
    mock.result = forced
    assert mock.check() is forced


def test_sample_usage_constant_is_a_complete_sample() -> None:
    assert isinstance(SAMPLE_USAGE, UsageSample)
    assert SAMPLE_USAGE.five_hour is not None and SAMPLE_USAGE.weekly is not None
    assert SAMPLE_USAGE.time.tzinfo is not None


def test_record_carries_context_through_to_latest() -> None:
    mock = MockUsage()
    new = replace(SAMPLE_USAGE, context=38.0)
    mock.record(new)
    latest = mock.latest()
    assert latest is not None and latest.context == 38.0


def test_context_is_ignored_by_check() -> None:
    mock = MockUsage()
    mock.sample = replace(SAMPLE_USAGE, five_hour=None, weekly=None, context=99.0)
    check = mock.check()
    assert check.verdict is UsageVerdict.UNKNOWN
    assert check.reason == "no usage data yet"
    mock.sample = replace(SAMPLE_USAGE, context=100.0)
    assert mock.check().verdict is UsageVerdict.OK
