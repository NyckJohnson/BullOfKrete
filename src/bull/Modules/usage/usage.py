"""Usage samples in `.bull/usage.json` and the pause decision."""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime

from bull.Modules.foundation.Contracts import AppLayout, Clock, Files
from bull.Modules.settings.Contracts import Settings
from bull.Modules.usage.Contracts import Usage, UsageCheck, UsageSample, UsageVerdict

_FORMAT = 1
_NO_DATA = "no usage data yet"


class LiveUsage(Usage):
    """Keeps the latest usage sample in `app.usage_file` and decides OK / PAUSE / UNKNOWN.

    Thresholds (`usage.pause_5h`, `usage.pause_weekly`) are read from `settings` at every
    `check`, so a changed setting takes effect without rebuilding the object.
    """

    def __init__(
        self, app: AppLayout, files: Files, settings: Settings, clock: Clock
    ) -> None:
        self._path = app.usage_file
        self._files = files
        self._settings = settings
        self._clock = clock

    def record(self, sample: UsageSample) -> None:
        """Overwrite `usage.json` (format 1) with `sample`, atomically."""
        data = {
            "format": _FORMAT,
            "time": _time_text(sample.time),
            "five_hour": sample.five_hour,
            "weekly": sample.weekly,
            "five_hour_resets": _optional_time_text(sample.five_hour_resets),
            "weekly_resets": _optional_time_text(sample.weekly_resets),
        }
        self._files.write_atomic(
            self._path, json.dumps(data, indent=2, sort_keys=True) + "\n"
        )

    def latest(self) -> UsageSample | None:
        """The recorded sample, or None when the file is missing or unreadable."""
        try:
            text = self._files.read_text(self._path)
        except (OSError, UnicodeDecodeError):
            return (
                None  # unreadable file (permissions, a directory, bad bytes) per spec
            )
        if text is None:
            return None
        try:
            data: object = json.loads(text)
        except json.JSONDecodeError:
            return None  # unreadable file means "no sample" per spec
        return _parse(data)

    def check(self) -> UsageCheck:
        return _decide(
            self.latest(),
            self._clock.now(),
            _threshold(self._settings, "usage.pause_5h"),
            _threshold(self._settings, "usage.pause_weekly"),
        )


def _threshold(settings: Settings, key: str) -> int:
    value = settings.get(key)
    # The settings schema declares these INT; anything else is a broken settings layer.
    if isinstance(value, bool) or not isinstance(value, int):
        # coverage-exempt-begin: schema makes usage.pause_* INT; mypy narrowing guard
        raise TypeError(f"setting {key} must be an int, got {value!r}")
        # coverage-exempt-end
    return value


def _decide(
    sample: UsageSample | None, now: datetime, pause_5h: int, pause_weekly: int
) -> UsageCheck:
    """The spec's pause rule.

    No sample or no percentages → UNKNOWN. A window whose reset time has passed counts
    as 0%. The 5-hour window is checked before the weekly one; a missing percentage
    never pauses.
    """
    if sample is None or (sample.five_hour is None and sample.weekly is None):
        return UsageCheck(UsageVerdict.UNKNOWN, _NO_DATA, None)
    five = _effective(sample.five_hour, sample.five_hour_resets, now)
    weekly = _effective(sample.weekly, sample.weekly_resets, now)
    if five is not None and five >= pause_5h:
        return UsageCheck(
            UsageVerdict.PAUSE,
            f"5-hour usage {_pct(five)} ≥ {_pct(pause_5h)}",
            sample.five_hour_resets,
        )
    if weekly is not None and weekly >= pause_weekly:
        return UsageCheck(
            UsageVerdict.PAUSE,
            f"weekly usage {_pct(weekly)} ≥ {_pct(pause_weekly)}",
            sample.weekly_resets,
        )
    return UsageCheck(
        UsageVerdict.OK,
        f"5-hour usage {_pct(five)}, weekly {_pct(weekly)}",
        None,
    )


def _effective(
    percent: float | None, resets: datetime | None, now: datetime
) -> float | None:
    if percent is not None and resets is not None and resets <= now:
        return 0.0
    return percent


def _pct(value: float | None) -> str:
    """`92.0` → "92%", `31.5` → "31.5%", None → "unknown"."""
    return "unknown" if value is None else f"{value:g}%"


def _time_text(t: datetime) -> str:
    return t.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _optional_time_text(t: datetime | None) -> str | None:
    return None if t is None else _time_text(t)


class _Malformed(Exception):
    pass


def _parse(data: object) -> UsageSample | None:
    """A sample from decoded `usage.json`, or None if it is not a valid format-1 sample."""
    if not isinstance(data, dict) or data.get("format") != _FORMAT:
        return None
    try:
        return UsageSample(
            time=_req_time(data.get("time")),
            five_hour=_opt_percent(data.get("five_hour")),
            weekly=_opt_percent(data.get("weekly")),
            five_hour_resets=_opt_time(data.get("five_hour_resets")),
            weekly_resets=_opt_time(data.get("weekly_resets")),
        )
    except _Malformed:
        return None  # unreadable file means "no sample" per spec


def _req_time(value: object) -> datetime:
    if not isinstance(value, str):
        raise _Malformed
    try:
        t = datetime.fromisoformat(value)
    except ValueError as e:
        raise _Malformed from e
    if t.tzinfo is None:
        raise _Malformed
    return t.astimezone(UTC)


def _opt_time(value: object) -> datetime | None:
    return None if value is None else _req_time(value)


def _opt_percent(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise _Malformed
    percent = float(value)
    if not math.isfinite(percent):  # json.loads accepts NaN / Infinity
        raise _Malformed
    return percent
