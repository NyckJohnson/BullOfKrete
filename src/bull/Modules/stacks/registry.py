"""The stack registry: built-in and installed stacks."""

from __future__ import annotations

from pathlib import Path

from bull.Modules.stacks.Contracts import Stack, StackRegistry


class LiveStackRegistry(StackRegistry):
    def all(self, include_test: bool = False) -> list[Stack]:
        raise NotImplementedError(f"{type(self).__name__}.all")

    def get(self, name: str) -> Stack:
        raise NotImplementedError(f"{type(self).__name__}.get")

    def load_path(self, path: Path) -> Stack:
        raise NotImplementedError(f"{type(self).__name__}.load_path")

    def install(self, path: Path) -> Stack:
        raise NotImplementedError(f"{type(self).__name__}.install")
