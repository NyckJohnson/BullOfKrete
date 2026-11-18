"""The counter module's contract: a count that goes up by one."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Count:
    """A count, as the `Count` interface (`interfaces/count.json`) carries it."""

    value: int


class CounterStore(Protocol):
    """Holds a count and bumps it by one."""

    def value(self) -> int:
        """The current count: the start value until the first increment."""

    def increment(self) -> int:
        """Add one to the count and return the new count."""
