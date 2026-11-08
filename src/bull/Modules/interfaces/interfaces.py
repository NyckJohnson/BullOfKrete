"""Interfaces between parts: memo entries, sides, checks and parts to run."""

from __future__ import annotations

from bull.Modules.foundation.Contracts import AppLayout
from bull.Modules.interfaces.Contracts import InterfaceResult, Interfaces
from bull.Modules.memo.Contracts import InterfaceEntry, Memo
from bull.Modules.stacks.Contracts import Role


class LiveInterfaces(Interfaces):
    def for_module(self, memo: Memo, module: str) -> list[tuple[InterfaceEntry, Role]]:
        raise NotImplementedError(f"{type(self).__name__}.for_module")

    def problems(self, app: AppLayout, memo: Memo) -> list[str]:
        raise NotImplementedError(f"{type(self).__name__}.problems")

    def check_module(
        self, app: AppLayout, memo: Memo, module: str
    ) -> list[InterfaceResult]:
        raise NotImplementedError(f"{type(self).__name__}.check_module")

    def parts_to_run(self, memo: Memo, part: str) -> list[str]:
        raise NotImplementedError(f"{type(self).__name__}.parts_to_run")
