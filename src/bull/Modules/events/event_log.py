"""The event log in `.bull/events.jsonl`."""

from __future__ import annotations

from bull.Modules.events.Contracts import Event, EventKind, EventLog, EventValue


class LiveEventLog(EventLog):
    def append(self, kind: EventKind, **data: EventValue) -> None:
        raise NotImplementedError(f"{type(self).__name__}.append")

    def read(self) -> list[Event]:
        raise NotImplementedError(f"{type(self).__name__}.read")
