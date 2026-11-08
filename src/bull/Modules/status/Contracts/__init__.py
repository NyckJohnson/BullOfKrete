"""status contract: stages, checkpoints, modules, units and the next step."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol

from bull.Modules.foundation.Contracts import BullError
from bull.Modules.memo.Contracts import Memo, ModuleEntry


class Mode(Enum):
    APP = "app"
    FEATURE = "feature"
    ADOPT = "adopt"


class UnitState(Enum):
    PENDING = "pending"
    TESTS = "tests"
    CODE = "code"
    DONE = "done"
    BLOCKED = "blocked"


class ModuleState(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    BLOCKED = "blocked"


class UnitKind(Enum):
    CODE = "code"
    SWITCH_OVER = "switch-over"


class StatusError(BullError): ...


@dataclass(frozen=True)
class Unit:
    number: int
    files: tuple[str, ...]
    kind: UnitKind
    state: UnitState
    attempts: int


@dataclass(frozen=True)
class ScanRecord:
    time: datetime
    covered: int
    missed: int
    contradicts: int
    not_in_spec: int


@dataclass(frozen=True)
class ModuleStatus:
    name: str
    part: str
    depends: tuple[str, ...]
    state: ModuleState
    units: tuple[Unit, ...]
    reference_tests: bool
    scan: ScanRecord | None


@dataclass(frozen=True)
class Track:
    stage: int
    checkpoints: tuple[str, ...]


@dataclass(frozen=True)
class Pause:
    reason: str
    since: datetime
    unit: str | None


@dataclass(frozen=True)
class Waiting:
    module: str
    what: str
    since: datetime


@dataclass(frozen=True)
class Approval:
    module: str
    note: str
    time: datetime


@dataclass(frozen=True)
class PlanItem:
    name: str
    done: bool


@dataclass(frozen=True)
class Plan:
    label: str
    items: tuple[PlanItem, ...]


@dataclass(frozen=True)
class ActiveFeature:
    slug: str
    track: Track
    applied_contracts: tuple[str, ...]


@dataclass(frozen=True)
class Status:
    format: int
    app: Track
    modules: tuple[ModuleStatus, ...]
    pause: Pause | None
    waiting: Waiting | None
    approvals: tuple[Approval, ...]
    plan: Plan | None
    feature: ActiveFeature | None
    adoption: Track | None


@dataclass(frozen=True)
class NextStep:
    text: str
    mode: Mode


class StatusStore(Protocol):
    def load(self) -> Status: ...
    def create(self) -> Status: ...
    def mode(self) -> Mode: ...
    def set_stage(self, stage: int) -> Status: ...
    def checkpoint(self, name: str) -> Status: ...
    def init_modules(self, memo: Memo, replace: bool = False) -> Status: ...
    def set_module(self, name: str, state: ModuleState) -> Status: ...
    def set_unit(self, name: str, number: int, state: UnitState) -> Status: ...
    def attempt(self, name: str, number: int) -> Unit: ...
    def unblock(self, name: str, number: int) -> Status: ...
    def pause(self, reason: str) -> Status: ...
    def resume(self) -> Status: ...
    def wait(self, module: str, what: str) -> Status: ...
    def approve(self, module: str, note: str) -> Status: ...
    def take_approval(self, module: str) -> Approval | None: ...
    def record_scan(
        self, module: str, covered: int, missed: int, contradicts: int, not_in_spec: int
    ) -> Status: ...
    def set_plan(self, label: str, items: Sequence[str]) -> Status: ...
    def tick(self, item: str) -> Status: ...
    def clear_plan(self) -> Status: ...
    # used by features and adoption:
    def start_feature(self, slug: str) -> Status: ...
    def end_feature(self) -> Status: ...
    def mark_contract_applied(self, module: str) -> Status: ...
    def reopen(self, module: str, files: Sequence[str]) -> Status: ...
    def add_modules(self, entries: Sequence[ModuleEntry]) -> Status: ...
    def start_adoption(self) -> Status: ...
    def finish_adoption(self) -> Status: ...
    def abandon_adoption(self) -> Status: ...


class Refs(Protocol):
    def trunk(self) -> str: ...
    def base(self) -> str: ...
    def module_branch(self, module: str) -> str: ...
    def tag(self, label: str) -> str: ...
    def module_for_branch(self, branch: str) -> str | None: ...


class Progress(Protocol):
    def next_step(self) -> NextStep: ...
    def summary(self) -> str: ...
    def as_json(self) -> dict[str, object]: ...
    def tags(self) -> list[str]: ...
