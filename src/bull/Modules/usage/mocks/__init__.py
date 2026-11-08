"""Mocks of the usage contract, for tests and previews."""

from __future__ import annotations

from datetime import UTC, datetime

from bull.Modules.usage.Contracts import Usage, UsageCheck, UsageSample, UsageVerdict

SAMPLE_USAGE = UsageSample(
    time=datetime(2026, 11, 7, 12, 0, 0, tzinfo=UTC),
    five_hour=42.0,
    weekly=31.5,
    five_hour_resets=datetime(2026, 11, 7, 15, 0, 0, tzinfo=UTC),
    weekly_resets=datetime(2026, 11, 12, 9, 0, 0, tzinfo=UTC),
)


class MockUsage(Usage):
    """In-memory usage: OK at 42% / 31.5% by default.

    `check` applies the spec rules to `sample` using `pause_5h`, `pause_weekly` and `now`;
    set `result` to return a fixed `UsageCheck` instead.
    """

    def __init__(
        self,
        pause_5h: int = 85,
        pause_weekly: int = 95,
        now: datetime = SAMPLE_USAGE.time,
    ) -> None:
        self.pause_5h = pause_5h
        self.pause_weekly = pause_weekly
        self.now = now
        self.sample: UsageSample | None = SAMPLE_USAGE
        self.result: UsageCheck | None = None
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def record(self, sample: UsageSample) -> None:
        self.calls.append(("record", (sample,)))
        self.sample = sample

    def latest(self) -> UsageSample | None:
        self.calls.append(("latest", ()))
        return self.sample

    def check(self) -> UsageCheck:
        self.calls.append(("check", ()))
        if self.result is not None:
            return self.result
        return self._decide()

    # The same rule as `LiveUsage.check`, duplicated so the mock depends only on Contracts.
    def _decide(self) -> UsageCheck:
        s = self.sample
        if s is None or (s.five_hour is None and s.weekly is None):
            return UsageCheck(UsageVerdict.UNKNOWN, "no usage data yet", None)
        five = self._effective(s.five_hour, s.five_hour_resets)
        weekly = self._effective(s.weekly, s.weekly_resets)
        if five is not None and five >= self.pause_5h:
            return UsageCheck(
                UsageVerdict.PAUSE,
                f"5-hour usage {_pct(five)} ≥ {_pct(self.pause_5h)}",
                s.five_hour_resets,
            )
        if weekly is not None and weekly >= self.pause_weekly:
            return UsageCheck(
                UsageVerdict.PAUSE,
                f"weekly usage {_pct(weekly)} ≥ {_pct(self.pause_weekly)}",
                s.weekly_resets,
            )
        return UsageCheck(
            UsageVerdict.OK, f"5-hour usage {_pct(five)}, weekly {_pct(weekly)}", None
        )

    def _effective(
        self, percent: float | None, resets: datetime | None
    ) -> float | None:
        if percent is not None and resets is not None and resets <= self.now:
            return 0.0
        return percent


def _pct(value: float | None) -> str:
    return "unknown" if value is None else f"{value:g}%"
