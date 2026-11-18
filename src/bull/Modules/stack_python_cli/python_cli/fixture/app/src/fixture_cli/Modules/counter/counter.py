"""The counter: a count kept in a file in a folder (the working folder, for the CLI)."""

from __future__ import annotations

from pathlib import Path

from fixture_cli.Modules.counter.Contracts import CounterStore

COUNT_FILE = ".fixture_cli_count"
"""The file, inside the counter's folder, that holds the count."""


class FileCounter(CounterStore):
    """A `CounterStore` that keeps its count in `<folder>/.fixture_cli_count`.

    Raises `ValueError` when that file holds something other than a whole number.
    """

    def __init__(self, folder: Path, start: int = 0) -> None:
        self._path = folder / COUNT_FILE
        self._start = start

    def value(self) -> int:
        if not self._path.is_file():
            return self._start
        return int(self._path.read_text().strip())

    def increment(self) -> int:
        new = self.value() + 1
        self._path.write_text(f"{new}\n")
        return new
