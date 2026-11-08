"""Modules from the memo: init, add and reopen.

Pure functions over `Status` (current status first, keyword-only context last), called by
`LiveStatusStore` through this module; they raise `StatusError` on refusal.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from bull.Modules.memo.Contracts import Memo, MemoProblem, ModuleEntry
from bull.Modules.status.Contracts import (
    ModuleState,
    ModuleStatus,
    Status,
    StatusError,
    Unit,
    UnitKind,
    UnitState,
)
from bull.Modules.status.transitions import find_module, put_module


def _part_of(entry: ModuleEntry, known_parts: Sequence[str]) -> str:
    """The entry's part, or the app's first (in a one-part app, only) part when it has none."""
    if entry.part is not None:
        return entry.part
    if not known_parts:
        raise StatusError(
            f"module {entry.name} has no part and the app has none",
            "add a part with `bull part add` or select a stack first",
        )
    return known_parts[0]


def _build(
    entry: ModuleEntry, known_parts: Sequence[str], adopting: bool
) -> ModuleStatus:
    """A pending module with one unit per `Files` group (and a switch-over when adopting
    legacy code), each pending at attempt 1."""
    units = [
        Unit(number, tuple(files), UnitKind.CODE, UnitState.PENDING, 1)
        for number, files in enumerate(entry.units, start=1)
    ]
    if adopting and entry.legacy_files:
        units.append(
            Unit(len(units) + 1, (), UnitKind.SWITCH_OVER, UnitState.PENDING, 1)
        )
    return ModuleStatus(
        name=entry.name,
        part=_part_of(entry, known_parts),
        depends=tuple(entry.depends),
        state=ModuleState.PENDING,
        units=tuple(units),
        reference_tests=bool(entry.reference_tests),
        scan=None,
    )


def _in_build_order(memo: Memo) -> list[ModuleEntry]:
    """The memo's modules in build order; modules the build order omits come last.

    Build-order names match module blocks ignoring case (as memo problems do); the block's
    name is the one kept.
    """
    by_name = {entry.name.casefold(): entry for entry in memo.modules}
    ordered: list[ModuleEntry] = []
    for step in memo.build_order:
        entry = by_name.pop(step.name.casefold(), None)
        if entry is None:
            raise StatusError(
                f"build order line {step.line}: {step.name} has no module section",
                "fix the memo, then run `bull status init-modules` again",
            )
        ordered.append(entry)
    ordered.extend(entry for entry in memo.modules if entry.name.casefold() in by_name)
    return ordered


def _started(module: ModuleStatus) -> bool:
    return module.state != ModuleState.PENDING or any(
        u.state != UnitState.PENDING for u in module.units
    )


def init_modules(
    status: Status,
    memo: Memo,
    replace: bool = False,
    *,
    known_parts: Sequence[str],
    problems: Sequence[MemoProblem],
) -> Status:
    """Replace the status's modules with the memo's, in build order.

    Refused when the memo has `problems` (every one listed with its line), or when a module
    is already past pending and `replace` is false. With `replace`, a module still in the
    memo keeps the progress of its unchanged units (see `_carry_over`); modules no longer in
    the memo are dropped.
    """
    if problems:
        listed = "; ".join(f"line {p.line}: {p.message}" for p in problems)
        raise StatusError(
            f"the memo has problems: {listed}",
            "fix the memo, then run `bull status init-modules` again",
        )
    started = [m.name for m in status.modules if _started(m)]
    if started and not replace:
        raise StatusError(
            f"modules already started: {', '.join(started)}",
            "run `bull status init-modules --replace` to start them over",
        )
    adopting = status.adoption is not None
    old = {m.name: m for m in status.modules}
    built = tuple(
        _carry_over(old.get(e.name), _build(e, known_parts, adopting))
        for e in _in_build_order(memo)
    )
    return _replace_modules(status, built)


def _carry_over(old: ModuleStatus | None, new: ModuleStatus) -> ModuleStatus:
    """`new` (freshly built, all pending) with `old`'s progress where it still applies.

    A unit is kept (state and attempts) when `old` has a unit with the same number, kind and
    files. The module keeps `old`'s state (and scan record) when every unit was kept and none
    was dropped; otherwise it is `in_progress` if any kept unit is past pending, else pending.
    """
    if old is None:
        return new
    previous = {(u.number, u.kind, u.files): u for u in old.units}
    units: list[Unit] = []
    kept = 0
    for unit in new.units:
        match = previous.get((unit.number, unit.kind, unit.files))
        if match is None:
            units.append(unit)
        else:
            units.append(replace(unit, state=match.state, attempts=match.attempts))
            kept += 1
    if kept == len(new.units) == len(old.units):
        return replace(new, state=old.state, units=tuple(units), scan=old.scan)
    started = any(u.state != UnitState.PENDING for u in units)
    state = ModuleState.IN_PROGRESS if started else ModuleState.PENDING
    return replace(new, state=state, units=tuple(units))


def _replace_modules(status: Status, modules: tuple[ModuleStatus, ...]) -> Status:
    # `replace` the function is shadowed by the parameter in `init_modules`.
    return replace(status, modules=modules)


def set_module(status: Status, name: str, state: ModuleState) -> Status:
    """Set a module's state: in_progress needs every dependency done; done needs every
    unit done. Unknown names are refused with a suggestion or the list of modules."""
    module = find_module(status, name)
    if state == ModuleState.IN_PROGRESS:
        done = {m.name for m in status.modules if m.state == ModuleState.DONE}
        waiting = [d for d in module.depends if d not in done]
        if waiting:
            raise StatusError(
                f"{name} depends on modules not done yet: {', '.join(waiting)}",
                "finish those modules first",
            )
    if state == ModuleState.DONE:
        unfinished = [str(u.number) for u in module.units if u.state != UnitState.DONE]
        if unfinished:
            raise StatusError(
                f"{name} has units not done: {', '.join(unfinished)}",
                "finish every unit before marking the module done",
            )
    return put_module(status, replace(module, state=state))


def reopen(status: Status, module: str, files: Sequence[str]) -> Status:
    """Reset the units holding any of `files` to pending (attempt 1) and the module to
    pending; refused when no unit holds any of them."""
    found = find_module(status, module)
    wanted = set(files)
    if not any(wanted.intersection(u.files) for u in found.units):
        raise StatusError(
            f"no unit of {module} holds {', '.join(files) or 'those files'}",
            "check the module's `Changes` line against its `Files` line in the memo",
        )
    units = tuple(
        replace(u, state=UnitState.PENDING, attempts=1)
        if wanted.intersection(u.files)
        else u
        for u in found.units
    )
    return put_module(status, replace(found, state=ModuleState.PENDING, units=units))


def add_modules(
    status: Status, entries: Sequence[ModuleEntry], *, known_parts: Sequence[str]
) -> Status:
    """Append new modules built from memo entries; a name already present is refused."""
    existing = {m.name for m in status.modules}
    clashes = [e.name for e in entries if e.name in existing]
    if clashes:
        raise StatusError(
            f"modules already exist: {', '.join(clashes)}",
            "use reopen for existing modules",
        )
    adopting = status.adoption is not None
    added = tuple(_build(e, known_parts, adopting) for e in entries)
    return replace(status, modules=(*status.modules, *added))
