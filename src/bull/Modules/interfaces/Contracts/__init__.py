"""interfaces contract: interfaces between parts and their checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from bull.Modules.foundation.Contracts import AppLayout
from bull.Modules.memo.Contracts import InterfaceEntry, Memo
from bull.Modules.stacks.Contracts import CheckItem, Role


@dataclass(frozen=True)
class InterfaceResult:
    interface: str
    part: str
    module: str
    role: Role
    items: tuple[CheckItem, ...]

    @property
    def ok(self) -> bool:
        raise NotImplementedError(f"{type(self).__name__}.ok")


class Interfaces(Protocol):
    def for_module(
        self, memo: Memo, module: str
    ) -> list[tuple[InterfaceEntry, Role]]: ...
    def problems(self, app: AppLayout, memo: Memo) -> list[str]: ...
    def check_module(
        self, app: AppLayout, memo: Memo, module: str
    ) -> list[InterfaceResult]: ...
    def parts_to_run(self, memo: Memo, part: str) -> list[str]: ...
