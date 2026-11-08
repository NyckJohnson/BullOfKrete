"""Format checks and migrations of the app's files."""

from __future__ import annotations

import json
import tomllib
from collections.abc import Sequence
from pathlib import Path

from bull.Modules.formats.Contracts import (
    FileFormat,
    Formats,
    FormatTooNew,
    FormatTooOld,
    Migration,
)
from bull.Modules.foundation.Contracts import AppLayout, BullError, FileFormatError
from bull.Modules.gitrepo.Contracts import Git

_UPGRADE_FIX = "uv tool upgrade bullofkrete"


class LiveFormats(Formats):
    """Reads the `format` of an app's files and upgrades them with registered migrations.

    `migrations` are the steps this bull knows (each from `source` to `source + 1`);
    `current` is the format this bull reads and writes (1 in v2.0).
    """

    def __init__(
        self, git: Git, migrations: Sequence[Migration] = (), current: int = 1
    ) -> None:
        self._git = git
        self._migrations = tuple(migrations)
        self._current = current

    def current(self) -> int:
        return self._current

    def inspect(self, app: AppLayout) -> list[FileFormat]:
        """The format of `status.json`, `backlog.json`, `config.toml` and each part file.

        Missing files are skipped; a file without an integer `format` reports None.
        Raises `FileFormatError` for a file that isn't valid JSON/TOML.
        """
        paths = [app.status_file, app.backlog_file, app.config_file]
        if app.parts_dir.is_dir():
            paths.extend(sorted(app.parts_dir.glob("*.toml")))
        return [
            FileFormat(path, _read_format(path), self._current)
            for path in paths
            if path.is_file()
        ]

    def check(self, app: AppLayout) -> None:
        """Raise `FormatTooNew` if any file is newer, else `FormatTooOld` if any is older."""
        self._oldest_outdated(app)

    def migrate(self, app: AppLayout) -> list[Path]:
        """Apply the migrations from the oldest found format up to `current`, then commit.

        Returns the changed paths in application order (each once); `[]` when every
        file is already current. Raises `FormatTooNew` for newer files and `BullError`
        when a step is missing (before anything is applied).
        """
        oldest = self._oldest_outdated(app, raise_too_old=False)
        if oldest is None:
            return []
        by_source: dict[int, Migration] = {}
        for migration in self._migrations:
            by_source.setdefault(migration.source, migration)
        steps: list[Migration] = []
        for source in range(oldest, self._current):
            step = by_source.get(source)
            if step is None:
                raise BullError(
                    f"no migration from format {source} to format {source + 1}",
                    _UPGRADE_FIX,
                )
            steps.append(step)
        changed: list[Path] = []
        for step in steps:
            for path in step.apply(app):
                if path not in changed:
                    changed.append(path)
        self._git.commit_all(
            app.root, f"chore: migrate bull files to format {self._current}"
        )
        return changed

    def _oldest_outdated(
        self, app: AppLayout, raise_too_old: bool = True
    ) -> int | None:
        """The oldest format below `current` (a missing `format` counts as 0), or None.

        Raises `FormatTooNew` naming the newest format above `current`, and, when
        `raise_too_old`, `FormatTooOld` naming the oldest one below it.
        """
        found = [0 if item.found is None else item.found for item in self.inspect(app)]
        newer = [f for f in found if f > self._current]
        if newer:
            raise FormatTooNew(
                f"this app's files are format {max(newer)}; "
                f"this bull reads format {self._current}: upgrade bull",
                _UPGRADE_FIX,
            )
        older = [f for f in found if f < self._current]
        if not older:
            return None
        oldest = min(older)
        if raise_too_old:
            raise FormatTooOld(
                f"this app's files are format {oldest}; run `bull migrate`",
                "bull migrate",
            )
        return oldest


def _read_format(path: Path) -> int | None:
    """The integer `format` key of a JSON or TOML file, or None if it has none."""
    text = path.read_text(encoding="utf-8")
    data: object
    try:
        data = json.loads(text) if path.suffix == ".json" else tomllib.loads(text)
    except (json.JSONDecodeError, tomllib.TOMLDecodeError) as error:
        raise FileFormatError(f"{path} is not valid: {error}") from error
    value = data.get("format") if isinstance(data, dict) else None
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None
