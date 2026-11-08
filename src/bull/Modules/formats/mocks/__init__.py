"""Mocks of the formats contract, for tests and previews."""

from __future__ import annotations

from pathlib import Path

from bull.Modules.formats.Contracts import FileFormat, Formats, Migration
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
    """Every file at the current format; `migrated` is what `migrate` returns."""

    def __init__(self, current: int = 1) -> None:
        self.current_format = current
        self.migrated: list[Path] = []
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def current(self) -> int:
        self.calls.append(("current", ()))
        return self.current_format

    def inspect(self, app: AppLayout) -> list[FileFormat]:
        self.calls.append(("inspect", (app,)))
        return [
            FileFormat(app.status_file, self.current_format, self.current_format),
            FileFormat(app.backlog_file, self.current_format, self.current_format),
            FileFormat(app.config_file, self.current_format, self.current_format),
        ]

    def check(self, app: AppLayout) -> None:
        self.calls.append(("check", (app,)))

    def migrate(self, app: AppLayout) -> list[Path]:
        self.calls.append(("migrate", (app,)))
        return list(self.migrated)
