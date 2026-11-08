"""Modules from the memo: init, add and reopen.

Pure functions over `Status` (current status first, keyword-only context last), called by
`LiveStatusStore` through this module; they raise `StatusError` on refusal.
Implemented in unit 3.
"""

from __future__ import annotations

from collections.abc import Sequence

from bull.Modules.memo.Contracts import Memo, MemoProblem, ModuleEntry
from bull.Modules.status.Contracts import ModuleState, Status


def init_modules(
    status: Status,
    memo: Memo,
    replace: bool = False,
    *,
    known_parts: Sequence[str],
    problems: Sequence[MemoProblem],
) -> Status:
    raise NotImplementedError("modules.init_modules")


def set_module(status: Status, name: str, state: ModuleState) -> Status:
    raise NotImplementedError("modules.set_module")


def reopen(status: Status, module: str, files: Sequence[str]) -> Status:
    raise NotImplementedError("modules.reopen")


def add_modules(
    status: Status, entries: Sequence[ModuleEntry], *, known_parts: Sequence[str]
) -> Status:
    raise NotImplementedError("modules.add_modules")
