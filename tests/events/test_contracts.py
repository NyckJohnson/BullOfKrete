"""Tests for the events contract types."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

import pytest

from bull.Modules.events.Contracts import Event, EventKind


def test_event_kind_values_match_the_data_model() -> None:
    assert {k.name: k.value for k in EventKind} == {
        "STATUS": "status",
        "GATE_STEP": "gate_step",
        "AGENT_START": "agent_start",
        "AGENT_END": "agent_end",
        "HOOK_BLOCK": "hook_block",
        "PAUSE": "pause",
        "RESUME": "resume",
        "DECISION": "decision",
    }


@pytest.mark.parametrize("kind", list(EventKind))
def test_event_kind_round_trips_through_its_value(kind: EventKind) -> None:
    assert EventKind(kind.value) is kind


def test_event_holds_time_kind_and_data() -> None:
    when = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    event = Event(time=when, kind=EventKind.PAUSE, data={"reason": "usage"})
    assert (event.time, event.kind, event.data) == (
        when,
        EventKind.PAUSE,
        {"reason": "usage"},
    )


def test_event_is_frozen() -> None:
    event = Event(time=datetime(2026, 1, 1, tzinfo=UTC), kind=EventKind.STATUS, data={})
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.kind = EventKind.PAUSE  # type: ignore[misc]
