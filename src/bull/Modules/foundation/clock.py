"""The clock: timezone-aware UTC."""

from __future__ import annotations

from datetime import UTC, datetime

from bull.Modules.foundation.Contracts import Clock


class LiveClock(Clock):
    def now(self) -> datetime:
        return datetime.now(UTC)
