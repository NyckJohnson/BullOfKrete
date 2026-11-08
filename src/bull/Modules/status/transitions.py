"""Stage, checkpoint, unit and attempt transitions and their rules.

Each function is pure: it takes the current `Status` first, then the store method's
arguments, then keyword-only context, and returns the new `Status` (or raises
`StatusError` on refusal). `LiveStatusStore` calls them through this module.

A change that has nothing to do (a checkpoint recorded twice, resume when not paused,
take_approval with none) returns a status equal to the one it was given; the store then
writes and logs nothing.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import datetime

from bull.Modules.status.Contracts import (
    ActiveFeature,
    Approval,
    Mode,
    ModuleState,
    ModuleStatus,
    Pause,
    Plan,
    PlanItem,
    ScanRecord,
    Status,
    StatusError,
    Track,
    Unit,
    UnitState,
    Waiting,
)

MIN_STAGE = 0
MAX_STAGE = 6

_APP_CHECKPOINTS = (
    "outline-approved",
    "setup",
    "skeleton",
    "ui-approved",
    "app-accepted",
)
_FEATURE_CHECKPOINTS = (*_APP_CHECKPOINTS, "accepted")
_ADOPT_CHECKPOINTS = ("outline-approved", "setup", "baseline", "scaffold", "adopted")

_CHECKPOINTS: dict[Mode, tuple[str, ...]] = {
    Mode.APP: _APP_CHECKPOINTS,
    Mode.FEATURE: _FEATURE_CHECKPOINTS,
    Mode.ADOPT: _ADOPT_CHECKPOINTS,
}

# Checkpoints that close a track; they need the track at stage 6.
_FINAL_CHECKPOINTS = frozenset({"app-accepted", "accepted", "adopted"})

# The checkpoints a track needs to enter each stage (cumulative: entering stage n needs
# those of every stage up to n).
_APP_NEEDS: dict[int, tuple[str, ...]] = {
    3: ("outline-approved", "setup"),
    4: ("skeleton",),
    5: ("ui-approved",),
}
_ADOPT_NEEDS: dict[int, tuple[str, ...]] = {
    3: ("outline-approved", "setup"),
    4: ("baseline",),
    5: ("scaffold",),
}

# Allowed unit state changes through `set_unit` (`code → tests` is the retry path).
_UNIT_MOVES = frozenset(
    {
        (UnitState.PENDING, UnitState.TESTS),
        (UnitState.TESTS, UnitState.CODE),
        (UnitState.CODE, UnitState.DONE),
        (UnitState.CODE, UnitState.TESTS),
    }
)


# --- shared helpers (also used by modules.py and next_step.py) ----------------------------


def mode_of(status: Status) -> Mode:
    """ADOPT while an adoption is active, else FEATURE while a feature is, else APP."""
    if status.adoption is not None:
        return Mode.ADOPT
    if status.feature is not None:
        return Mode.FEATURE
    return Mode.APP


def track_of(status: Status) -> Track:
    """The track of the status's current mode."""
    if status.adoption is not None:
        return status.adoption
    if status.feature is not None:
        return status.feature.track
    return status.app


def _with_track(status: Status, track: Track) -> Status:
    if status.adoption is not None:
        return replace(status, adoption=track)
    if status.feature is not None:
        return replace(status, feature=replace(status.feature, track=track))
    return replace(status, app=track)


def find_module(status: Status, name: str) -> ModuleStatus:
    """The module called `name`; unknown → `StatusError` suggesting a case-insensitive
    match ("did you mean `Counter`?") or else listing the modules."""
    for module in status.modules:
        if module.name == name:
            return module
    for module in status.modules:
        if module.name.lower() == name.lower():
            raise StatusError(
                f"unknown module {name!r}", f"did you mean `{module.name}`?"
            )
    names = ", ".join(m.name for m in status.modules) or "none yet"
    raise StatusError(f"unknown module {name!r}", f"the modules are: {names}")


def put_module(status: Status, module: ModuleStatus) -> Status:
    """`status` with the module of the same name replaced by `module`."""
    return replace(
        status,
        modules=tuple(module if m.name == module.name else m for m in status.modules),
    )


def _find_unit(module: ModuleStatus, number: int) -> Unit:
    for unit in module.units:
        if unit.number == number:
            return unit
    numbers = ", ".join(str(u.number) for u in module.units) or "none"
    raise StatusError(
        f"{module.name} has no unit {number}", f"its units are: {numbers}"
    )


def _put_unit(status: Status, module: ModuleStatus, unit: Unit) -> Status:
    units = tuple(unit if u.number == unit.number else u for u in module.units)
    return put_module(status, replace(module, units=units))


def _change_unit(
    status: Status, name: str, number: int, change: Callable[[Unit], Unit]
) -> tuple[Status, Unit]:
    module = find_module(status, name)
    unit = change(_find_unit(module, number))
    return _put_unit(status, module, unit), unit


def first_unfinished(module: ModuleStatus) -> Unit | None:
    """The module's first unit that is not done, if any."""
    return next((u for u in module.units if u.state != UnitState.DONE), None)


