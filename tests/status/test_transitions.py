"""Tests for `bull.Modules.status.transitions`: stage, checkpoint, unit and attempt rules."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from bull.Modules.status import transitions
from bull.Modules.status.Contracts import (
    ActiveFeature,
    Approval,
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
    UnitKind,
    UnitState,
    Waiting,
)
from bull.Modules.status.mocks import SAMPLE_TIME, sample_status

NOW = datetime(2026, 11, 8, 9, 30, 0, tzinfo=UTC)
APP_CPS = ("outline-approved", "setup", "skeleton", "ui-approved")
EMPTY = Status(1, Track(0, ()), (), None, None, (), None, None, None)


def reason(error: pytest.ExceptionInfo[StatusError]) -> str:
    return f"{error.value.message} {error.value.fix}"


def unit(
    number: int,
    state: UnitState = UnitState.PENDING,
    attempts: int = 1,
    kind: UnitKind = UnitKind.CODE,
) -> Unit:
    return Unit(number, (f"f{number}.py",), kind, state, attempts)


def module(
    name: str,
    state: ModuleState = ModuleState.PENDING,
    units: tuple[Unit, ...] = (),
    reference_tests: bool = False,
) -> ModuleStatus:
    return ModuleStatus(name, "app", (), state, units, reference_tests, None)


def at(
    stage: int,
    checkpoints: tuple[str, ...] = (),
    modules: tuple[ModuleStatus, ...] = (),
    **extra: object,
) -> Status:
    return replace(EMPTY, app=Track(stage, checkpoints), modules=modules, **extra)  # type: ignore[arg-type]


def with_unit(state: UnitState, attempts: int = 1) -> Status:
    """A status whose `Counter` unit 1 is in `state` with `attempts`."""
    return at(
        5,
        APP_CPS,
        (
            module(
                "Counter", ModuleState.IN_PROGRESS, (unit(1, state, attempts), unit(2))
            ),
        ),
    )


def unit_of(status: Status, name: str = "Counter", number: int = 1) -> Unit:
    mod = next(m for m in status.modules if m.name == name)
    return next(u for u in mod.units if u.number == number)


# --- set_stage ---------------------------------------------------------------------------


@pytest.mark.parametrize("stage", [-1, 7, 100])
def test_set_stage_refuses_a_stage_outside_0_to_6(stage: int) -> None:
    with pytest.raises(StatusError):
        transitions.set_stage(at(2, APP_CPS), stage)


@pytest.mark.parametrize("stage", [0, 1, 2])
def test_set_stage_moves_to_early_stages_without_checkpoints(stage: int) -> None:
    assert transitions.set_stage(at(1), stage).app.stage == stage


def test_set_stage_keeps_the_rest_of_the_status() -> None:
    new = transitions.set_stage(sample_status(), 4)
    assert new.app.checkpoints == sample_status().app.checkpoints
    assert new.modules == sample_status().modules


@pytest.mark.parametrize(
    ("checkpoints", "missing"),
    [
        ((), "outline-approved"),
        (("setup",), "outline-approved"),
        (("outline-approved",), "setup"),
    ],
)
def test_set_stage_3_needs_outline_approved_and_setup(
    checkpoints: tuple[str, ...], missing: str
) -> None:
    with pytest.raises(StatusError) as caught:
        transitions.set_stage(at(2, checkpoints), 3)
    assert missing in reason(caught)


def test_set_stage_3_allowed_with_outline_approved_and_setup() -> None:
    new = transitions.set_stage(at(2, ("outline-approved", "setup")), 3)
    assert new.app.stage == 3


def test_set_stage_4_needs_skeleton() -> None:
    cps = ("outline-approved", "setup")
    with pytest.raises(StatusError) as caught:
        transitions.set_stage(at(3, cps), 4)
    assert "skeleton" in reason(caught)
    assert transitions.set_stage(at(3, (*cps, "skeleton")), 4).app.stage == 4


def test_set_stage_5_needs_ui_approved() -> None:
    cps = ("outline-approved", "setup", "skeleton")
    with pytest.raises(StatusError) as caught:
        transitions.set_stage(at(4, cps), 5)
    assert "ui-approved" in reason(caught)
    assert transitions.set_stage(at(4, (*cps, "ui-approved")), 5).app.stage == 5


def test_set_stage_6_refused_while_a_module_is_not_done() -> None:
    mods = (
        module("Store", ModuleState.DONE),
        module("Counter", ModuleState.IN_PROGRESS),
    )
    with pytest.raises(StatusError) as caught:
        transitions.set_stage(at(5, APP_CPS, mods), 6)
    assert "Counter" in reason(caught)


def test_set_stage_6_allowed_when_every_module_is_done() -> None:
    mods = (module("Store", ModuleState.DONE), module("Counter", ModuleState.DONE))
    assert transitions.set_stage(at(5, APP_CPS, mods), 6).app.stage == 6


def test_set_stage_back_is_allowed_without_checkpoints() -> None:
    assert transitions.set_stage(at(5, ()), 2).app.stage == 2


def test_set_stage_in_feature_mode_changes_only_the_feature_track() -> None:
    feature = ActiveFeature("dark-mode", Track(1, ()), ())
    base = at(6, (*APP_CPS, "app-accepted"), feature=feature)
    new = transitions.set_stage(base, 2)
    assert new.feature is not None
    assert new.feature.track.stage == 2
    assert new.app == base.app


def test_set_stage_in_feature_mode_checks_the_feature_checkpoints() -> None:
    feature = ActiveFeature("dark-mode", Track(2, ("outline-approved",)), ())
    base = at(6, (*APP_CPS, "app-accepted"), feature=feature)
    with pytest.raises(StatusError) as caught:
        transitions.set_stage(base, 3)
    assert "setup" in reason(caught)


def test_set_stage_in_adopt_mode_changes_only_the_adoption_track() -> None:
    base = at(0, adoption=Track(1, ()))
    new = transitions.set_stage(base, 2)
    assert new.adoption == Track(2, ())
    assert new.app == base.app


@pytest.mark.parametrize(
    ("stage", "have", "need"),
    [
        (3, ("outline-approved",), "setup"),
        (4, ("outline-approved", "setup"), "baseline"),
        (5, ("outline-approved", "setup", "baseline"), "scaffold"),
    ],
)
def test_set_stage_in_adopt_mode_needs_the_adopt_checkpoints(
    stage: int, have: tuple[str, ...], need: str
) -> None:
    base = at(0, adoption=Track(stage - 1, have))
    with pytest.raises(StatusError) as caught:
        transitions.set_stage(base, stage)
    assert need in reason(caught)
    ok = replace(base, adoption=Track(stage - 1, (*have, need)))
    assert transitions.set_stage(ok, stage).adoption == Track(stage, (*have, need))


def test_set_stage_in_adopt_mode_ignores_the_app_skeleton_checkpoint() -> None:
    base = at(0, APP_CPS, adoption=Track(3, ("outline-approved", "setup")))
    with pytest.raises(StatusError):
        transitions.set_stage(base, 4)


def test_set_stage_6_in_adopt_mode_needs_every_module_done() -> None:
    cps = ("outline-approved", "setup", "baseline", "scaffold")
    mods = (module("Store", ModuleState.PENDING),)
    with pytest.raises(StatusError):
        transitions.set_stage(at(0, modules=mods, adoption=Track(5, cps)), 6)
    done = (module("Store", ModuleState.DONE),)
    new = transitions.set_stage(at(0, modules=done, adoption=Track(5, cps)), 6)
    assert new.adoption == Track(6, cps)


# --- checkpoint --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name", ["outline-approved", "setup", "skeleton", "ui-approved"]
)
def test_checkpoint_records_an_app_checkpoint(name: str) -> None:
    new = transitions.checkpoint(at(2), name)
    assert new.app.checkpoints == (name,)


def test_checkpoint_appends_after_existing_checkpoints() -> None:
    new = transitions.checkpoint(at(2, ("outline-approved",)), "setup")
    assert new.app.checkpoints == ("outline-approved", "setup")


@pytest.mark.parametrize(
    "name", ["bogus", "", "accepted", "adopted", "baseline", "scaffold"]
)
def test_checkpoint_refuses_a_name_outside_the_app_list(name: str) -> None:
    with pytest.raises(StatusError):
        transitions.checkpoint(at(6), name)


def test_checkpoint_app_accepted_needs_stage_6() -> None:
    with pytest.raises(StatusError):
        transitions.checkpoint(at(5, APP_CPS), "app-accepted")
    new = transitions.checkpoint(at(6, APP_CPS), "app-accepted")
    assert "app-accepted" in new.app.checkpoints


def test_checkpoint_twice_is_a_no_op() -> None:
    once = transitions.checkpoint(at(2), "setup")
    assert transitions.checkpoint(once, "setup") == once


def test_checkpoint_app_accepted_twice_is_a_no_op() -> None:
    once = transitions.checkpoint(at(6, APP_CPS), "app-accepted")
    assert transitions.checkpoint(once, "app-accepted") == once


def test_checkpoint_in_feature_mode_goes_on_the_feature_track() -> None:
    feature = ActiveFeature("dark-mode", Track(2, ()), ())
    base = at(6, APP_CPS, feature=feature)
    new = transitions.checkpoint(base, "outline-approved")
    assert new.feature is not None
    assert new.feature.track.checkpoints == ("outline-approved",)
    assert new.app == base.app


def test_checkpoint_feature_accepted_needs_feature_stage_6() -> None:
    low = at(6, APP_CPS, feature=ActiveFeature("dark-mode", Track(5, ()), ()))
    with pytest.raises(StatusError):
        transitions.checkpoint(low, "accepted")
    high = at(6, APP_CPS, feature=ActiveFeature("dark-mode", Track(6, ()), ()))
    new = transitions.checkpoint(high, "accepted")
    assert new.feature is not None
    assert "accepted" in new.feature.track.checkpoints


def test_checkpoint_in_feature_mode_refuses_adopt_names() -> None:
    base = at(6, APP_CPS, feature=ActiveFeature("dark-mode", Track(6, ()), ()))
    with pytest.raises(StatusError):
        transitions.checkpoint(base, "adopted")


@pytest.mark.parametrize("name", ["outline-approved", "setup", "baseline", "scaffold"])
def test_checkpoint_in_adopt_mode_records_adopt_names(name: str) -> None:
    new = transitions.checkpoint(at(0, adoption=Track(2, ())), name)
    assert new.adoption == Track(2, (name,))


@pytest.mark.parametrize(
    "name", ["skeleton", "ui-approved", "app-accepted", "accepted"]
)
def test_checkpoint_in_adopt_mode_refuses_names_outside_its_list(name: str) -> None:
    with pytest.raises(StatusError):
        transitions.checkpoint(at(0, adoption=Track(6, ())), name)


def test_checkpoint_adopted_needs_adoption_stage_6() -> None:
    with pytest.raises(StatusError):
        transitions.checkpoint(at(0, adoption=Track(5, ())), "adopted")
    new = transitions.checkpoint(at(0, adoption=Track(6, ())), "adopted")
    assert new.adoption == Track(6, ("adopted",))


# --- set_unit ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (UnitState.PENDING, UnitState.TESTS),
        (UnitState.TESTS, UnitState.CODE),
        (UnitState.CODE, UnitState.DONE),
        (UnitState.CODE, UnitState.TESTS),
    ],
)
def test_set_unit_allows_the_forward_order_and_code_back_to_tests(
    before: UnitState, after: UnitState
) -> None:
    new = transitions.set_unit(with_unit(before), "Counter", 1, after)
    assert unit_of(new).state == after


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (UnitState.PENDING, UnitState.CODE),
        (UnitState.PENDING, UnitState.DONE),
        (UnitState.TESTS, UnitState.DONE),
    ],
)
def test_set_unit_refuses_skipping_a_state(before: UnitState, after: UnitState) -> None:
    with pytest.raises(StatusError):
        transitions.set_unit(with_unit(before), "Counter", 1, after)


@pytest.mark.parametrize("after", [UnitState.TESTS, UnitState.CODE, UnitState.DONE])
def test_set_unit_refuses_any_change_of_a_blocked_unit(after: UnitState) -> None:
    with pytest.raises(StatusError) as caught:
        transitions.set_unit(with_unit(UnitState.BLOCKED), "Counter", 1, after)
    assert "blocked" in reason(caught)


def test_set_unit_changes_only_the_named_unit() -> None:
    base = with_unit(UnitState.PENDING)
    new = transitions.set_unit(base, "Counter", 1, UnitState.TESTS)
    assert unit_of(new, number=2) == unit_of(base, number=2)
    assert unit_of(new).attempts == 1


def test_set_unit_refuses_an_unknown_module() -> None:
    with pytest.raises(StatusError):
        transitions.set_unit(with_unit(UnitState.PENDING), "Nope", 1, UnitState.TESTS)


def test_set_unit_refuses_an_unknown_unit_number() -> None:
    with pytest.raises(StatusError):
        transitions.set_unit(
            with_unit(UnitState.PENDING), "Counter", 9, UnitState.TESTS
        )


# --- attempt / unblock -------------------------------------------------------------------


def test_attempt_adds_one_and_returns_the_unit_back_at_tests() -> None:
    new, changed = transitions.attempt(
        with_unit(UnitState.CODE, 1), "Counter", 1, max_attempts=3
    )
    assert changed.attempts == 2
    assert changed.state == UnitState.TESTS
    assert unit_of(new) == changed


def test_attempt_allows_reaching_the_limit() -> None:
    new, changed = transitions.attempt(
        with_unit(UnitState.CODE, 2), "Counter", 1, max_attempts=3
    )
    assert changed.attempts == 3
    assert changed.state == UnitState.TESTS
    assert unit_of(new).state == UnitState.TESTS


def test_attempt_at_the_limit_blocks_the_unit_in_the_returned_status() -> None:
    new, changed = transitions.attempt(
        with_unit(UnitState.CODE, 3), "Counter", 1, max_attempts=3
    )
    assert changed.state == UnitState.BLOCKED
    assert unit_of(new).state == UnitState.BLOCKED
    assert unit_of(new).attempts == 3


def test_attempt_respects_a_lower_max_attempts() -> None:
    _, changed = transitions.attempt(
        with_unit(UnitState.CODE, 1), "Counter", 1, max_attempts=1
    )
    assert changed.state == UnitState.BLOCKED


def test_attempt_leaves_other_units_alone() -> None:
    base = with_unit(UnitState.CODE, 1)
    new, _ = transitions.attempt(base, "Counter", 1, max_attempts=3)
    assert unit_of(new, number=2) == unit_of(base, number=2)


def test_attempt_refuses_an_unknown_module() -> None:
    with pytest.raises(StatusError):
        transitions.attempt(with_unit(UnitState.CODE), "Nope", 1, max_attempts=3)


def test_unblock_returns_the_unit_to_tests_with_one_attempt() -> None:
    new = transitions.unblock(with_unit(UnitState.BLOCKED, 3), "Counter", 1)
    assert unit_of(new).state == UnitState.TESTS
    assert unit_of(new).attempts == 1


# --- pause / resume ----------------------------------------------------------------------


def test_pause_records_reason_time_and_the_unit_in_progress() -> None:
    new = transitions.pause(sample_status(), "usage limit", now=NOW)
    assert new.pause == Pause("usage limit", NOW, "Counter unit 1")


def test_pause_names_the_first_unfinished_unit() -> None:
    base = transitions.set_unit(sample_status(), "Counter", 1, UnitState.CODE)
    base = transitions.set_unit(base, "Counter", 1, UnitState.DONE)
    assert transitions.pause(base, "usage", now=NOW).pause == Pause(
        "usage", NOW, "Counter unit 2"
    )


def test_pause_without_a_module_in_progress_has_no_unit() -> None:
    new = transitions.pause(at(2), "usage", now=NOW)
    assert new.pause == Pause("usage", NOW, None)


def test_resume_clears_the_pause() -> None:
    paused = replace(sample_status(), pause=Pause("usage", SAMPLE_TIME, None))
    assert transitions.resume(paused).pause is None


def test_resume_when_not_paused_changes_nothing() -> None:
    assert transitions.resume(sample_status()) == sample_status()


# --- wait / approve / take_approval ------------------------------------------------------


def test_wait_records_module_what_and_time() -> None:
    new = transitions.wait(sample_status(), "Store", "contract change", now=NOW)
    assert new.waiting == Waiting("Store", "contract change", NOW)


def test_approve_clears_a_matching_wait_and_appends_an_approval() -> None:
    base = replace(
        sample_status(), waiting=Waiting("Store", "contract change", SAMPLE_TIME)
    )
    new = transitions.approve(base, "Store", "fine", now=NOW)
    assert new.waiting is None
    assert new.approvals == (Approval("Store", "fine", NOW),)


def test_approve_keeps_a_wait_for_another_module() -> None:
    wait = Waiting("Counter", "contract change", SAMPLE_TIME)
    new = transitions.approve(
        replace(sample_status(), waiting=wait), "Store", "fine", now=NOW
    )
    assert new.waiting == wait
    assert new.approvals == (Approval("Store", "fine", NOW),)


def test_approve_appends_after_earlier_approvals() -> None:
    first = Approval("Store", "one", SAMPLE_TIME)
    new = transitions.approve(
        replace(sample_status(), approvals=(first,)), "Store", "two", now=NOW
    )
    assert new.approvals == (first, Approval("Store", "two", NOW))


def test_take_approval_returns_the_oldest_for_the_module_and_removes_it() -> None:
    old = Approval("Store", "old", SAMPLE_TIME)
    other = Approval("Counter", "other", SAMPLE_TIME)
    newer = Approval("Store", "newer", NOW)
    base = replace(sample_status(), approvals=(old, other, newer))
    new, taken = transitions.take_approval(base, "Store")
    assert taken == old
    assert new.approvals == (other, newer)


def test_take_approval_with_none_returns_none_and_the_same_status() -> None:
    base = replace(sample_status(), approvals=(Approval("Counter", "x", SAMPLE_TIME),))
    new, taken = transitions.take_approval(base, "Store")
    assert taken is None
    assert new == base


# --- record_scan -------------------------------------------------------------------------


def scanned_base() -> Status:
    return at(
        5, APP_CPS, (module("Counter", ModuleState.IN_PROGRESS, (unit(1),), True),)
    )


def test_record_scan_stores_the_counts_and_time() -> None:
    new = transitions.record_scan(scanned_base(), "Counter", 4, 3, 2, 1, now=NOW)
    assert new.modules[0].scan == ScanRecord(NOW, 4, 3, 2, 1)


def test_record_scan_accepts_zero_counts() -> None:
    new = transitions.record_scan(scanned_base(), "Counter", 0, 0, 0, 0, now=NOW)
    assert new.modules[0].scan == ScanRecord(NOW, 0, 0, 0, 0)


def test_record_scan_refuses_a_module_without_reference_tests() -> None:
    with pytest.raises(StatusError):
        transitions.record_scan(sample_status(), "Counter", 1, 0, 0, 0, now=NOW)


@pytest.mark.parametrize(
    "counts", [(-1, 0, 0, 0), (0, -1, 0, 0), (0, 0, -1, 0), (0, 0, 0, -1)]
)
def test_record_scan_refuses_a_negative_count(
    counts: tuple[int, int, int, int],
) -> None:
    with pytest.raises(StatusError):
        transitions.record_scan(scanned_base(), "Counter", *counts, now=NOW)


def test_record_scan_refuses_an_unknown_module() -> None:
    with pytest.raises(StatusError):
        transitions.record_scan(scanned_base(), "Nope", 1, 0, 0, 0, now=NOW)


# --- plan --------------------------------------------------------------------------------


def test_set_plan_lists_every_item_not_done() -> None:
    new = transitions.set_plan(sample_status(), "verify", ["a", "b"])
    assert new.plan == Plan("verify", (PlanItem("a", False), PlanItem("b", False)))


def test_set_plan_replaces_an_existing_plan() -> None:
    first = transitions.set_plan(sample_status(), "one", ["a"])
    assert transitions.set_plan(first, "two", ["b"]).plan == Plan(
        "two", (PlanItem("b", False),)
    )


def test_tick_marks_only_that_item_done() -> None:
    base = transitions.set_plan(sample_status(), "verify", ["a", "b"])
    new = transitions.tick(base, "b")
    assert new.plan == Plan("verify", (PlanItem("a", False), PlanItem("b", True)))


def test_tick_of_an_unknown_item_is_refused() -> None:
    base = transitions.set_plan(sample_status(), "verify", ["a"])
    with pytest.raises(StatusError) as caught:
        transitions.tick(base, "zzz")
    assert "zzz" in reason(caught)


def test_tick_without_a_plan_is_refused() -> None:
    with pytest.raises(StatusError):
        transitions.tick(sample_status(), "a")


def test_clear_plan_removes_the_plan() -> None:
    base = transitions.set_plan(sample_status(), "verify", ["a"])
    assert transitions.clear_plan(base).plan is None


# --- features ----------------------------------------------------------------------------


ACCEPTED = at(6, (*APP_CPS, "app-accepted"))


def test_start_feature_begins_the_feature_track_at_stage_1() -> None:
    new = transitions.start_feature(ACCEPTED, "dark-mode")
    assert new.feature == ActiveFeature("dark-mode", Track(1, ()), ())


def test_start_feature_refused_before_app_accepted() -> None:
    with pytest.raises(StatusError) as caught:
        transitions.start_feature(at(6, APP_CPS), "dark-mode")
    assert "app-accepted" in reason(caught)


def test_start_feature_refused_during_an_adoption() -> None:
    with pytest.raises(StatusError):
        transitions.start_feature(replace(ACCEPTED, adoption=Track(1, ())), "dark-mode")


def test_start_feature_refused_while_another_is_active() -> None:
    active = replace(ACCEPTED, feature=ActiveFeature("one", Track(2, ()), ()))
    with pytest.raises(StatusError) as caught:
        transitions.start_feature(active, "two")
    assert "one" in reason(caught)


def test_end_feature_clears_the_active_feature() -> None:
    active = replace(ACCEPTED, feature=ActiveFeature("one", Track(2, ()), ()))
    assert transitions.end_feature(active).feature is None


def test_mark_contract_applied_records_the_module() -> None:
    active = replace(ACCEPTED, feature=ActiveFeature("one", Track(3, ()), ()))
    new = transitions.mark_contract_applied(active, "Store")
    assert new.feature is not None
    assert new.feature.applied_contracts == ("Store",)


def test_mark_contract_applied_keeps_earlier_modules() -> None:
    active = replace(ACCEPTED, feature=ActiveFeature("one", Track(3, ()), ("Store",)))
    new = transitions.mark_contract_applied(active, "Counter")
    assert new.feature is not None
    assert new.feature.applied_contracts == ("Store", "Counter")


# --- adoption ----------------------------------------------------------------------------


def test_start_adoption_begins_the_adoption_track_at_stage_1() -> None:
    assert transitions.start_adoption(EMPTY).adoption == Track(1, ())


def test_start_adoption_refused_when_modules_exist() -> None:
    with pytest.raises(StatusError):
        transitions.start_adoption(at(0, modules=(module("Store"),)))


def test_start_adoption_refused_when_the_app_track_is_past_stage_0() -> None:
    with pytest.raises(StatusError):
        transitions.start_adoption(at(1))


def test_finish_adoption_needs_adoption_stage_6() -> None:
    with pytest.raises(StatusError):
        transitions.finish_adoption(at(0, adoption=Track(5, ())))


def test_finish_adoption_without_an_adoption_is_refused() -> None:
    with pytest.raises(StatusError):
        transitions.finish_adoption(EMPTY)


def test_finish_adoption_records_app_accepted_at_stage_6_and_clears_the_adoption() -> (
    None
):
    base = at(
        0, adoption=Track(6, ("outline-approved", "setup", "baseline", "scaffold"))
    )
    new = transitions.finish_adoption(base)
    assert new.adoption is None
    assert new.app.stage == 6
    assert "app-accepted" in new.app.checkpoints


def test_abandon_adoption_clears_the_adoption() -> None:
    new = transitions.abandon_adoption(at(0, adoption=Track(3, ("setup",))))
    assert new.adoption is None
    assert new.app.stage == 0
