"""Tests for `bull.Modules.status.modules`: init, set, reopen and add modules."""

from __future__ import annotations

from dataclasses import replace

import pytest

from bull.Modules.memo.Contracts import BuildEntry, Memo, MemoProblem, ModuleEntry
from bull.Modules.memo.mocks import sample_memo
from bull.Modules.status import modules
from bull.Modules.status.Contracts import (
    ModuleState,
    ModuleStatus,
    Status,
    StatusError,
    Track,
    Unit,
    UnitKind,
    UnitState,
)
from bull.Modules.status.mocks import sample_status

EMPTY = Status(1, Track(0, ()), (), None, None, (), None, None, None)
PARTS = ("app",)


def reason(error: pytest.ExceptionInfo[StatusError]) -> str:
    return f"{error.value.message} {error.value.fix}"


def entry(
    name: str,
    units: tuple[tuple[str, ...], ...] = (("a.py",),),
    depends: tuple[str, ...] = (),
    part: str | None = None,
    legacy_files: tuple[str, ...] = (),
    reference_tests: tuple[str, ...] = (),
) -> ModuleEntry:
    return ModuleEntry(
        name=name,
        line=10,
        part=part,
        depends=depends,
        units=units,
        legacy_files=legacy_files,
        legacy_tests=(),
        callers=(),
        reference_tests=reference_tests,
        changes={},
        contract_changes={},
    )


def memo_of(*entries: ModuleEntry, parts: tuple[str, ...] = ()) -> Memo:
    return replace(
        sample_memo(),
        modules=entries,
        build_order=tuple(BuildEntry(e.name, e.depends, 1) for e in entries),
        parts=parts,
    )


def init(
    memo: Memo,
    status: Status = EMPTY,
    replace_existing: bool = False,
    known_parts: tuple[str, ...] = PARTS,
    problems: tuple[MemoProblem, ...] = (),
) -> Status:
    return modules.init_modules(
        status, memo, replace_existing, known_parts=known_parts, problems=problems
    )


def by_name(status: Status, name: str) -> ModuleStatus:
    return next(m for m in status.modules if m.name == name)


# --- init_modules ------------------------------------------------------------------------


def test_init_modules_refuses_listing_every_problem_with_its_line() -> None:
    problems = (MemoProblem(12, "Store has no Files line"), MemoProblem(40, "cycle"))
    with pytest.raises(StatusError) as caught:
        init(sample_memo(), problems=problems)
    text = reason(caught)
    for problem in problems:
        assert problem.message in text
        assert str(problem.line) in text


def test_init_modules_on_problems_does_not_return_modules() -> None:
    with pytest.raises(StatusError):
        init(sample_memo(), problems=(MemoProblem(1, "bad"),))


def test_init_modules_follows_the_build_order_not_the_module_order() -> None:
    store = entry("Store")
    counter = entry("Counter", depends=("Store",))
    memo = replace(
        memo_of(counter, store),
        build_order=(BuildEntry("Store", (), 1), BuildEntry("Counter", ("Store",), 2)),
    )
    assert [m.name for m in init(memo).modules] == ["Store", "Counter"]


def test_init_modules_copies_depends() -> None:
    status = init(sample_memo())
    assert by_name(status, "Counter").depends == ("Store",)
    assert by_name(status, "Store").depends == ()


def test_init_modules_makes_modules_pending_without_a_scan() -> None:
    status = init(sample_memo())
    assert all(
        m.state == ModuleState.PENDING and m.scan is None for m in status.modules
    )


def test_init_modules_uses_the_only_part_when_the_memo_has_none() -> None:
    status = init(sample_memo(), known_parts=("app",))
    assert {m.part for m in status.modules} == {"app"}


def test_init_modules_keeps_the_part_the_memo_names() -> None:
    memo = memo_of(entry("Store", part="core"), parts=("core", "web"))
    status = init(memo, known_parts=("core", "web"))
    assert by_name(status, "Store").part == "core"


def test_init_modules_makes_one_unit_per_files_group() -> None:
    status = init(sample_memo())
    counter = by_name(status, "Counter")
    assert [(u.number, u.files) for u in counter.units] == [
        (1, ("Contracts/counter.fx", "counter.fx")),
        (2, ("cli.fx",)),
    ]
    assert all(u.kind == UnitKind.CODE for u in counter.units)


def test_init_modules_units_start_pending_with_one_attempt() -> None:
    status = init(sample_memo())
    units = [u for m in status.modules for u in m.units]
    assert units
    assert all(u.state == UnitState.PENDING and u.attempts == 1 for u in units)


def test_init_modules_reference_tests_true_when_the_memo_line_is_non_empty() -> None:
    memo = memo_of(
        entry("Store", reference_tests=("v1/test_store.py",)), entry("Counter")
    )
    status = init(memo)
    assert by_name(status, "Store").reference_tests is True
    assert by_name(status, "Counter").reference_tests is False


