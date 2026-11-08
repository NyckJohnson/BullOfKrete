"""formats contract: file format versions and migrations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from bull.Modules.foundation.Contracts import AppLayout, BullError


class FormatTooOld(BullError): ...


class FormatTooNew(BullError): ...


@dataclass(frozen=True)
class FileFormat:
    path: Path
    found: int | None
    current: int


class Migration(Protocol):
    source: int  # migrates files from `source` to `source + 1`

    def apply(self, app: AppLayout) -> list[Path]: ...


class Formats(Protocol):
    def current(self) -> int: ...
    def inspect(self, app: AppLayout) -> list[FileFormat]: ...
    def check(self, app: AppLayout) -> None: ...
    def migrate(self, app: AppLayout) -> list[Path]: ...
