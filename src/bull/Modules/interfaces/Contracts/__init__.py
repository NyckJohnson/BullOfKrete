"""interfaces contract: interfaces between parts and their checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from bull.Modules.foundation.Contracts import AppLayout
from bull.Modules.memo.Contracts import InterfaceEntry, Memo
from bull.Modules.stacks.Contracts import CheckItem, Role


@dataclass(frozen=True)
class InterfaceResult:
    """One side's check of one interface: the interface, the module's part, module and role,
    and the items the side's stack `interface_check` returned."""

    interface: str
    part: str
    module: str
    role: Role
    items: tuple[CheckItem, ...]

    @property
    def ok(self) -> bool:
        """True when every item is ok; a result with no items is ok."""
        return all(item.ok for item in self.items)


class Interfaces(Protocol):
    """Interfaces between parts: who provides or consumes them, their problems, their per-side
    checks, and which parts must run for a part's journeys."""

    def for_module(
        self, memo: Memo, module: str
    ) -> list[tuple[InterfaceEntry, Role]]: ...
    def problems(self, app: AppLayout, memo: Memo) -> list[str]: ...
    def check_module(
        self, app: AppLayout, memo: Memo, module: str
    ) -> list[InterfaceResult]: ...
    def parts_to_run(self, memo: Memo, part: str) -> list[str]: ...
