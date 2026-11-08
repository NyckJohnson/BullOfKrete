"""`bull stack install`: the static self-test, then the registry install."""

from __future__ import annotations

from pathlib import Path

from bull.Modules.stackflow.Contracts import StackInstaller
from bull.Modules.stacks.Contracts import Stack


class LiveStackInstaller(StackInstaller):
    def install(self, path: Path) -> Stack:
        raise NotImplementedError(f"{type(self).__name__}.install")
