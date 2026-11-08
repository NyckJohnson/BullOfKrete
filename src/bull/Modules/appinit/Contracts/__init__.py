"""appinit contract: `bull init`, `bull open` and `bull doctor`."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from bull.Modules.stacks.Contracts import CheckItem


@dataclass(frozen=True)
class InitResult:
    root: Path
    created: bool
    relinked: bool
    adopting: bool


@dataclass(frozen=True)
class DoctorReport:
    items: tuple[CheckItem, ...]
    stacks: tuple[tuple[str, tuple[CheckItem, ...]], ...]

    @property
    def ok(self) -> bool:
        raise NotImplementedError(f"{type(self).__name__}.ok")


class AppInit(Protocol):
    def init(self, path: Path, adopt: bool = False) -> InitResult: ...
    def open_argv(self, path: Path, extra: Sequence[str]) -> list[str]: ...


class Doctor(Protocol):
    def run(self) -> DoctorReport: ...
