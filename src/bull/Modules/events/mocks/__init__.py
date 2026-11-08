"""Mocks of the events contract, for tests and previews."""

from __future__ import annotations

from datetime import UTC, datetime

from bull.Modules.events.Contracts import Event, EventKind, EventLog, EventValue

SAMPLE_TIME = datetime(2026, 11, 7, 12, 0, 0, tzinfo=UTC)


class MockEventLog(EventLog):
    """Keeps appended events in memory; `read` returns them in order."""

    def __init__(self) -> None:
        self.events: list[Event] = [
            Event(
                time=SAMPLE_TIME,
                kind=EventKind.STATUS,
                data={"what": "unit", "module": "Counter", "unit": 1, "state": "tests"},
            )
        ]
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def append(self, kind: EventKind, **data: EventValue) -> None:
        self.calls.append(("append", (kind, dict(data))))
        self.events.append(Event(time=SAMPLE_TIME, kind=kind, data=dict(data)))

    def read(self) -> list[Event]:
        self.calls.append(("read", ()))
        return list(self.events)
