"""Tests for the events mock other modules' tests rely on."""

from __future__ import annotations

from bull.Modules.events.Contracts import EventKind, EventLog
from bull.Modules.events.mocks import MockEventLog


def test_mock_event_log_satisfies_the_protocol() -> None:
    log: EventLog = MockEventLog()
    assert isinstance(log.read(), list)


def test_mock_records_appended_events_in_order_with_their_data() -> None:
    log = MockEventLog()
    before = len(log.read())
    log.append(EventKind.PAUSE, reason="usage", minutes=5)
    log.append(EventKind.RESUME)
    new = log.read()[before:]
    assert [e.kind for e in new] == [EventKind.PAUSE, EventKind.RESUME]
    assert dict(new[0].data) == {"reason": "usage", "minutes": 5}
    assert dict(new[1].data) == {}


def test_mock_read_returns_a_copy() -> None:
    log = MockEventLog()
    snapshot = log.read()
    snapshot.clear()
    log.append(EventKind.STATUS, what="x")
    assert log.read()[-1].data == {"what": "x"}


def test_mock_logs_append_and_read_calls() -> None:
    log = MockEventLog()
    log.append(EventKind.DECISION, note="ok")
    log.read()
    assert [name for name, _ in log.calls] == ["append", "read"]
