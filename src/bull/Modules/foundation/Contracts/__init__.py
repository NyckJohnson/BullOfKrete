"""foundation contract: errors, the app layout, files, the process runner and the clock."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol


class BullError(Exception):
    """An error bull reports to the user: what went wrong and, when known, how to fix it."""

    def __init__(self, message: str, fix: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.fix = fix

    message: str
    fix: str


class ToolMissing(BullError): ...  # an executable isn't on PATH


class FileFormatError(BullError): ...  # unreadable JSON/TOML; message names the path


@dataclass(frozen=True)
class AppLayout:
    root: Path
    bull_dir: Path
    config_file: Path
    parts_dir: Path
    status_file: Path
    backlog_file: Path
    usage_file: Path
    events_file: Path
    passes_dir: Path
    results_dir: Path
    plugin_dir: Path
    run_dir: Path
    memo_file: Path
    api_dir: Path
    features_dir: Path
    interfaces_dir: Path


class Layouts(Protocol):
    def at(self, root: Path) -> AppLayout: ...
    def find(self, start: Path) -> AppLayout | None: ...
    def user_config_dir(self) -> Path: ...
    def user_data_dir(self) -> Path: ...
    def machine_local_ignores(self) -> list[str]: ...


class Files(Protocol):
    def read_text(self, path: Path) -> str | None: ...
    def write_atomic(self, path: Path, text: str) -> None: ...
    def read_json(self, path: Path) -> object | None: ...
    def write_json(self, path: Path, data: object) -> None: ...
    def append_line(self, path: Path, line: str) -> None: ...


@dataclass(frozen=True)
class RunResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    seconds: float


class Spawned(Protocol):
    pid: int

    def alive(self) -> bool: ...
    def stop(self, grace: float = 5.0) -> None: ...


class Runner(Protocol):
    def run(
        self,
        argv: Sequence[str],
        cwd: Path,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> RunResult: ...
    def spawn(
        self,
        argv: Sequence[str],
        cwd: Path,
        env: Mapping[str, str] | None = None,
        log: Path | None = None,
    ) -> Spawned: ...
    def which(self, tool: str) -> Path | None: ...


class Clock(Protocol):
    def now(self) -> datetime: ...
