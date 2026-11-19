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


def test_init_modules_refuses_a_memo_with_no_modules() -> None:
    with pytest.raises(StatusError) as caught:
        init(memo_of())
    assert caught.value.message == "docs/outline.md has no modules"
    assert caught.value.fix == "write the memo first"


def test_init_modules_with_replace_refuses_a_memo_with_no_modules() -> None:
    base = at_modules((module_in("Old", ModuleState.PENDING),))
    with pytest.raises(StatusError) as caught:
        init(memo_of(), base, replace_existing=True)
    assert caught.value.message == "docs/outline.md has no modules"
    assert caught.value.fix == "write the memo first"


def test_init_modules_refusing_an_empty_memo_leaves_the_given_status_unchanged() -> (
    None
):
    base = at_modules((module_in("Old", ModuleState.IN_PROGRESS),))
    before = base
    with pytest.raises(StatusError):
        init(memo_of(), base, replace_existing=True)
    assert base == before
    assert [m.name for m in base.modules] == ["Old"]


def test_init_modules_accepts_a_memo_with_a_single_module() -> None:
    status = init(memo_of(entry("Store")))
    assert [m.name for m in status.modules] == ["Store"]


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


def old_unit(
    number: int,
    files: tuple[str, ...],
    state: UnitState,
    attempts: int = 1,
    kind: UnitKind = UnitKind.CODE,
) -> Unit:
    return Unit(number, files, kind, state, attempts)


def replaced(old: tuple[ModuleStatus, ...], memo: Memo) -> Status:
    return init(memo, at_modules(old), replace_existing=True)


def test_init_modules_with_replace_keeps_state_and_attempts_of_unchanged_units() -> (
    None
):
    old = module_in(
        "Store",
        ModuleState.IN_PROGRESS,
        (
            old_unit(1, ("a.py",), UnitState.DONE, attempts=2),
            old_unit(2, ("b.py",), UnitState.CODE, attempts=3),
        ),
    )
    memo = memo_of(entry("Store", units=(("a.py",), ("b.py",))))
    units = by_name(replaced((old,), memo), "Store").units
    assert [(u.number, u.state, u.attempts) for u in units] == [
        (1, UnitState.DONE, 2),
        (2, UnitState.CODE, 3),
    ]


def test_init_modules_with_replace_restarts_a_unit_whose_files_changed() -> None:
    old = module_in(
        "Store",
        ModuleState.IN_PROGRESS,
        (
            old_unit(1, ("a.py",), UnitState.DONE, attempts=2),
            old_unit(2, ("b.py",), UnitState.DONE, attempts=2),
        ),
    )
    memo = memo_of(entry("Store", units=(("a.py",), ("b.py", "c.py"))))
    units = by_name(replaced((old,), memo), "Store").units
    assert (units[0].state, units[0].attempts) == (UnitState.DONE, 2)
    assert units[1].files == ("b.py", "c.py")
    assert (units[1].state, units[1].attempts) == (UnitState.PENDING, 1)


def test_init_modules_with_replace_restarts_a_unit_whose_kind_changed() -> None:
    old = module_in(
        "Store",
        ModuleState.IN_PROGRESS,
        (
            old_unit(1, ("a.py",), UnitState.DONE),
            old_unit(2, (), UnitState.DONE, attempts=2, kind=UnitKind.CODE),
        ),
    )
    memo = memo_of(entry("Store", legacy_files=("old/store.py",)))
    base = replace(at_modules((old,)), adoption=Track(2, ()))
    units = by_name(init(memo, base, replace_existing=True), "Store").units
    assert units[1].kind == UnitKind.SWITCH_OVER
    assert (units[1].state, units[1].attempts) == (UnitState.PENDING, 1)
    assert units[0].state == UnitState.DONE


def test_init_modules_with_replace_restarts_a_unit_whose_number_changed() -> None:
    old = module_in(
        "Store",
        ModuleState.IN_PROGRESS,
        (old_unit(1, ("b.py",), UnitState.DONE, attempts=2),),
    )
    memo = memo_of(entry("Store", units=(("a.py",), ("b.py",))))
    units = by_name(replaced((old,), memo), "Store").units
    assert [(u.state, u.attempts) for u in units] == [
        (UnitState.PENDING, 1),
        (UnitState.PENDING, 1),
    ]


def test_init_modules_with_replace_starts_new_units_pending() -> None:
    old = module_in(
        "Store",
        ModuleState.IN_PROGRESS,
        (old_unit(1, ("a.py",), UnitState.DONE),),
    )
    memo = memo_of(entry("Store", units=(("a.py",), ("b.py",))))
    units = by_name(replaced((old,), memo), "Store").units
    assert len(units) == 2
    assert (units[1].state, units[1].attempts) == (UnitState.PENDING, 1)


def test_init_modules_with_replace_keeps_module_state_when_every_unit_is_kept() -> None:
    old = module_in(
        "Store",
        ModuleState.DONE,
        (old_unit(1, ("a.py",), UnitState.DONE),),
    )
    status = replaced((old,), memo_of(entry("Store")))
    assert by_name(status, "Store").state == ModuleState.DONE


