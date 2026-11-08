"""Mocks of the appinit contract, for tests and previews."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from bull.Modules.appinit.Contracts import AppInit, Doctor, DoctorReport, InitResult
from bull.Modules.stacks.Contracts import CheckItem


class MockAppInit(AppInit):
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def init(self, path: Path, adopt: bool = False) -> InitResult:
        self.calls.append(("init", (path, adopt)))
        return InitResult(root=path, created=True, relinked=False, adopting=adopt)

    def open_argv(self, path: Path, extra: Sequence[str]) -> list[str]:
        self.calls.append(("open_argv", (path, tuple(extra))))
        return ["claude", "--plugin-dir", str(path / ".bull" / "plugin"), *extra]


class MockDoctor(Doctor):
    """uv, git and claude found; one stack's toolchain missing."""

    def __init__(self) -> None:
        self.report = DoctorReport(
            items=(
                CheckItem(True, "python 3.12.4", ""),
                CheckItem(True, "uv 0.13.1", ""),
                CheckItem(True, "git 2.47.0", ""),
                CheckItem(True, "claude 2.1.0", ""),
            ),
            stacks=(
                ("python_cli", (CheckItem(True, "uv", ""),)),
                ("go_cli", (CheckItem(False, "go", "install Go: https://go.dev/dl/"),)),
            ),
        )
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def run(self) -> DoctorReport:
        self.calls.append(("run", ()))
        return self.report
