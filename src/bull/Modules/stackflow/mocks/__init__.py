"""Mocks of the stackflow contract, for tests and previews."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from bull.Modules.stackflow.Contracts import (
    StackInstaller,
    StackRepoStatus,
    StackStage,
    StackWorkflow,
)
from bull.Modules.stacks.Contracts import Stack
from bull.Modules.stacks.mocks import sample_stack
from bull.Modules.stacks.Contracts import Maturity
from bull.Modules.stacktest.Contracts import StackTestReport

SAMPLE_SHA = "3f9c2a1e8b7d6c5f4a3b2c1d0e9f8a7b6c5d4e3f"


class MockStackWorkflow(StackWorkflow):
    """A `go_cli` stack repo at stage 1, applying changes without the stage rules."""

    def __init__(self) -> None:
        self.status = StackRepoStatus(
            format=1,
            name="go_cli",
            stage=StackStage.DISCUSS,
            checkpoints=(),
            static_pass=None,
            test_pass=None,
        )
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def init(self, path: Path) -> StackRepoStatus:
        self.calls.append(("init", (path,)))
        self.status = replace(self.status, name=path.name)
        return self.status

    def load(self, path: Path) -> StackRepoStatus:
        self.calls.append(("load", (path,)))
        return self.status

    def set_stage(self, path: Path, stage: int) -> StackRepoStatus:
        self.calls.append(("set_stage", (path, stage)))
        self.status = replace(self.status, stage=StackStage(stage))
        return self.status

    def checkpoint(self, path: Path, name: str) -> StackRepoStatus:
        self.calls.append(("checkpoint", (path, name)))
        if name not in self.status.checkpoints:
            self.status = replace(
                self.status, checkpoints=(*self.status.checkpoints, name)
            )
        return self.status

    def record_test(self, path: Path, report: StackTestReport) -> StackRepoStatus:
        self.calls.append(("record_test", (path, report)))
        if report.static:
            self.status = replace(self.status, static_pass=SAMPLE_SHA)
        else:
            self.status = replace(self.status, test_pass=SAMPLE_SHA)
        return self.status

    def next_step(self, path: Path) -> str:
        self.calls.append(("next_step", (path,)))
        return (
            "discuss the design and fill DESIGN.md; then "
            "`bull status checkpoint design-approved`"
        )

    def ref(self, kind: str, name: str) -> str:
        self.calls.append(("ref", (kind, name)))
        return f"stack/{name}"


class MockStackInstaller(StackInstaller):
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def install(self, path: Path) -> Stack:
        self.calls.append(("install", (path,)))
        return sample_stack(path.name, Maturity.EXPERIMENTAL)
