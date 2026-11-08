"""Mocks of the status contract, for tests and previews."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime

from bull.Modules.memo.Contracts import Memo, ModuleEntry
from bull.Modules.status.Contracts import (
    ActiveFeature,
    Approval,
    Mode,
    ModuleState,
    ModuleStatus,
    NextStep,
    Pause,
    Plan,
    PlanItem,
    Progress,
    Refs,
    ScanRecord,
    Status,
    StatusStore,
    Track,
    Unit,
    UnitKind,
    UnitState,
    Waiting,
)

SAMPLE_TIME = datetime(2026, 11, 7, 12, 0, 0, tzinfo=UTC)


def sample_status() -> Status:
    """`tally` at stage 5: `Store` done, `Counter` in progress with unit 1 at `tests`."""
    store = ModuleStatus(
        name="Store",
        part="app",
        depends=(),
        state=ModuleState.DONE,
        units=(
            Unit(
                1, ("Contracts/store.fx", "store.fx"), UnitKind.CODE, UnitState.DONE, 1
            ),
        ),
        reference_tests=False,
        scan=None,
    )
    counter = ModuleStatus(
        name="Counter",
        part="app",
        depends=("Store",),
        state=ModuleState.IN_PROGRESS,
        units=(
            Unit(
                1,
                ("Contracts/counter.fx", "counter.fx"),
                UnitKind.CODE,
                UnitState.TESTS,
                1,
            ),
            Unit(2, ("cli.fx",), UnitKind.CODE, UnitState.PENDING, 1),
        ),
        reference_tests=False,
        scan=None,
    )
    return Status(
        format=1,
        app=Track(5, ("outline-approved", "setup", "skeleton", "ui-approved")),
        modules=(store, counter),
        pause=None,
        waiting=None,
        approvals=(),
        plan=None,
        feature=None,
        adoption=None,
    )


class MockStatusStore(StatusStore):
    """Keeps a `Status` in memory and applies each change without the real rules."""

    def __init__(self, status: Status | None = None) -> None:
        self.status = status if status is not None else sample_status()
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def _module(self, name: str) -> ModuleStatus:
        return next(m for m in self.status.modules if m.name == name)

    def _put_module(self, module: ModuleStatus) -> Status:
        modules = tuple(
            module if m.name == module.name else m for m in self.status.modules
        )
        self.status = replace(self.status, modules=modules)
        return self.status

    def _put_unit(self, name: str, unit: Unit) -> Status:
        module = self._module(name)
        units = tuple(unit if u.number == unit.number else u for u in module.units)
        return self._put_module(replace(module, units=units))

    def _unit(self, name: str, number: int) -> Unit:
        return next(u for u in self._module(name).units if u.number == number)

    def load(self) -> Status:
        self.calls.append(("load", ()))
        return self.status

    def create(self) -> Status:
        self.calls.append(("create", ()))
        self.status = Status(1, Track(0, ()), (), None, None, (), None, None, None)
        return self.status

    def mode(self) -> Mode:
        self.calls.append(("mode", ()))
        if self.status.adoption is not None:
            return Mode.ADOPT
        if self.status.feature is not None:
            return Mode.FEATURE
        return Mode.APP

    def set_stage(self, stage: int) -> Status:
        self.calls.append(("set_stage", (stage,)))
        self.status = replace(self.status, app=replace(self.status.app, stage=stage))
        return self.status

    def checkpoint(self, name: str) -> Status:
        self.calls.append(("checkpoint", (name,)))
        if name not in self.status.app.checkpoints:
            track = replace(
                self.status.app, checkpoints=(*self.status.app.checkpoints, name)
            )
            self.status = replace(self.status, app=track)
        return self.status

    def init_modules(self, memo: Memo, replace: bool = False) -> Status:
        self.calls.append(("init_modules", (memo, replace)))
        return self.add_modules(memo.modules)

    def set_module(self, name: str, state: ModuleState) -> Status:
        self.calls.append(("set_module", (name, state)))
        return self._put_module(replace(self._module(name), state=state))

    def set_unit(self, name: str, number: int, state: UnitState) -> Status:
        self.calls.append(("set_unit", (name, number, state)))
        return self._put_unit(name, replace(self._unit(name, number), state=state))

    def attempt(self, name: str, number: int) -> Unit:
        self.calls.append(("attempt", (name, number)))
        unit = self._unit(name, number)
        unit = replace(unit, attempts=unit.attempts + 1, state=UnitState.TESTS)
        self._put_unit(name, unit)
        return unit

    def unblock(self, name: str, number: int) -> Status:
        self.calls.append(("unblock", (name, number)))
        unit = replace(self._unit(name, number), state=UnitState.TESTS, attempts=1)
        return self._put_unit(name, unit)

    def pause(self, reason: str) -> Status:
        self.calls.append(("pause", (reason,)))
        self.status = replace(
            self.status, pause=Pause(reason, SAMPLE_TIME, "Counter unit 1")
        )
        return self.status

    def resume(self) -> Status:
        self.calls.append(("resume", ()))
        self.status = replace(self.status, pause=None)
        return self.status

    def wait(self, module: str, what: str) -> Status:
        self.calls.append(("wait", (module, what)))
        self.status = replace(self.status, waiting=Waiting(module, what, SAMPLE_TIME))
        return self.status

    def approve(self, module: str, note: str) -> Status:
        self.calls.append(("approve", (module, note)))
        approvals = (*self.status.approvals, Approval(module, note, SAMPLE_TIME))
        self.status = replace(self.status, waiting=None, approvals=approvals)
        return self.status

    def take_approval(self, module: str) -> Approval | None:
        self.calls.append(("take_approval", (module,)))
        for approval in self.status.approvals:
            if approval.module == module:
                rest = tuple(a for a in self.status.approvals if a is not approval)
                self.status = replace(self.status, approvals=rest)
                return approval
        return None

    def record_scan(
        self, module: str, covered: int, missed: int, contradicts: int, not_in_spec: int
    ) -> Status:
        self.calls.append(
            ("record_scan", (module, covered, missed, contradicts, not_in_spec))
        )
        scan = ScanRecord(SAMPLE_TIME, covered, missed, contradicts, not_in_spec)
        return self._put_module(replace(self._module(module), scan=scan))

    def set_plan(self, label: str, items: Sequence[str]) -> Status:
        self.calls.append(("set_plan", (label, tuple(items))))
        plan = Plan(label, tuple(PlanItem(item, False) for item in items))
        self.status = replace(self.status, plan=plan)
        return self.status

    def tick(self, item: str) -> Status:
        self.calls.append(("tick", (item,)))
        if self.status.plan is not None:
            items = tuple(
                PlanItem(i.name, i.done or i.name == item)
                for i in self.status.plan.items
            )
            self.status = replace(
                self.status, plan=replace(self.status.plan, items=items)
            )
        return self.status

    def clear_plan(self) -> Status:
        self.calls.append(("clear_plan", ()))
        self.status = replace(self.status, plan=None)
        return self.status

    def start_feature(self, slug: str) -> Status:
        self.calls.append(("start_feature", (slug,)))
        feature = ActiveFeature(slug, Track(1, ()), ())
        self.status = replace(self.status, feature=feature)
        return self.status

    def end_feature(self) -> Status:
        self.calls.append(("end_feature", ()))
        self.status = replace(self.status, feature=None)
        return self.status

    def mark_contract_applied(self, module: str) -> Status:
        self.calls.append(("mark_contract_applied", (module,)))
        feature = self.status.feature
        if feature is not None:
            applied = (*feature.applied_contracts, module)
            self.status = replace(
                self.status, feature=replace(feature, applied_contracts=applied)
            )
        return self.status

    def reopen(self, module: str, files: Sequence[str]) -> Status:
        self.calls.append(("reopen", (module, tuple(files))))
        current = self._module(module)
        units = tuple(
            replace(u, state=UnitState.PENDING, attempts=1)
            if set(u.files) & set(files)
            else u
            for u in current.units
        )
        return self._put_module(
            replace(current, units=units, state=ModuleState.PENDING)
        )

    def add_modules(self, entries: Sequence[ModuleEntry]) -> Status:
        self.calls.append(("add_modules", (tuple(entries),)))
        added = tuple(
            ModuleStatus(
                name=entry.name,
                part=entry.part or "app",
                depends=entry.depends,
                state=ModuleState.PENDING,
                units=tuple(
                    Unit(n, files, UnitKind.CODE, UnitState.PENDING, 1)
                    for n, files in enumerate(entry.units, start=1)
                ),
                reference_tests=bool(entry.reference_tests),
                scan=None,
            )
            for entry in entries
        )
        self.status = replace(self.status, modules=(*self.status.modules, *added))
        return self.status

    def start_adoption(self) -> Status:
        self.calls.append(("start_adoption", ()))
        self.status = replace(self.status, adoption=Track(1, ()))
        return self.status

    def finish_adoption(self) -> Status:
        self.calls.append(("finish_adoption", ()))
        app = Track(6, (*self.status.app.checkpoints, "app-accepted"))
        self.status = replace(self.status, app=app, adoption=None)
        return self.status

    def abandon_adoption(self) -> Status:
        self.calls.append(("abandon_adoption", ()))
        self.status = replace(self.status, adoption=None)
        return self.status


class MockRefs(Refs):
    """APP-mode names on the `main` trunk."""

    def __init__(self, prefix: str = "", trunk: str = "main") -> None:
        self.prefix = prefix
        self.trunk_name = trunk
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def trunk(self) -> str:
        self.calls.append(("trunk", ()))
        return self.trunk_name

    def base(self) -> str:
        self.calls.append(("base", ()))
        return f"{self.prefix}main" if self.prefix else self.trunk_name

    def module_branch(self, module: str) -> str:
        self.calls.append(("module_branch", (module,)))
        return f"{self.prefix}module/{module}"

    def tag(self, label: str) -> str:
        self.calls.append(("tag", (label,)))
        return label if label == "adopted" else f"{self.prefix}{label}"

    def module_for_branch(self, branch: str) -> str | None:
        self.calls.append(("module_for_branch", (branch,)))
        start = f"{self.prefix}module/"
        return branch[len(start) :] if branch.startswith(start) else None


class MockProgress(Progress):
    def __init__(self) -> None:
        self.step = NextStep("Counter unit 1: code-writer, then gates --fast", Mode.APP)
        self.tag_names: list[str] = [
            "module/Store",
            "outline-approved",
            "setup",
            "skeleton",
        ]
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def next_step(self) -> NextStep:
        self.calls.append(("next_step", ()))
        return self.step

    def summary(self) -> str:
        self.calls.append(("summary", ()))
        return (
            "stage 5 (app) · units 1/3\n"
            "  Store    done         unit 1 done\n"
            "  Counter  in_progress  unit 1 tests, unit 2 pending\n"
            f"next: {self.step.text}\n"
        )

    def as_json(self) -> dict[str, object]:
        self.calls.append(("as_json", ()))
        return {
            "format": 1,
            "kind": "app",
            "stage": 5,
            "mode": self.step.mode.value,
            "next": self.step.text,
            "units_done": 1,
            "units_total": 3,
        }

    def tags(self) -> list[str]:
        self.calls.append(("tags", ()))
        return sorted(self.tag_names)
