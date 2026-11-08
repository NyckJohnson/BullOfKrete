"""Mocks of the formats contract, for tests and previews."""

from __future__ import annotations

from pathlib import Path

from bull.Modules.formats.Contracts import (
    FileFormat,
    Formats,
    FormatTooNew,
    FormatTooOld,
    Migration,
)
from bull.Modules.foundation.Contracts import AppLayout


class MockMigration(Migration):
    """Pretends to migrate `status.json` from `source` to `source + 1`."""

    def __init__(self, source: int = 0) -> None:
        self.source = source
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def apply(self, app: AppLayout) -> list[Path]:
        self.calls.append(("apply", (app,)))
        return [app.status_file]


class MockFormats(Formats):
    """Every file reports format `found` (initially `current`); `migrated` is what a
    real migration returns. `check` and `migrate` follow the live rules for `found`."""

    def __init__(self, current: int = 1) -> None:
        self.current_format = current
        self.found: int | None = current
        self.migrated: list[Path] = []
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def current(self) -> int:
        self.calls.append(("current", ()))
        return self.current_format

    def inspect(self, app: AppLayout) -> list[FileFormat]:
        self.calls.append(("inspect", (app,)))
        return [
            FileFormat(path, self.found, self.current_format)
            for path in (app.status_file, app.backlog_file, app.config_file)
        ]

    def check(self, app: AppLayout) -> None:
        self.calls.append(("check", (app,)))
        self._raise_if_newer()
        if self.found != self.current_format:
            raise FormatTooOld(
                f"this app's files are format {self.found or 0}; run `bull migrate`",
                "bull migrate",
            )

    def migrate(self, app: AppLayout) -> list[Path]:
        self.calls.append(("migrate", (app,)))
        self._raise_if_newer()
        if self.found == self.current_format:
            return []
        self.found = self.current_format
        return list(self.migrated)

    def _raise_if_newer(self) -> None:
        if self.found is not None and self.found > self.current_format:
            raise FormatTooNew(
                f"this app's files are format {self.found}; "
                f"this bull reads format {self.current_format}: upgrade bull",
                "uv tool upgrade bullofkrete",
            )
