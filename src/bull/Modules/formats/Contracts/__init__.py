"""formats contract: file format versions and migrations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from bull.Modules.foundation.Contracts import AppLayout, BullError


class FormatTooOld(BullError):
    """Some app file is older than this bull's format (or has none): run `bull migrate`."""


class FormatTooNew(BullError):
    """Some app file is newer than this bull's format: upgrade bull."""


@dataclass(frozen=True)
class FileFormat:
    """One app file's `format`: `found` (None if it has none) against bull's `current`."""

    path: Path
    found: int | None
    current: int


class Migration(Protocol):
    """One upgrade step; `apply` rewrites the app's files and returns those it changed."""

    source: int  # migrates files from `source` to `source + 1`

    def apply(self, app: AppLayout) -> list[Path]: ...


class Formats(Protocol):
    """Format versions of an app's files: read them, check them, migrate them.

    `current` is the format this bull reads; `inspect` lists each file's format;
    `check` raises `FormatTooNew`/`FormatTooOld`; `migrate` upgrades older files,
    commits, and returns the changed paths (`[]` when already current).
    """

    def current(self) -> int: ...
    def inspect(self, app: AppLayout) -> list[FileFormat]: ...
    def check(self, app: AppLayout) -> None: ...
    def migrate(self, app: AppLayout) -> list[Path]: ...
