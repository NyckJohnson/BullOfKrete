"""The event log in `.bull/events.jsonl`."""

from __future__ import annotations

import json
import sys
import threading
from datetime import datetime
from pathlib import Path

from bull.Modules.events.Contracts import Event, EventKind, EventLog, EventValue
from bull.Modules.foundation.Contracts import Clock, Files

# The log is best-effort: a failed append warns once per process, then stays quiet.
_warned = False
_warn_lock = threading.Lock()


def _warn_once(path: Path, error: OSError) -> None:
    """Write one warning line to stderr the first time any append fails in this process."""
    global _warned
    with _warn_lock:
        if _warned:
            return
        _warned = True
    print(
        f"bull: warning: cannot write the event log {path} ({error.strerror or error}); "
        "events are not being recorded.",
        file=sys.stderr,
    )


def _is_event_value(value: object) -> bool:
    return value is None or isinstance(value, str | int | float | bool)


def _parse_line(line: str) -> Event | None:
    """Parse one log line; returns None for blank, malformed or invalid lines."""
    if not line.strip():
        return None
    try:
        obj: object = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    raw_time = obj.pop("time", None)
    raw_kind = obj.pop("kind", None)
    if not isinstance(raw_time, str) or not isinstance(raw_kind, str):
        return None
    try:
        time = datetime.fromisoformat(raw_time)
        kind = EventKind(raw_kind)
    except ValueError:
        return None
    data: dict[str, EventValue] = {}
    for key, value in obj.items():
        if not _is_event_value(value):
            return None
        data[key] = value
    return Event(time=time, kind=kind, data=data)


class LiveEventLog(EventLog):
    """Appends events as JSON lines to `path` and reads them back, through `files`."""

    def __init__(self, path: Path, files: Files, clock: Clock) -> None:
        self._path = path
        self._files = files
        self._clock = clock

    def append(self, kind: EventKind, **data: EventValue) -> None:
        """Append one event; on an OS error warns once per process on stderr, never raises."""
        record: dict[str, EventValue] = {
            "time": self._clock.now().isoformat(),
            "kind": kind.value,
        }
        # The clock's time and the kind win over a data key of the same name.
        record.update((k, v) for k, v in data.items() if k not in record)
        try:
            self._files.append_line(self._path, json.dumps(record))
        except OSError as error:
            _warn_once(self._path, error)

    def read(self) -> list[Event]:
        """Events in file order; blank or invalid lines are skipped.

        A missing file, or a path whose parent is not a folder (so the file cannot
        exist), reads as no events.
        """
        try:
            text = self._files.read_text(self._path)
        except NotADirectoryError:
            return []
        if text is None:
            return []
        events: list[Event] = []
        for line in text.splitlines():
            event = _parse_line(line)
            if event is not None:
                events.append(event)
        return events
