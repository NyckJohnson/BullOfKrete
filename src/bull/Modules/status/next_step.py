"""The next step, by priority and stage.

Priority: paused, then waiting for a contract approval, then a blocked unit, then the
step for the current track's stage. FEATURE and ADOPT texts start "feature <slug>:" /
"adoption:" and use `/bull:feature` / `/bull:adopt` for every stage command. When the
current git branch is known and is neither the base nor the branch of the module in
progress, the text starts "switch to <branch>, then".
"""

from __future__ import annotations

from bull.Modules.status.Contracts import (
    Mode,
    ModuleState,
    ModuleStatus,
    NextStep,
    Refs,
    Status,
    StatusError,
    Track,
    Unit,
    UnitKind,
    UnitState,
)
from bull.Modules.status.transitions import first_unfinished

_APP_STAGE_COMMANDS = {
    0: "/bull:discuss",
    1: "/bull:discuss",
    3: "/bull:skeleton",
    4: "/bull:prototype",
}

_CODE_UNIT_STEPS = {
    UnitState.PENDING: "test-writer",
    UnitState.TESTS: "code-writer, then gates --fast",
    UnitState.CODE: "reviewer",
}

_SWITCH_OVER_STEPS = {
    UnitState.PENDING: "switch-over: legacy-test-scanner, then test-writer for missed cases",
    UnitState.TESTS: "switch-over: code-writer, then test-writer, then gates --fast",
    UnitState.CODE: "switch-over: reviewer",
}


def _track(status: Status, mode: Mode) -> Track:
    if mode == Mode.ADOPT:
        if status.adoption is None:
            raise StatusError("adopt mode without an active adoption in status.json")
        return status.adoption
    if mode == Mode.FEATURE:
        if status.feature is None:
            raise StatusError("feature mode without an active feature in status.json")
        return status.feature.track
    return status.app


def _label(status: Status, mode: Mode) -> str:
    if mode == Mode.FEATURE and status.feature is not None:
        return f"feature {status.feature.slug}: "
    if mode == Mode.ADOPT:
        return "adoption: "
    return ""


def _blocked(status: Status) -> tuple[ModuleStatus, Unit] | None:
    for module in status.modules:
        for unit in module.units:
            if unit.state == UnitState.BLOCKED:
                return module, unit
    return None


def _in_progress(status: Status) -> ModuleStatus | None:
    return next((m for m in status.modules if m.state == ModuleState.IN_PROGRESS), None)


def _stage_command(track: Track, mode: Mode) -> str:
    """The command for a stage other than 5; once the checkpoint ending stage 2, 3 or 4
    is recorded, the next stage's command."""
    if mode == Mode.FEATURE:
        return "run /bull:feature"
    if mode == Mode.ADOPT:
        return "run /bull:adopt"
    if track.stage == 2:
        if "setup" in track.checkpoints:
            return "run /bull:skeleton"
        if "outline-approved" in track.checkpoints:
            return "run /bull:setup"
        return "run /bull:outline"
    if track.stage == 3 and "skeleton" in track.checkpoints:
        return "run /bull:prototype"
    if track.stage == 4 and "ui-approved" in track.checkpoints:
        return "run /bull:build"
    if track.stage >= 6:
        if "app-accepted" in track.checkpoints:
            return "run /bull:feature"
        return "run /bull:verify"
    return f"run {_APP_STAGE_COMMANDS.get(track.stage, '/bull:discuss')}"


def _module_step(module: ModuleStatus, refs: Refs) -> str:
    """The step for the module in progress."""
    unit = first_unfinished(module)
    if unit is not None:
        steps = (
            _SWITCH_OVER_STEPS
            if unit.kind == UnitKind.SWITCH_OVER
            else _CODE_UNIT_STEPS
        )
        return f"{module.name} unit {unit.number}: {steps[unit.state]}"
    if module.reference_tests and module.scan is None:
        return f"reference-test scan for {module.name}"
    return (
        f"{module.name}: coverage triage, full gates, "
        f"merge {refs.module_branch(module.name)} into {refs.base()}"
    )


def _start_step(status: Status, mode: Mode, refs: Refs) -> str:
    """The step when no module is in progress."""
    done = {m.name for m in status.modules if m.state == ModuleState.DONE}
    if len(done) == len(status.modules):
        final = {
            Mode.APP: "/bull:verify",
            Mode.FEATURE: "/bull:feature",
            Mode.ADOPT: "/bull:adopt",
        }[mode]
        return f"`bull gates --all`, then {final}"
    for module in status.modules:
        if module.state == ModuleState.PENDING and all(
            d in done for d in module.depends
        ):
            return f"start {module.name} on {refs.module_branch(module.name)}"
    stuck = ", ".join(m.name for m in status.modules if m.name not in done)
    return f"no module can start (not done: {stuck}): ask the human"


def next_step(status: Status, mode: Mode, refs: Refs, branch: str | None) -> NextStep:
    """The next step for `status` in `mode`; `branch` is the current git branch, None
    when unknown."""
    label = _label(status, mode)
    if status.pause is not None:
        return NextStep(
            f"{label}paused ({status.pause.reason}): run /bull:resume", mode
        )
    if status.waiting is not None:
        return NextStep(
            f"{label}waiting for the human to approve the "
            f"{status.waiting.module} contract change",
            mode,
        )
    blocked = _blocked(status)
    if blocked is not None:
        stuck, unit = blocked
        return NextStep(
            f"{label}{stuck.name} unit {unit.number} is blocked: ask the human", mode
        )

    track = _track(status, mode)
    target = refs.base()
    if track.stage == 5:
        module = _in_progress(status)
        if module is not None:
            target = refs.module_branch(module.name)
            text = _module_step(module, refs)
        else:
            text = _start_step(status, mode, refs)
    else:
        text = _stage_command(track, mode)

    switch = ""
    if branch is not None and branch not in (refs.base(), target):
        switch = f"switch to {target}, then "
    return NextStep(f"{switch}{label}{text}", mode)
