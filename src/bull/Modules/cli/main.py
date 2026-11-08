"""`bull`'s entry point: dispatches a command and returns its exit code."""

from __future__ import annotations

from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    raise NotImplementedError("main")
