"""usage contract: usage samples and the pause decision."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol


class UsageVerdict(Enum):
    OK = "OK"
    PAUSE = "PAUSE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class UsageSample:
    time: datetime
    five_hour: float | None
    weekly: float | None
    five_hour_resets: datetime | None
    weekly_resets: datetime | None
    context: float | None = None  # the session's context-window use, 0-100


@dataclass(frozen=True)
class UsageCheck:
    verdict: UsageVerdict
    reason: str
    resets_at: datetime | None


class Usage(Protocol):
    def record(self, sample: UsageSample) -> None: ...
    def latest(self) -> UsageSample | None: ...
    def check(self) -> UsageCheck: ...
