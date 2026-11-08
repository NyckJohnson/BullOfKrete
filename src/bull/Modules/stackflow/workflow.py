"""The stack repo workflow: stages, checkpoints, test passes and refs."""

from __future__ import annotations

from pathlib import Path

from bull.Modules.stackflow.Contracts import StackRepoStatus, StackWorkflow
from bull.Modules.stacktest.Contracts import StackTestReport


class LiveStackWorkflow(StackWorkflow):
    def init(self, path: Path) -> StackRepoStatus:
        raise NotImplementedError(f"{type(self).__name__}.init")

    def load(self, path: Path) -> StackRepoStatus:
        raise NotImplementedError(f"{type(self).__name__}.load")

    def set_stage(self, path: Path, stage: int) -> StackRepoStatus:
        raise NotImplementedError(f"{type(self).__name__}.set_stage")

    def checkpoint(self, path: Path, name: str) -> StackRepoStatus:
        raise NotImplementedError(f"{type(self).__name__}.checkpoint")

    def record_test(self, path: Path, report: StackTestReport) -> StackRepoStatus:
        raise NotImplementedError(f"{type(self).__name__}.record_test")

    def next_step(self, path: Path) -> str:
        raise NotImplementedError(f"{type(self).__name__}.next_step")

    def ref(self, kind: str, name: str) -> str:
        raise NotImplementedError(f"{type(self).__name__}.ref")
