"""Usage samples in `.bull/usage.json` and the pause decision."""

from __future__ import annotations

from bull.Modules.usage.Contracts import Usage, UsageCheck, UsageSample


class LiveUsage(Usage):
    def record(self, sample: UsageSample) -> None:
        raise NotImplementedError(f"{type(self).__name__}.record")

    def latest(self) -> UsageSample | None:
        raise NotImplementedError(f"{type(self).__name__}.latest")

    def check(self) -> UsageCheck:
        raise NotImplementedError(f"{type(self).__name__}.check")
