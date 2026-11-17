"""appinit contract: `bull init`, `bull open` and `bull doctor`."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from bull.Modules.stacks.Contracts import CheckItem


@dataclass(frozen=True)
class InitResult:
    """Outcome of `bull init`: the app root and what the command did there."""

    root: Path
    created: bool
    relinked: bool
    adopting: bool


@dataclass(frozen=True)
class DoctorReport:
    """Result of `bull doctor`: core tool checks plus informational per-stack checks."""

    items: tuple[CheckItem, ...]
    stacks: tuple[tuple[str, tuple[CheckItem, ...]], ...]

    @property
    def ok(self) -> bool:
        """True exactly when every core item in `items` passes.

        Per-stack items in `stacks` are informational and never affect this.
        """
        return all(item.ok for item in self.items)


class AppInit(Protocol):
    """Sets up an app folder (`bull init`) and builds the `bull open` command line."""

    def init(self, path: Path, adopt: bool = False) -> InitResult: ...
    def open_argv(self, path: Path, extra: Sequence[str]) -> list[str]: ...


class Doctor(Protocol):
    """Checks the machine's tools (`bull doctor`)."""

    def run(self) -> DoctorReport: ...