def test_init_modules_adds_a_switch_over_unit_when_adopting_a_legacy_module() -> None:
    memo = memo_of(
        entry("Store", units=(("a.py",), ("b.py",)), legacy_files=("old/store.py",)),
        entry("Counter"),
    )
    status = init(memo, replace(EMPTY, adoption=Track(2, ())))
    store = by_name(status, "Store")
    assert [u.number for u in store.units] == [1, 2, 3]
    last = store.units[-1]
    assert last.kind == UnitKind.SWITCH_OVER
    assert last.files == ()
    assert last.state == UnitState.PENDING
    assert last.attempts == 1
    assert [u.kind for u in store.units[:2]] == [UnitKind.CODE, UnitKind.CODE]


def test_init_modules_adds_no_switch_over_to_a_module_without_legacy_files() -> None:
    memo = memo_of(entry("Store"), entry("Counter"))
    status = init(memo, replace(EMPTY, adoption=Track(2, ())))
    assert all(u.kind == UnitKind.CODE for m in status.modules for u in m.units)


def test_init_modules_adds_no_switch_over_outside_an_adoption() -> None:
    memo = memo_of(entry("Store", legacy_files=("old/store.py",)))
    status = init(memo)
    assert [u.kind for u in by_name(status, "Store").units] == [UnitKind.CODE]


def test_init_modules_refuses_when_a_module_is_past_pending_without_replace() -> None:
    with pytest.raises(StatusError):
        init(sample_memo(), sample_status())


def test_init_modules_refuses_when_a_module_is_done_without_replace() -> None:
    base = at_modules((module_in("Store", ModuleState.DONE),))
    with pytest.raises(StatusError):
        init(sample_memo(), base)


def test_init_modules_replaces_started_modules_with_replace() -> None:
    status = init(sample_memo(), sample_status(), replace_existing=True)
    assert [m.name for m in status.modules] == ["Store", "Counter"]
    assert all(m.state == ModuleState.PENDING for m in status.modules)
    assert all(u.state == UnitState.PENDING for m in status.modules for u in m.units)


def test_init_modules_replaces_pending_modules_without_replace() -> None:
    base = at_modules((module_in("Old", ModuleState.PENDING),))
    status = init(sample_memo(), base)
    assert [m.name for m in status.modules] == ["Store", "Counter"]


def test_init_modules_keeps_the_rest_of_the_status() -> None:
    base = replace(EMPTY, app=Track(2, ("outline-approved",)))
    assert init(sample_memo(), base).app == base.app


# --- helpers for set_module / reopen / add -----------------------------------------------


def unit(
    number: int,
    state: UnitState = UnitState.PENDING,
    files: tuple[str, ...] | None = None,
) -> Unit:
    return Unit(
        number,
        files if files is not None else (f"f{number}.py",),
        UnitKind.CODE,
        state,
        1,
    )


def module_in(
    name: str,
    state: ModuleState = ModuleState.PENDING,
    units: tuple[Unit, ...] = (),
    depends: tuple[str, ...] = (),
) -> ModuleStatus:
    return ModuleStatus(name, "app", depends, state, units, False, None)


def at_modules(mods: tuple[ModuleStatus, ...]) -> Status:
    return replace(EMPTY, app=Track(5, ()), modules=mods)


# --- set_module --------------------------------------------------------------------------


def test_set_module_in_progress_when_dependencies_are_done() -> None:
    base = at_modules(
        (module_in("Store", ModuleState.DONE), module_in("Counter", depends=("Store",)))
    )
    new = modules.set_module(base, "Counter", ModuleState.IN_PROGRESS)
    assert by_name(new, "Counter").state == ModuleState.IN_PROGRESS


def test_set_module_in_progress_refused_naming_unfinished_dependencies() -> None:
    base = at_modules(
        (
            module_in("Store", ModuleState.IN_PROGRESS),
            module_in("Cache"),
            module_in("Counter", depends=("Store", "Cache")),
        )
    )
    with pytest.raises(StatusError) as caught:
        modules.set_module(base, "Counter", ModuleState.IN_PROGRESS)
    assert "Store" in reason(caught)
    assert "Cache" in reason(caught)


def test_set_module_in_progress_ignores_dependencies_that_are_done() -> None:
    base = at_modules(
        (
            module_in("Store", ModuleState.DONE),
            module_in("Cache"),
            module_in("Counter", depends=("Store", "Cache")),
        )
    )
    with pytest.raises(StatusError) as caught:
        modules.set_module(base, "Counter", ModuleState.IN_PROGRESS)
    assert "Cache" in reason(caught)
    assert "Store" not in reason(caught)


