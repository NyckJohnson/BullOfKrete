"""The clock: timezone-aware UTC."""

from __future__ import annotations

from datetime import datetime

from bull.Modules.foundation.Contracts import Clock


class LiveClock(Clock):
    def now(self) -> datetime:
        raise NotImplementedError(f"{type(self).__name__}.now")
