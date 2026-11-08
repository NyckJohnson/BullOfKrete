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
    """OK at 42% / 31.5% by default; set `result` to PAUSE or UNKNOWN to test the guards."""

    def __init__(self) -> None:
        self.sample: UsageSample | None = SAMPLE_USAGE
        self.result = UsageCheck(
            UsageVerdict.OK, "5-hour usage 42%, weekly 31.5%", None
        )
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def record(self, sample: UsageSample) -> None:
        self.calls.append(("record", (sample,)))
        self.sample = sample

    def latest(self) -> UsageSample | None:
        self.calls.append(("latest", ()))
        return self.sample

    def check(self) -> UsageCheck:
        self.calls.append(("check", ()))
        return self.result
