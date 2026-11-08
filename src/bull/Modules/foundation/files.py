"""Atomic file I/O."""

from __future__ import annotations

from pathlib import Path

from bull.Modules.foundation.Contracts import Files


class LiveFiles(Files):
    def read_text(self, path: Path) -> str | None:
        raise NotImplementedError(f"{type(self).__name__}.read_text")

    def write_atomic(self, path: Path, text: str) -> None:
        raise NotImplementedError(f"{type(self).__name__}.write_atomic")

    def read_json(self, path: Path) -> object | None:
        raise NotImplementedError(f"{type(self).__name__}.read_json")

    def write_json(self, path: Path, data: object) -> None:
        raise NotImplementedError(f"{type(self).__name__}.write_json")

    def append_line(self, path: Path, line: str) -> None:
        raise NotImplementedError(f"{type(self).__name__}.append_line")
