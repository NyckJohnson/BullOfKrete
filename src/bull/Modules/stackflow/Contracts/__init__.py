"""stackflow contract: the stack repo workflow and stack installation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Protocol

from bull.Modules.stacks.Contracts import Stack
from bull.Modules.stacktest.Contracts import StackTestReport


class StackStage(IntEnum):
    DISCUSS = 1
    SCAFFOLD = 2
    FIXTURE = 3
    GATE_CODE = 4
    REVIEW = 5
    ACCEPTED = 6


@dataclass(frozen=True)
class StackRepoStatus:
    format: int
    name: str
    stage: StackStage
    checkpoints: tuple[str, ...]
    static_pass: str | None
    test_pass: str | None  # sha of the last passing run


class StackWorkflow(Protocol):
    def init(self, path: Path) -> StackRepoStatus: ...
    def load(self, path: Path) -> StackRepoStatus: ...
    def set_stage(self, path: Path, stage: int) -> StackRepoStatus: ...
    def checkpoint(self, path: Path, name: str) -> StackRepoStatus: ...
    def record_test(self, path: Path, report: StackTestReport) -> StackRepoStatus: ...
    def next_step(self, path: Path) -> str: ...
    def ref(self, kind: str, name: str) -> str: ...


class StackInstaller(Protocol):
    def install(self, path: Path) -> Stack: ...
