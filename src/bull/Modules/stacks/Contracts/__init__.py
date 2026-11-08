"""stacks contract: stack manifests, readers, the registry and the per-app stack operations."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol

from bull.Modules.foundation.Contracts import AppLayout, BullError
from bull.Modules.settings.Contracts import SettingValue, StackLayer


class StackKind(Enum):
    APP = "app"
    SERVICE = "service"
    TOOL = "tool"


class Maturity(Enum):
    EXPERIMENTAL = "experimental"
    VERIFIED = "verified"
    TEST = "test"


class IssueLevel(Enum):
    BLOCK = "block"
    FIX = "fix"
    NOTE = "note"


class Role(Enum):
    PROVIDER = "provider"
    CONSUMER = "consumer"


class StackError(BullError): ...


@dataclass(frozen=True)
class Requirement:
    tool: str
    hint: str


@dataclass(frozen=True)
class GateCommands:
    preflight: tuple[str, ...]
    setup: tuple[str, ...]
    build_test: tuple[str, ...]
    build_test_fast: tuple[str, ...]
    lint: tuple[str, ...]
    rerun_failed: tuple[str, ...]
    journeys: tuple[str, ...] | None


@dataclass(frozen=True)
class RunCommands:
    start: tuple[str, ...]
    ready: tuple[str, ...]
    stop: tuple[str, ...]
    ready_timeout: float


@dataclass(frozen=True)
class StackManifest:
    name: str
    title: str
    description: str
    language: str
    kind: StackKind
    maturity: Maturity
    source_glob: str
    test_glob: tuple[str, ...]
    comment: str
    scaffold: tuple[str, ...]
    gitignore: tuple[str, ...]
    agents: tuple[str, ...]
    requires: tuple[Requirement, ...]
    settings: StackLayer
    gates: GateCommands
    run: RunCommands | None
    interface_formats: tuple[str, ...]
    commands: Mapping[str, tuple[str, ...]]


@dataclass(frozen=True)
class CheckItem:
    ok: bool
    item: str
    fix: str


@dataclass(frozen=True)
class TestRun:
    count: int
    failed: tuple[str, ...]


@dataclass(frozen=True)
class CoverageData:
    uncovered: Mapping[Path, tuple[int, ...]]
    no_data: tuple[Path, ...]


@dataclass(frozen=True)
class Issue:
    level: IssueLevel
    item: str
    fix: str


@dataclass(frozen=True)
class Detection:
    confidence: float
    summary: str
    settings: Mapping[str, str]
    issues: tuple[Issue, ...]


class StackReaders(Protocol):
    """Functions every stack's readers.py defines."""

    def contract_declarations(self, path: Path) -> list[str]: ...
    def test_results(self, results: Path) -> TestRun | None: ...
    def uncovered(
        self, part_root: Path, sources: Sequence[Path], results: Path
    ) -> CoverageData: ...
    def check(
        self, part_root: Path, settings: Mapping[str, SettingValue], adopting: bool
    ) -> list[CheckItem]: ...


@dataclass(frozen=True)
class OptionalReaders:
    detect: Callable[[Path], Detection] | None
    inventory: Callable[[Path, Mapping[str, SettingValue]], str] | None
    legacy_declarations: Callable[[Path], list[str]] | None
    interface_check: (
        Callable[
            [Path, Mapping[str, SettingValue], Path, str, Role, str], list[CheckItem]
        ]
        | None
    )


@dataclass(frozen=True)
class Stack:
    manifest: StackManifest
    home: Path
    builtin: bool
    readers: StackReaders
    optional: OptionalReaders


class StackRegistry(Protocol):
    def all(self, include_test: bool = False) -> list[Stack]: ...
    def get(self, name: str) -> Stack: ...
    def load_path(self, path: Path) -> Stack: ...
    def install(self, path: Path) -> Stack: ...


class StackOps(Protocol):
    def select(self, app: AppLayout, name: str) -> None: ...
    def rules(self, stack: Stack, agent: str) -> str: ...
    def setup_guide(self, stack: Stack, section: str | None = None) -> str: ...
    def check(self, app: AppLayout, part: str | None = None) -> list[CheckItem]: ...
    def run_command(
        self, app: AppLayout, command: str, part: str | None = None
    ) -> int: ...
