"""Format checks and migrations of the app's files."""

from __future__ import annotations

from pathlib import Path

from bull.Modules.formats.Contracts import FileFormat, Formats
from bull.Modules.foundation.Contracts import AppLayout


class LiveFormats(Formats):
    def current(self) -> int:
        raise NotImplementedError(f"{type(self).__name__}.current")

    def inspect(self, app: AppLayout) -> list[FileFormat]:
        raise NotImplementedError(f"{type(self).__name__}.inspect")

    def check(self, app: AppLayout) -> None:
        raise NotImplementedError(f"{type(self).__name__}.check")

    def migrate(self, app: AppLayout) -> list[Path]:
        raise NotImplementedError(f"{type(self).__name__}.migrate")
