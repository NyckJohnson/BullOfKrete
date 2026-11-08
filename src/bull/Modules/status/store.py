"""The status store: reads, validates and writes `.bull/status.json`."""

from __future__ import annotations

from collections.abc import Sequence

from bull.Modules.memo.Contracts import Memo, ModuleEntry
from bull.Modules.status.Contracts import (
    Approval,
    Mode,
    ModuleState,
    Status,
    StatusStore,
    Unit,
    UnitState,
)


class LiveStatusStore(StatusStore):
    def load(self) -> Status:
        raise NotImplementedError(f"{type(self).__name__}.load")

    def create(self) -> Status:
        raise NotImplementedError(f"{type(self).__name__}.create")

    def mode(self) -> Mode:
        raise NotImplementedError(f"{type(self).__name__}.mode")

    def set_stage(self, stage: int) -> Status:
        raise NotImplementedError(f"{type(self).__name__}.set_stage")

    def checkpoint(self, name: str) -> Status:
        raise NotImplementedError(f"{type(self).__name__}.checkpoint")

    def init_modules(self, memo: Memo, replace: bool = False) -> Status:
        raise NotImplementedError(f"{type(self).__name__}.init_modules")

    def set_module(self, name: str, state: ModuleState) -> Status:
        raise NotImplementedError(f"{type(self).__name__}.set_module")

    def set_unit(self, name: str, number: int, state: UnitState) -> Status:
        raise NotImplementedError(f"{type(self).__name__}.set_unit")

    def attempt(self, name: str, number: int) -> Unit:
        raise NotImplementedError(f"{type(self).__name__}.attempt")

    def unblock(self, name: str, number: int) -> Status:
        raise NotImplementedError(f"{type(self).__name__}.unblock")

    def pause(self, reason: str) -> Status:
        raise NotImplementedError(f"{type(self).__name__}.pause")

    def resume(self) -> Status:
        raise NotImplementedError(f"{type(self).__name__}.resume")

    def wait(self, module: str, what: str) -> Status:
        raise NotImplementedError(f"{type(self).__name__}.wait")

    def approve(self, module: str, note: str) -> Status:
        raise NotImplementedError(f"{type(self).__name__}.approve")

    def take_approval(self, module: str) -> Approval | None:
        raise NotImplementedError(f"{type(self).__name__}.take_approval")

    def record_scan(
        self, module: str, covered: int, missed: int, contradicts: int, not_in_spec: int
    ) -> Status:
        raise NotImplementedError(f"{type(self).__name__}.record_scan")

    def set_plan(self, label: str, items: Sequence[str]) -> Status:
        raise NotImplementedError(f"{type(self).__name__}.set_plan")

    def tick(self, item: str) -> Status:
        raise NotImplementedError(f"{type(self).__name__}.tick")

    def clear_plan(self) -> Status:
        raise NotImplementedError(f"{type(self).__name__}.clear_plan")

    def start_feature(self, slug: str) -> Status:
        raise NotImplementedError(f"{type(self).__name__}.start_feature")

    def end_feature(self) -> Status:
        raise NotImplementedError(f"{type(self).__name__}.end_feature")

    def mark_contract_applied(self, module: str) -> Status:
        raise NotImplementedError(f"{type(self).__name__}.mark_contract_applied")

    def reopen(self, module: str, files: Sequence[str]) -> Status:
        raise NotImplementedError(f"{type(self).__name__}.reopen")

    def add_modules(self, entries: Sequence[ModuleEntry]) -> Status:
        raise NotImplementedError(f"{type(self).__name__}.add_modules")

    def start_adoption(self) -> Status:
        raise NotImplementedError(f"{type(self).__name__}.start_adoption")

    def finish_adoption(self) -> Status:
        raise NotImplementedError(f"{type(self).__name__}.finish_adoption")

    def abandon_adoption(self) -> Status:
        raise NotImplementedError(f"{type(self).__name__}.abandon_adoption")