def test_set_module_unknown_name_suggests_the_case_insensitive_match() -> None:
    with pytest.raises(StatusError) as caught:
        modules.set_module(sample_status(), "counter", ModuleState.IN_PROGRESS)
    assert "did you mean `Counter`?" in reason(caught)


def test_set_module_unknown_name_without_a_match_lists_the_modules() -> None:
    with pytest.raises(StatusError) as caught:
        modules.set_module(sample_status(), "Nope", ModuleState.IN_PROGRESS)
    text = reason(caught)
    assert "Store" in text
    assert "Counter" in text
    assert "did you mean" not in text


def test_set_module_done_needs_every_unit_done() -> None:
    base = at_modules(
        (
            module_in(
                "Store",
                ModuleState.IN_PROGRESS,
                (unit(1, UnitState.DONE), unit(2, UnitState.CODE)),
            ),
        )
    )
    with pytest.raises(StatusError):
        modules.set_module(base, "Store", ModuleState.DONE)


def test_set_module_done_when_every_unit_is_done() -> None:
    base = at_modules(
        (
            module_in(
                "Store",
                ModuleState.IN_PROGRESS,
                (unit(1, UnitState.DONE), unit(2, UnitState.DONE)),
            ),
        )
    )
    new = modules.set_module(base, "Store", ModuleState.DONE)
    assert by_name(new, "Store").state == ModuleState.DONE


def test_set_module_changes_only_that_module() -> None:
    base = at_modules(
        (module_in("Store", ModuleState.DONE), module_in("Counter", depends=("Store",)))
    )
    new = modules.set_module(base, "Counter", ModuleState.IN_PROGRESS)
    assert by_name(new, "Store") == by_name(base, "Store")


@pytest.mark.parametrize("state", [ModuleState.PENDING, ModuleState.BLOCKED])
def test_set_module_to_pending_or_blocked_is_allowed(state: ModuleState) -> None:
    new = modules.set_module(sample_status(), "Counter", state)
    assert by_name(new, "Counter").state == state


# --- reopen ------------------------------------------------------------------------------


def done_store() -> Status:
    units = (
        Unit(1, ("Contracts/store.py", "store.py"), UnitKind.CODE, UnitState.DONE, 3),
        Unit(2, ("cli.py",), UnitKind.CODE, UnitState.DONE, 2),
    )
    return at_modules((module_in("Store", ModuleState.DONE, units),))


def test_reopen_resets_units_holding_the_files_to_pending_with_one_attempt() -> None:
    new = modules.reopen(done_store(), "Store", ["store.py"])
    first, second = by_name(new, "Store").units
    assert first.state == UnitState.PENDING
    assert first.attempts == 1
    assert second == done_store().modules[0].units[1]


def test_reopen_puts_the_module_back_to_pending() -> None:
    new = modules.reopen(done_store(), "Store", ["cli.py"])
    assert by_name(new, "Store").state == ModuleState.PENDING


def test_reopen_with_files_in_two_units_resets_both() -> None:
    new = modules.reopen(done_store(), "Store", ["store.py", "cli.py"])
    assert all(u.state == UnitState.PENDING for u in by_name(new, "Store").units)


def test_reopen_unknown_module_is_refused() -> None:
    with pytest.raises(StatusError):
        modules.reopen(done_store(), "Nope", ["store.py"])


# --- add_modules -------------------------------------------------------------------------


def test_add_modules_appends_new_modules_after_the_existing_ones() -> None:
    new = modules.add_modules(
        sample_status(), [entry("Cache", depends=("Store",))], known_parts=PARTS
    )
    assert [m.name for m in new.modules] == ["Store", "Counter", "Cache"]
    assert new.modules[:2] == sample_status().modules


def test_add_modules_builds_pending_modules_with_a_unit_per_files_group() -> None:
    new = modules.add_modules(
        sample_status(),
        [entry("Cache", units=(("a.py",), ("b.py", "c.py")), depends=("Store",))],
        known_parts=PARTS,
    )
    cache = by_name(new, "Cache")
    assert cache.state == ModuleState.PENDING
    assert cache.depends == ("Store",)
    assert cache.part == "app"
    assert [(u.number, u.files, u.state, u.attempts) for u in cache.units] == [
        (1, ("a.py",), UnitState.PENDING, 1),
        (2, ("b.py", "c.py"), UnitState.PENDING, 1),
    ]


def test_add_modules_sets_reference_tests_from_the_entry() -> None:
    new = modules.add_modules(
        sample_status(),
        [entry("Cache", reference_tests=("v1/t.py",))],
        known_parts=PARTS,
    )
    assert by_name(new, "Cache").reference_tests is True


def test_add_modules_keeps_a_named_part() -> None:
    new = modules.add_modules(
        sample_status(), [entry("Cache", part="web")], known_parts=("app", "web")
    )
    assert by_name(new, "Cache").part == "web"
