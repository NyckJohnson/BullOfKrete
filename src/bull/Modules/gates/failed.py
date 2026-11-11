"""The failed-test list in `.bull/results/<part>/failed.txt`."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from bull.Modules.foundation.Contracts import Files

_FAILED_FILE = "failed.txt"


def read_failed(files: Files, results: Path) -> tuple[str, ...]:
    """The test ids in `results/failed.txt`, one per line.

    Blank lines and surrounding whitespace are dropped; a missing file gives `()`.
    """
    text = files.read_text(results / _FAILED_FILE)
    if text is None:
        return ()
    return tuple(line.strip() for line in text.splitlines() if line.strip())


def write_failed(files: Files, results: Path, ids: Sequence[str]) -> None:
    """Replace `results/failed.txt` with `ids`, one per line (no ids: an empty file)."""
    text = "".join(f"{test_id}\n" for test_id in ids)
    files.write_atomic(results / _FAILED_FILE, text)
