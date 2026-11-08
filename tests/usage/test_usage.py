"""Tests for `bull.Modules.usage.usage`.

Constructor chosen here: `LiveUsage(app: AppLayout, files: Files, settings: Settings,
clock: Clock)`. The sample lives at `app.usage_file`; the foundation `MockFiles` is
enough to observe the writes (`write_atomic` or `write_json`, both store into `texts`).
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from bull.Modules.foundation.mocks import (
    SAMPLE_TIME,
    MockClock,
    MockFiles,
    sample_layout,
)
from bull.Modules.settings.Contracts import Layer, SettingValue
from bull.Modules.settings.mocks import MockSettings
from bull.Modules.usage.Contracts import Usage, UsageCheck, UsageSample, UsageVerdict
from bull.Modules.usage.usage import LiveUsage

_BODY = (
    '{"format": 1, "time": %s, "five_hour": %s, "weekly": 1, '
    '"five_hour_resets": null, "weekly_resets": null}'
)
APP = sample_layout(Path("/tmp/apps/tally"))
NOW = SAMPLE_TIME
SOON = NOW + timedelta(hours=2)
LATER = NOW + timedelta(days=3)
PAST = NOW - timedelta(minutes=1)


def sample(
    five: float | None = 10.0,
    weekly: float | None = 10.0,
    five_resets: datetime | None = SOON,
    weekly_resets: datetime | None = LATER,
) -> UsageSample:
    return UsageSample(NOW, five, weekly, five_resets, weekly_resets)


class Rig:
    def __init__(self) -> None:
        self.files = MockFiles()
        self.settings = MockSettings()
        self.clock = MockClock(NOW)
        self.usage = LiveUsage(APP, self.files, self.settings, self.clock)

    def check(self, s: UsageSample | None) -> UsageCheck:
        if s is not None:
            self.usage.record(s)
        return self.usage.check()


class RaisingFiles(MockFiles):
    """Reads (text or JSON) fail with `error`, like a real disk problem."""

    def __init__(self, error: Exception) -> None:
        super().__init__()
        self.error = error

    def read_text(self, path: Path) -> str | None:
        raise self.error

    def read_json(self, path: Path) -> object | None:
        raise self.error


@pytest.fixture
def rig() -> Rig:
    return Rig()


def test_live_usage_satisfies_the_protocol(rig: Rig) -> None:
    usage: Usage = rig.usage
    assert usage.latest() is None


# --- record / latest -------------------------------------------------------


def test_record_writes_usage_json_format_1(rig: Rig) -> None:
    rig.usage.record(sample(92.0, 31.5, SOON, LATER))
    text = rig.files.texts[APP.usage_file]
    assert json.loads(text) == {
        "format": 1,
        "time": "2026-11-07T12:00:00Z",
        "five_hour": 92.0,
        "weekly": 31.5,
        "five_hour_resets": "2026-11-07T14:00:00Z",
        "weekly_resets": "2026-11-10T12:00:00Z",
    }


def test_record_text_is_indent_2_sorted_with_trailing_newline(rig: Rig) -> None:
    rig.usage.record(sample())
    text = rig.files.texts[APP.usage_file]
    data = json.loads(text)
    assert text == json.dumps(data, indent=2, sort_keys=True) + "\n"


def test_record_writes_nulls_for_missing_values(rig: Rig) -> None:
    rig.usage.record(sample(None, None, None, None))
    data = json.loads(rig.files.texts[APP.usage_file])
    assert data["five_hour"] is None and data["weekly"] is None
    assert data["five_hour_resets"] is None and data["weekly_resets"] is None


def test_record_goes_through_files_not_the_real_disk(rig: Rig) -> None:
    rig.usage.record(sample())
    assert {c[0] for c in rig.files.calls} & {"write_atomic", "write_json"}


def test_record_overwrites_the_previous_sample(rig: Rig) -> None:
    rig.usage.record(sample(1.0))
    rig.usage.record(sample(2.0))
    assert rig.usage.latest() == sample(2.0)


def test_record_converts_non_utc_times_to_utc_z(rig: Rig) -> None:
    from datetime import timezone

    plus2 = timezone(timedelta(hours=2))
    rig.usage.record(
        replace(sample(), time=datetime(2026, 11, 7, 14, 0, 0, tzinfo=plus2))
    )
    assert json.loads(rig.files.texts[APP.usage_file])["time"] == "2026-11-07T12:00:00Z"


def test_latest_round_trips_a_recorded_sample(rig: Rig) -> None:
    s = sample(92.0, 31.5)
    rig.usage.record(s)
    assert rig.usage.latest() == s


def test_latest_round_trips_none_values(rig: Rig) -> None:
    s = sample(None, 5.0, None, LATER)
    rig.usage.record(s)
    assert rig.usage.latest() == s


def test_latest_reads_a_file_written_by_another_process(rig: Rig) -> None:
    rig.files.texts[APP.usage_file] = json.dumps(
        {
            "format": 1,
            "time": "2026-11-07T12:00:00Z",
            "five_hour": 3.0,
            "weekly": None,
            "five_hour_resets": "2026-11-07T14:00:00Z",
            "weekly_resets": None,
        }
    )
    assert rig.usage.latest() == sample(3.0, None, SOON, None)


def test_latest_of_missing_file_is_none(rig: Rig) -> None:
    assert rig.usage.latest() is None


@pytest.mark.parametrize(
    "text",
    [
        "",
        "{not json",
        "[]",
        "42",
        "null",
        "{}",
        '{"format": 1}',
        _BODY % ('"garbage"', "1"),
        _BODY % ('"2026-11-07T12:00:00Z"', '"high"'),
        _BODY % ("5", "1"),
    ],
)
def test_latest_of_unreadable_file_is_none(rig: Rig, text: str) -> None:
    rig.files.texts[APP.usage_file] = text
    assert rig.usage.latest() is None


# --- check: unknown --------------------------------------------------------


def test_check_without_a_sample_is_unknown(rig: Rig) -> None:
    check = rig.usage.check()
    assert check.verdict is UsageVerdict.UNKNOWN
    assert check.reason == "no usage data yet"
    assert check.resets_at is None


def test_check_with_both_percentages_none_is_unknown(rig: Rig) -> None:
    check = rig.check(sample(None, None))
    assert check.verdict is UsageVerdict.UNKNOWN
    assert check.reason == "no usage data yet"


def test_check_with_unreadable_file_is_unknown(rig: Rig) -> None:
    rig.files.texts[APP.usage_file] = "{broken"
    assert rig.usage.check().verdict is UsageVerdict.UNKNOWN


# --- check: pause ----------------------------------------------------------


def test_five_hour_over_threshold_pauses_with_exact_reason(rig: Rig) -> None:
    check = rig.check(sample(92.0, 10.0))
    assert check == UsageCheck(UsageVerdict.PAUSE, "5-hour usage 92% ≥ 85%", SOON)


def test_five_hour_exactly_at_threshold_pauses(rig: Rig) -> None:
    check = rig.check(sample(85.0, 10.0))
    assert check.verdict is UsageVerdict.PAUSE
    assert check.reason == "5-hour usage 85% ≥ 85%"


def test_five_hour_just_below_threshold_is_ok(rig: Rig) -> None:
    assert rig.check(sample(84.9, 10.0)).verdict is UsageVerdict.OK


def test_weekly_over_threshold_pauses_with_its_reset(rig: Rig) -> None:
    check = rig.check(sample(10.0, 97.0))
    assert check == UsageCheck(UsageVerdict.PAUSE, "weekly usage 97% ≥ 95%", LATER)


def test_weekly_exactly_at_threshold_pauses(rig: Rig) -> None:
    check = rig.check(sample(10.0, 95.0))
    assert check.verdict is UsageVerdict.PAUSE
    assert check.reason == "weekly usage 95% ≥ 95%"


def test_weekly_just_below_threshold_is_ok(rig: Rig) -> None:
    assert rig.check(sample(10.0, 94.9)).verdict is UsageVerdict.OK


def test_five_hour_pause_wins_when_both_are_over(rig: Rig) -> None:
    check = rig.check(sample(90.0, 99.0))
    assert check.reason == "5-hour usage 90% ≥ 85%"
    assert check.resets_at == SOON


def test_pause_without_a_reset_time_has_no_resets_at(rig: Rig) -> None:
    check = rig.check(sample(90.0, 10.0, None, LATER))
    assert check.verdict is UsageVerdict.PAUSE
    assert check.resets_at is None


def test_five_hour_threshold_comes_from_settings(rig: Rig) -> None:
    rig.settings.set("usage.pause_5h", "50", Layer.APP)
    check = rig.check(sample(60.0, 10.0))
    assert check == UsageCheck(UsageVerdict.PAUSE, "5-hour usage 60% ≥ 50%", SOON)


def test_five_hour_raised_threshold_lets_more_through(rig: Rig) -> None:
    rig.settings.set("usage.pause_5h", "95", Layer.USER)
    assert rig.check(sample(90.0, 10.0)).verdict is UsageVerdict.OK


def test_weekly_threshold_comes_from_settings(rig: Rig) -> None:
    rig.settings.set("usage.pause_weekly", "60", Layer.APP)
    check = rig.check(sample(10.0, 70.0))
    assert check == UsageCheck(UsageVerdict.PAUSE, "weekly usage 70% ≥ 60%", LATER)


def test_threshold_is_read_at_each_check(rig: Rig) -> None:
    rig.usage.record(sample(60.0, 10.0))
    assert rig.usage.check().verdict is UsageVerdict.OK
    rig.settings.set("usage.pause_5h", "60", Layer.APP)
    assert rig.usage.check().verdict is UsageVerdict.PAUSE


# --- check: resets, None, ok -----------------------------------------------


def test_expired_five_hour_window_counts_as_zero(rig: Rig) -> None:
    assert rig.check(sample(99.0, 10.0, PAST, LATER)).verdict is UsageVerdict.OK


def test_expired_weekly_window_counts_as_zero(rig: Rig) -> None:
    assert rig.check(sample(10.0, 99.0, SOON, PAST)).verdict is UsageVerdict.OK


def test_expired_five_hour_still_lets_weekly_pause(rig: Rig) -> None:
    check = rig.check(sample(99.0, 96.0, PAST, LATER))
    assert check == UsageCheck(UsageVerdict.PAUSE, "weekly usage 96% ≥ 95%", LATER)


def test_window_becomes_expired_as_the_clock_advances(rig: Rig) -> None:
    rig.usage.record(sample(99.0, 10.0, SOON, LATER))
    assert rig.usage.check().verdict is UsageVerdict.PAUSE
    rig.clock.time = SOON + timedelta(seconds=1)
    assert rig.usage.check().verdict is UsageVerdict.OK


def test_both_windows_expired_is_ok(rig: Rig) -> None:
    assert rig.check(sample(99.0, 99.0, PAST, PAST)).verdict is UsageVerdict.OK


def test_missing_five_hour_percentage_uses_weekly(rig: Rig) -> None:
    check = rig.check(sample(None, 96.0))
    assert check == UsageCheck(UsageVerdict.PAUSE, "weekly usage 96% ≥ 95%", LATER)


def test_missing_weekly_percentage_uses_five_hour(rig: Rig) -> None:
    check = rig.check(sample(90.0, None))
    assert check == UsageCheck(UsageVerdict.PAUSE, "5-hour usage 90% ≥ 85%", SOON)


def test_one_missing_percentage_and_the_other_low_is_ok(rig: Rig) -> None:
    assert rig.check(sample(None, 10.0)).verdict is UsageVerdict.OK
    assert rig.check(sample(10.0, None)).verdict is UsageVerdict.OK


def test_ok_reason_mentions_both_percentages(rig: Rig) -> None:
    check = rig.check(sample(42.0, 31.5))
    assert check.verdict is UsageVerdict.OK
    assert "42" in check.reason and "31.5" in check.reason


def test_zero_percent_is_ok(rig: Rig) -> None:
    assert rig.check(sample(0.0, 0.0)).verdict is UsageVerdict.OK


def test_hundred_percent_pauses(rig: Rig) -> None:
    assert rig.check(sample(100.0, 100.0)).verdict is UsageVerdict.PAUSE


# --- unreadable at the OS level / non-finite numbers -----------------------

_READ_ERRORS = [
    PermissionError("denied"),
    IsADirectoryError("is a directory"),
    OSError("io"),
    UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte"),
]


@pytest.mark.parametrize("error", _READ_ERRORS, ids=lambda e: type(e).__name__)
def test_latest_is_none_when_reading_the_file_fails(error: Exception) -> None:
    usage = LiveUsage(APP, RaisingFiles(error), MockSettings(), MockClock(NOW))
    assert usage.latest() is None


@pytest.mark.parametrize("error", _READ_ERRORS, ids=lambda e: type(e).__name__)
def test_check_is_unknown_when_reading_the_file_fails(error: Exception) -> None:
    usage = LiveUsage(APP, RaisingFiles(error), MockSettings(), MockClock(NOW))
    check = usage.check()
    assert check.verdict is UsageVerdict.UNKNOWN
    assert check.reason == "no usage data yet"


@pytest.mark.parametrize("field", ["five_hour", "weekly"])
@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity"])
def test_latest_is_none_for_non_finite_percentages(
    rig: Rig, field: str, bad: str
) -> None:
    body = {"five_hour": "1", "weekly": "1"}
    body[field] = bad
    rig.files.texts[APP.usage_file] = (
        '{"format": 1, "time": "2026-11-07T12:00:00Z", '
        f'"five_hour": {body["five_hour"]}, "weekly": {body["weekly"]}, '
        '"five_hour_resets": null, "weekly_resets": null}'
    )
    assert rig.usage.latest() is None


@pytest.mark.parametrize("field", ["time", "five_hour_resets"])
def test_naive_timestamp_makes_the_file_unreadable(rig: Rig, field: str) -> None:
    data: dict[str, object] = {
        "format": 1,
        "time": "2026-11-07T12:00:00Z",
        "five_hour": 10.0,
        "weekly": 10.0,
        "five_hour_resets": "2026-11-07T14:00:00Z",
        "weekly_resets": None,
    }
    data[field] = "2026-01-01T00:00:00"
    rig.files.texts[APP.usage_file] = json.dumps(data)
    assert rig.usage.latest() is None
    check = rig.usage.check()
    assert check.verdict is UsageVerdict.UNKNOWN
    assert check.reason == "no usage data yet"


class BadThresholdSettings(MockSettings):
    """Returns `value` for `bad_key`, as a broken settings layer would."""

    def __init__(self, bad_key: str, value: object) -> None:
        super().__init__()
        self.bad_key = bad_key
        self.bad_value: SettingValue = value  # type: ignore[assignment]

    def get(self, key: str, part: str | None = None) -> SettingValue:
        if key == self.bad_key:
            return self.bad_value
        return super().get(key, part)


@pytest.mark.parametrize("key", ["usage.pause_5h", "usage.pause_weekly"])
@pytest.mark.parametrize("value", ["85", True, 85.5])
def test_check_raises_type_error_naming_a_non_int_threshold(
    key: str, value: object
) -> None:
    settings = BadThresholdSettings(key, value)
    usage = LiveUsage(APP, MockFiles(), settings, MockClock(NOW))
    usage.record(sample(10.0, 10.0))
    with pytest.raises(TypeError, match=key.replace(".", r"\.")):
        usage.check()
