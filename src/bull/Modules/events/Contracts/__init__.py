"""events contract: the append-only event log."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol

EventValue = str | int | float | bool | None


class EventKind(Enum):
    STATUS = "status"
    GATE_STEP = "gate_step"
    AGENT_START = "agent_start"
    AGENT_END = "agent_end"
    HOOK_BLOCK = "hook_block"
    PAUSE = "pause"
    RESUME = "resume"
    DECISION = "decision"


@dataclass(frozen=True)
class Event:
    time: datetime
    kind: EventKind
    data: Mapping[str, EventValue]


class EventLog(Protocol):
    def append(self, kind: EventKind, **data: EventValue) -> None: ...
    def read(self) -> list[Event]: ...
