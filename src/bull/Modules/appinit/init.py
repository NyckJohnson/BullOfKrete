"""`bull init` and `bull open`."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from bull.Modules.appinit.Contracts import AppInit, InitResult


class LiveAppInit(AppInit):
    def init(self, path: Path, adopt: bool = False) -> InitResult:
        raise NotImplementedError(f"{type(self).__name__}.init")

    def open_argv(self, path: Path, extra: Sequence[str]) -> list[str]:
        raise NotImplementedError(f"{type(self).__name__}.open_argv")