# --- stage and checkpoint -----------------------------------------------------------------


def set_stage(status: Status, stage: int) -> Status:
    """Move the current mode's track to `stage` (0–6).

    Moving forward needs the checkpoints that close the earlier stages (see `_APP_NEEDS`,
    `_ADOPT_NEEDS`) and, for stage 6, every module done; moving back is always allowed.
    """
    if not MIN_STAGE <= stage <= MAX_STAGE:
        raise StatusError(
            f"stage {stage} is not a stage",
            f"stages run from {MIN_STAGE} to {MAX_STAGE}",
        )
    track = track_of(status)
    if stage > track.stage:
        needs = _ADOPT_NEEDS if mode_of(status) == Mode.ADOPT else _APP_NEEDS
        required = [cp for n in sorted(needs) if n <= stage for cp in needs[n]]
        missing = [cp for cp in required if cp not in track.checkpoints]
        if missing:
            raise StatusError(
                f"stage {stage} needs the checkpoint(s) {', '.join(missing)}",
                "record them with `bull status checkpoint <name>` first",
            )
        if stage == MAX_STAGE:
            unfinished = [m.name for m in status.modules if m.state != ModuleState.DONE]
            if unfinished:
                raise StatusError(
                    f"stage 6 needs every module done; not done: {', '.join(unfinished)}",
                    "finish those modules first",
                )
    return _with_track(status, Track(stage, track.checkpoints))


def checkpoint(status: Status, name: str) -> Status:
    """Record checkpoint `name` on the current mode's track; recording twice is a no-op."""
    mode = mode_of(status)
    allowed = _CHECKPOINTS[mode]
    if name not in allowed:
        raise StatusError(
            f"{name!r} is not a {mode.value} checkpoint",
            f"the checkpoints are: {', '.join(allowed)}",
        )
    track = track_of(status)
    if name in track.checkpoints:
        return status
    if name in _FINAL_CHECKPOINTS and track.stage != MAX_STAGE:
        raise StatusError(
            f"checkpoint {name} needs stage 6 (now at stage {track.stage})",
            "verify the work in stage 6 first",
        )
    return _with_track(status, Track(track.stage, (*track.checkpoints, name)))


# --- units --------------------------------------------------------------------------------


def set_unit(status: Status, name: str, number: int, state: UnitState) -> Status:
    """Move a unit along pending → tests → code → done (or code → tests for a retry).

    Setting the state a unit already has is a no-op; a blocked unit is refused until
    unblocked.
    """

    def change(unit: Unit) -> Unit:
        if unit.state == UnitState.BLOCKED:
            raise StatusError(
                f"{name} unit {number} is blocked",
                f"ask the human, then `bull status unblock {name} {number}`",
            )
        if unit.state == state:
            return unit
        if (unit.state, state) not in _UNIT_MOVES:
            raise StatusError(
                f"{name} unit {number} cannot go from {unit.state.value} to {state.value}",
                "units go pending → tests → code → done (code → tests for a retry)",
            )
        return replace(unit, state=state)

    return _change_unit(status, name, number, change)[0]


def attempt(
    status: Status, name: str, number: int, *, max_attempts: int
) -> tuple[Status, Unit]:
    """Start another attempt at a unit.

    Below `max_attempts`: attempts + 1 and the unit goes back to `tests` (the code work is
    redone). At the limit: the unit is `blocked` with its attempts unchanged; the store saves
    that and then raises.
    """

    def change(unit: Unit) -> Unit:
        if unit.attempts < max_attempts:
            return replace(unit, state=UnitState.TESTS, attempts=unit.attempts + 1)
        return replace(unit, state=UnitState.BLOCKED)

    return _change_unit(status, name, number, change)


def unblock(status: Status, name: str, number: int) -> Status:
    """Return a unit to `tests` with one attempt."""
    return _change_unit(
        status,
        name,
        number,
        lambda unit: replace(unit, state=UnitState.TESTS, attempts=1),
    )[0]


# --- pause, wait, approvals ---------------------------------------------------------------


def _unit_in_progress(status: Status) -> str | None:
    for module in status.modules:
        if module.state == ModuleState.IN_PROGRESS:
            unit = first_unfinished(module)
            if unit is not None:
                return f"{module.name} unit {unit.number}"
    return None


def pause(status: Status, reason: str, *, now: datetime) -> Status:
    """Record a pause with its reason, time and the unit in progress ("Counter unit 2")."""
    return replace(status, pause=Pause(reason, now, _unit_in_progress(status)))


def resume(status: Status) -> Status:
    """Clear the pause; a no-op when not paused."""
    if status.pause is None:
        return status
    return replace(status, pause=None)


def wait(status: Status, module: str, what: str, *, now: datetime) -> Status:
    """Record that `module` waits for the human to approve `what`."""
    return replace(status, waiting=Waiting(module, what, now))


def approve(status: Status, module: str, note: str, *, now: datetime) -> Status:
    """Append an approval for `module`, clearing a wait for the same module."""
    waiting = status.waiting
    if waiting is not None and waiting.module == module:
        waiting = None
    return replace(
        status,
        waiting=waiting,
        approvals=(*status.approvals, Approval(module, note, now)),
    )


