"""Atomic file I/O."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from bull.Modules.foundation.Contracts import FileFormatError, Files

# Mode for newly created files (mkstemp creates them 0600).
_NEW_FILE_MODE = 0o644


class LiveFiles(Files):
    """Reads and writes UTF-8 text; every write but `append_line` is atomic."""

    def read_text(self, path: Path) -> str | None:
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None

    def write_atomic(self, path: Path, text: str) -> None:
        """Write `text` to a temp file beside `path`, then `os.replace` it into place.

        If anything fails before the replace, the temp file is removed and the
        target is left as it was (or absent); the error propagates.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            mode = path.stat().st_mode & 0o777
        except FileNotFoundError:
            mode = _NEW_FILE_MODE
        fd, temp_name = tempfile.mkstemp(
            dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
        )
        temp = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temp, mode)
            os.replace(temp, path)
        except BaseException:
            temp.unlink(missing_ok=True)
            raise

    def read_json(self, path: Path) -> object | None:
        """Parse `path` as JSON; missing → None; unreadable → `FileFormatError`."""
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            return None
        try:
            data: object = json.loads(raw.decode("utf-8"))
        except UnicodeDecodeError as error:
            raise FileFormatError(
                f"{path}: not valid UTF-8 ({error.reason})",
                fix=f"Fix or delete {path}.",
            ) from error
        except json.JSONDecodeError as error:
            raise FileFormatError(
                f"{path}: invalid JSON at line {error.lineno}, column {error.colno}: {error.msg}",
                fix=f"Fix or delete {path}.",
            ) from error
        return data

    def write_json(self, path: Path, data: object) -> None:
        self.write_atomic(path, json.dumps(data, indent=2, sort_keys=True) + "\n")

    def append_line(self, path: Path, line: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="") as handle:
            handle.write(line + "\n")