def test_init_modules_with_replace_is_in_progress_when_a_kept_unit_is_past_pending() -> (
    None
):
    old = module_in(
        "Store",
        ModuleState.DONE,
        (
            old_unit(1, ("a.py",), UnitState.DONE),
            old_unit(2, ("b.py",), UnitState.DONE),
        ),
    )
    memo = memo_of(entry("Store", units=(("a.py",), ("changed.py",))))
    assert by_name(replaced((old,), memo), "Store").state == ModuleState.IN_PROGRESS


def test_init_modules_with_replace_is_pending_when_no_unit_is_past_pending() -> None:
    old = module_in(
        "Store",
        ModuleState.IN_PROGRESS,
        (old_unit(1, ("a.py",), UnitState.PENDING),),
    )
    memo = memo_of(entry("Store", units=(("other.py",),)))
    assert by_name(replaced((old,), memo), "Store").state == ModuleState.PENDING


def test_init_modules_with_replace_is_pending_when_only_changed_units_were_started() -> (
    None
):
    old = module_in(
        "Store",
        ModuleState.IN_PROGRESS,
        (old_unit(1, ("a.py",), UnitState.CODE),),
    )
    memo = memo_of(entry("Store", units=(("other.py",),)))
    status = replaced((old,), memo)
    assert by_name(status, "Store").state == ModuleState.PENDING


def test_init_modules_with_replace_drops_modules_no_longer_in_the_memo() -> None:
    gone = module_in(
        "Gone", ModuleState.DONE, (old_unit(1, ("g.py",), UnitState.DONE),)
    )
    status = replaced((gone,), memo_of(entry("Store")))
    assert [m.name for m in status.modules] == ["Store"]


def test_init_modules_with_replace_starts_modules_new_to_the_memo_pending() -> None:
    old = module_in(
        "Store", ModuleState.DONE, (old_unit(1, ("a.py",), UnitState.DONE),)
    )
    memo = memo_of(entry("Store"), entry("Counter", depends=("Store",)))
    status = replaced((old,), memo)
    counter = by_name(status, "Counter")
    assert counter.state == ModuleState.PENDING
    assert all(u.state == UnitState.PENDING and u.attempts == 1 for u in counter.units)
    assert by_name(status, "Store").state == ModuleState.DONE


def test_init_modules_with_replace_follows_the_memo_build_order() -> None:
    old = (
        module_in(
            "Counter", ModuleState.DONE, (old_unit(1, ("a.py",), UnitState.DONE),)
        ),
        module_in("Store", ModuleState.DONE, (old_unit(1, ("a.py",), UnitState.DONE),)),
    )
    memo = memo_of(entry("Store"), entry("Counter", depends=("Store",)))
    assert [m.name for m in replaced(old, memo).modules] == ["Store", "Counter"]


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


# --- coverage triage: guards ---------------------------------------------------------------


def test_add_modules_refuses_a_module_with_no_part_when_the_app_has_no_parts() -> None:
    with pytest.raises(StatusError) as caught:
        modules.add_modules(sample_status(), [entry("Cache")], known_parts=())
    assert "bull part add" in reason(caught)


def test_init_modules_refuses_a_module_with_no_part_when_the_app_has_no_parts() -> None:
    with pytest.raises(StatusError) as caught:
        init(memo_of(entry("Store")), known_parts=())
    assert "bull part add" in reason(caught)


def test_add_modules_refuses_a_name_that_already_exists() -> None:
    with pytest.raises(StatusError) as caught:
        modules.add_modules(sample_status(), [entry("Store")], known_parts=PARTS)
    assert "Store" in reason(caught)


def test_reopen_refuses_when_no_unit_holds_any_of_the_files() -> None:
    with pytest.raises(StatusError):
        modules.reopen(done_store(), "Store", ["nowhere.py"])


def test_reopen_refuses_an_empty_file_list() -> None:
    with pytest.raises(StatusError):
        modules.reopen(done_store(), "Store", [])


def test_reopen_ignores_files_no_unit_holds_when_some_match() -> None:
    new = modules.reopen(done_store(), "Store", ["store.py", "nowhere.py"])
    first, second = by_name(new, "Store").units
    assert first.state == UnitState.PENDING
    assert second == done_store().modules[0].units[1]


def test_init_modules_matches_a_build_order_name_to_its_block_ignoring_case() -> None:
    memo = replace(memo_of(entry("foo")), build_order=(BuildEntry("Foo", (), 1),))
    status = init(memo)
    assert [m.name for m in status.modules] == ["foo"]


def test_init_modules_refuses_a_build_order_name_without_a_block() -> None:
    memo = replace(memo_of(entry("foo")), build_order=(BuildEntry("Bar", (), 7),))
    with pytest.raises(StatusError) as error:
        init(memo, problems=())
    assert "Bar" in reason(error)
    assert "module section" in reason(error)
