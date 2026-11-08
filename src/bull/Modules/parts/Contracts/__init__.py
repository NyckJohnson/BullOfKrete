"""parts contract: an app's parts and their folders."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from bull.Modules.foundation.Contracts import AppLayout


@dataclass(frozen=True)
class Part:
    name: str
    stack: str
    dir: str
    root: Path
    source_dir: Path
    test_dir: Path


class Parts(Protocol):
    def all(self, app: AppLayout) -> list[Part]: ...
    def get(self, app: AppLayout, name: str | None = None) -> Part: ...
    def add(
        self, app: AppLayout, name: str, stack: str, dir: str | None = None
    ) -> Part: ...
    def check(self, app: AppLayout) -> list[str]: ...
    def module_src(self, part: Part, module: str) -> Path: ...
    def module_tests(self, part: Part, module: str) -> Path: ...
    def is_test_path(self, app: AppLayout, path: Path) -> bool: ...