def take_approval(status: Status, module: str) -> tuple[Status, Approval | None]:
    """Remove and return the oldest approval for `module`; none → (status, None)."""
    for index, approval in enumerate(status.approvals):
        if approval.module == module:
            rest = status.approvals[:index] + status.approvals[index + 1 :]
            return replace(status, approvals=rest), approval
    return status, None


def record_scan(
    status: Status,
    module: str,
    covered: int,
    missed: int,
    contradicts: int,
    not_in_spec: int,
    *,
    now: datetime,
) -> Status:
    """Record a reference-test scan; only for a module with reference tests, counts ≥ 0."""
    found = find_module(status, module)
    if not found.reference_tests:
        raise StatusError(
            f"{module} has no reference tests to scan",
            "only modules with a `Reference tests:` line in the memo get a scan",
        )
    counts = {
        "covered": covered,
        "missed": missed,
        "contradicts": contradicts,
        "not-in-spec": not_in_spec,
    }
    negative = [key for key, value in counts.items() if value < 0]
    if negative:
        raise StatusError(
            f"scan counts must be 0 or more: {', '.join(negative)}",
            "pass the counts from the legacy-test-scanner's report",
        )
    scan = ScanRecord(now, covered, missed, contradicts, not_in_spec)
    return put_module(status, replace(found, scan=scan))


# --- plan ---------------------------------------------------------------------------------


def set_plan(status: Status, label: str, items: Sequence[str]) -> Status:
    """Replace the progress gauge with `items`, none done."""
    return replace(
        status, plan=Plan(label, tuple(PlanItem(item, False) for item in items))
    )


def tick(status: Status, item: str) -> Status:
    """Mark a plan item done; an unknown item or no plan is refused."""
    plan = status.plan
    if plan is None:
        raise StatusError("there is no plan to tick", "set one with `bull status plan`")
    if all(i.name != item for i in plan.items):
        names = ", ".join(i.name for i in plan.items)
        raise StatusError(
            f"plan {plan.label!r} has no item {item!r}", f"its items are: {names}"
        )
    items = tuple(replace(i, done=True) if i.name == item else i for i in plan.items)
    return replace(status, plan=replace(plan, items=items))


def clear_plan(status: Status) -> Status:
    """Remove the progress gauge."""
    return replace(status, plan=None)


# --- features -----------------------------------------------------------------------------


def start_feature(status: Status, slug: str) -> Status:
    """Start feature `slug` at stage 1; needs `app-accepted`, no adoption, no feature."""
    if status.adoption is not None:
        raise StatusError(
            "a feature cannot start during an adoption", "finish the adoption first"
        )
    if "app-accepted" not in status.app.checkpoints:
        raise StatusError(
            "a feature needs the app-accepted checkpoint first",
            "finish and accept the app in stage 6",
        )
    if status.feature is not None:
        raise StatusError(
            f"feature {status.feature.slug} is still active",
            "accept or abandon it before starting another",
        )
    return replace(status, feature=ActiveFeature(slug, Track(1, ()), ()))


def end_feature(status: Status) -> Status:
    """Clear the active feature."""
    if status.feature is None:
        raise StatusError("no feature is active")
    return replace(status, feature=None)


def mark_contract_applied(status: Status, module: str) -> Status:
    """Record that the active feature's contract changes for `module` are applied."""
    feature = status.feature
    if feature is None:
        raise StatusError(
            "no feature is active", "contract changes belong to a feature"
        )
    if module in feature.applied_contracts:
        return status
    applied = (*feature.applied_contracts, module)
    return replace(status, feature=replace(feature, applied_contracts=applied))


# --- adoption -----------------------------------------------------------------------------


def start_adoption(status: Status) -> Status:
    """Start an adoption at stage 1; refused once modules exist or the app is past stage 0."""
    if status.adoption is not None:
        raise StatusError("an adoption is already active")
    if status.feature is not None:
        raise StatusError(
            f"feature {status.feature.slug} is active", "an adoption cannot start now"
        )
    if status.modules or status.app.stage > MIN_STAGE:
        raise StatusError(
            "an adoption can only start in a new app (stage 0, no modules)",
            "this app is already being built by the pipeline",
        )
    return replace(status, adoption=Track(1, ()))


def finish_adoption(status: Status) -> Status:
    """Close the adoption at stage 6: the app track gets `app-accepted` at stage 6."""
    adoption = status.adoption
    if adoption is None:
        raise StatusError("no adoption is active")
    if adoption.stage != MAX_STAGE:
        raise StatusError(
            f"the adoption is at stage {adoption.stage}; finishing needs stage 6",
            "verify the adopted app first",
        )
    checkpoints = status.app.checkpoints
    if "app-accepted" not in checkpoints:
        checkpoints = (*checkpoints, "app-accepted")
    return replace(status, app=Track(MAX_STAGE, checkpoints), adoption=None)


def abandon_adoption(status: Status) -> Status:
    """Clear the adoption, leaving the app track as it was."""
    if status.adoption is None:
        raise StatusError("no adoption is active")
    return replace(status, adoption=None)
