"""Tests for `bull.Modules.status.next_step`: the next step by priority and stage."""

from __future__ import annotations

from dataclasses import replace

import pytest

import bull.Modules.status.next_step as next_step_module
from bull.Modules.status.Contracts import (
    ActiveFeature,
    Mode,
    ModuleState,
    ModuleStatus,
    NextStep,
    Pause,
    ScanRecord,
    Status,
    StatusError,
    Track,
    Unit,
    UnitKind,
    UnitState,
    Waiting,
)
from bull.Modules.status.mocks import SAMPLE_TIME, MockRefs

APP_CPS = ("outline-approved", "setup", "skeleton", "ui-approved")
EMPTY = Status(1, Track(0, ()), (), None, None, (), None, None, None)


def unit(
    number: int,
    state: UnitState = UnitState.PENDING,
    kind: UnitKind = UnitKind.CODE,
) -> Unit:
    return Unit(
        number,
        () if kind is UnitKind.SWITCH_OVER else (f"f{number}.py",),
        kind,
        state,
        1,
    )


def module(
    name: str,
    state: ModuleState = ModuleState.PENDING,
    units: tuple[Unit, ...] = (),
    depends: tuple[str, ...] = (),
    reference_tests: bool = False,
    scan: ScanRecord | None = None,
) -> ModuleStatus:
    return ModuleStatus(name, "app", depends, state, units, reference_tests, scan)


def app(
    stage: int,
    mods: tuple[ModuleStatus, ...] = (),
    cps: tuple[str, ...] = APP_CPS,
    **extra: object,
) -> Status:
    return replace(EMPTY, app=Track(stage, cps), modules=mods, **extra)  # type: ignore[arg-type]


def step(status: Status, branch: str | None = None) -> NextStep:
    return next_step_module.next_step(status, Mode.APP, MockRefs(), branch)


def counter_at(state: UnitState) -> Status:
    mods = (
        module("Store", ModuleState.DONE, (unit(1, UnitState.DONE),)),
        module(
            "Counter", ModuleState.IN_PROGRESS, (unit(1, state), unit(2)), ("Store",)
        ),
    )
    return app(5, mods)


# --- priority ----------------------------------------------------------------------------


def test_paused_says_to_resume_with_the_reason() -> None:
    status = app(5, pause=Pause("usage limit", SAMPLE_TIME, None))
    assert step(status).text == "paused (usage limit): run /bull:resume"


def test_paused_wins_over_waiting_and_a_blocked_unit() -> None:
    mods = (module("Store", ModuleState.BLOCKED, (unit(1, UnitState.BLOCKED),)),)
    status = app(
        5,
        mods,
        pause=Pause("usage", SAMPLE_TIME, None),
        waiting=Waiting("Store", "contract", SAMPLE_TIME),
    )
    assert step(status).text.startswith("paused (usage)")


def test_waiting_says_the_human_must_approve_the_contract_change() -> None:
    status = app(5, waiting=Waiting("Store", "contract", SAMPLE_TIME))
    assert (
        step(status).text
        == "waiting for the human to approve the Store contract change"
    )


def test_waiting_wins_over_a_blocked_unit() -> None:
    mods = (module("Counter", ModuleState.BLOCKED, (unit(1, UnitState.BLOCKED),)),)
    status = app(5, mods, waiting=Waiting("Store", "contract", SAMPLE_TIME))
    assert step(status).text.startswith("waiting for the human")


def test_a_blocked_unit_says_to_ask_the_human() -> None:
    mods = (
        module(
            "Counter",
            ModuleState.IN_PROGRESS,
            (unit(1, UnitState.DONE), unit(2, UnitState.BLOCKED)),
        ),
    )
    assert step(app(5, mods)).text == "Counter unit 2 is blocked: ask the human"


def test_a_blocked_unit_wins_over_the_stage() -> None:
    mods = (module("Counter", ModuleState.IN_PROGRESS, (unit(1, UnitState.BLOCKED),)),)
    assert "blocked" in step(app(2, mods, cps=())).text


# --- stages 0 to 4 and 6 -----------------------------------------------------------------


@pytest.mark.parametrize("stage", [0, 1])
def test_stages_0_and_1_say_discuss(stage: int) -> None:
    assert "/bull:discuss" in step(app(stage, cps=())).text


def test_stage_2_says_outline_before_the_outline_is_approved() -> None:
    assert "/bull:outline" in step(app(2, cps=())).text


def test_stage_2_says_setup_after_outline_approved() -> None:
    text = step(app(2, cps=("outline-approved",))).text
    assert "/bull:setup" in text
    assert "/bull:outline" not in text


def test_stage_3_says_skeleton() -> None:
    assert "/bull:skeleton" in step(app(3, cps=("outline-approved", "setup"))).text


def test_stage_4_says_prototype() -> None:
    assert (
        "/bull:prototype"
        in step(app(4, cps=("outline-approved", "setup", "skeleton"))).text
    )


def test_stage_6_says_verify_before_acceptance() -> None:
    assert "/bull:verify" in step(app(6)).text


def test_stage_6_says_feature_after_app_accepted() -> None:
    text = step(app(6, cps=(*APP_CPS, "app-accepted"))).text
    assert "/bull:feature" in text
    assert "/bull:verify" not in text


def test_the_result_carries_the_mode() -> None:
    assert step(app(3)).mode == Mode.APP


# --- stage 5 -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (UnitState.PENDING, "unit 1: test-writer"),
        (UnitState.TESTS, "unit 1: code-writer, then gates --fast"),
        (UnitState.CODE, "unit 1: reviewer"),
    ],
)
def test_stage_5_names_the_agent_for_the_first_unfinished_unit(
    state: UnitState, expected: str
) -> None:
    assert expected in step(counter_at(state)).text


def test_stage_5_skips_done_units() -> None:
    assert "unit 2: test-writer" in step(counter_at(UnitState.DONE)).text


def test_stage_5_names_the_module_in_progress() -> None:
    assert "Counter" in step(counter_at(UnitState.TESTS)).text


def test_stage_5_switch_over_units_say_switch_over() -> None:
    mods = (
        module(
            "Counter",
            ModuleState.IN_PROGRESS,
            (unit(1, UnitState.DONE), unit(2, UnitState.PENDING, UnitKind.SWITCH_OVER)),
        ),
    )
    assert "switch-over" in step(app(5, mods)).text


def test_stage_5_all_units_done_with_reference_tests_and_no_scan_says_scan() -> None:
    mods = (
        module(
            "Counter",
            ModuleState.IN_PROGRESS,
            (unit(1, UnitState.DONE),),
            reference_tests=True,
        ),
    )
    assert "reference-test scan for Counter" in step(app(5, mods)).text


def test_stage_5_all_units_done_after_the_scan_says_triage_and_merge() -> None:
    scan = ScanRecord(SAMPLE_TIME, 1, 0, 0, 0)
    mods = (
        module(
            "Counter",
            ModuleState.IN_PROGRESS,
            (unit(1, UnitState.DONE),),
            reference_tests=True,
            scan=scan,
        ),
    )
    text = step(app(5, mods)).text
    assert "coverage triage, full gates, merge module/Counter into main" in text
    assert "scan" not in text


def test_stage_5_all_units_done_without_reference_tests_says_triage_and_merge() -> None:
    mods = (module("Counter", ModuleState.IN_PROGRESS, (unit(1, UnitState.DONE),)),)
    assert (
        "coverage triage, full gates, merge module/Counter into main"
        in step(app(5, mods)).text
    )


def test_stage_5_no_module_in_progress_starts_the_first_pending_one() -> None:
    mods = (
        module("Store", units=(unit(1),)),
        module("Counter", units=(unit(1),), depends=("Store",)),
    )
    assert "start Store on module/Store" in step(app(5, mods)).text


def test_stage_5_start_skips_a_module_whose_dependencies_are_not_done() -> None:
    mods = (module("Counter", depends=("Store",)), module("Store"))
    assert "start Store on module/Store" in step(app(5, mods)).text


def test_stage_5_start_follows_a_finished_dependency() -> None:
    mods = (module("Store", ModuleState.DONE), module("Counter", depends=("Store",)))
    assert "start Counter on module/Counter" in step(app(5, mods)).text


def test_stage_5_all_modules_done_says_gates_all_then_verify() -> None:
    mods = (module("Store", ModuleState.DONE), module("Counter", ModuleState.DONE))
    text = step(app(5, mods)).text
    assert "bull gates --all" in text
    assert "/bull:verify" in text


# --- the switch-to prefix ----------------------------------------------------------------


def test_no_prefix_on_the_base_branch() -> None:
    assert not step(counter_at(UnitState.TESTS), "main").text.startswith("switch to")


def test_no_prefix_on_the_module_branch_in_progress() -> None:
    assert not step(counter_at(UnitState.TESTS), "module/Counter").text.startswith(
        "switch to"
    )


def test_no_prefix_when_the_branch_is_unknown() -> None:
    assert not step(counter_at(UnitState.TESTS), None).text.startswith("switch to")


def test_prefix_when_on_another_branch_names_the_module_branch() -> None:
    text = step(counter_at(UnitState.TESTS), "module/Store").text
    assert text.startswith("switch to module/Counter, then")
    assert "unit 1: code-writer" in text


def test_prefix_on_the_wrong_branch_with_no_module_in_progress_names_the_base() -> None:
    mods = (module("Store"),)
    text = step(app(5, mods), "module/Other").text
    assert text.startswith("switch to main, then")
    assert "start Store on module/Store" in text


# --- feature and adopt modes -------------------------------------------------------------


def feature_status(stage: int, mods: tuple[ModuleStatus, ...] = ()) -> Status:
    feature = ActiveFeature("dark-mode", Track(stage, ()), ())
    return app(6, mods, cps=(*APP_CPS, "app-accepted"), feature=feature)


def feature_step(status: Status, branch: str | None = None) -> NextStep:
    return next_step_module.next_step(
        status, Mode.FEATURE, MockRefs("feature/dark-mode/"), branch
    )


def adopt_status(stage: int, mods: tuple[ModuleStatus, ...] = ()) -> Status:
    return replace(EMPTY, modules=mods, adoption=Track(stage, ()))


def adopt_step(status: Status, branch: str | None = None) -> NextStep:
    return next_step_module.next_step(status, Mode.ADOPT, MockRefs("adopt/"), branch)


def test_feature_steps_start_with_the_feature_slug() -> None:
    result = feature_step(feature_status(1))
    assert result.text.startswith("feature dark-mode:")
    assert result.mode == Mode.FEATURE


def test_feature_uses_the_feature_command_instead_of_discuss() -> None:
    text = feature_step(feature_status(1)).text
    assert "/bull:feature" in text
    assert "/bull:discuss" not in text


def test_feature_uses_its_own_track_not_the_app_stage() -> None:
    # The app track is at stage 6; the feature track is at stage 1.
    assert "/bull:feature" in feature_step(feature_status(1)).text


def test_feature_stage_5_uses_prefixed_branches() -> None:
    mods = (module("Counter", ModuleState.PENDING, (unit(1),)),)
    text = feature_step(feature_status(5, mods)).text
    assert "start Counter on feature/dark-mode/module/Counter" in text


def test_feature_all_modules_done_uses_the_feature_wording() -> None:
    mods = (module("Counter", ModuleState.DONE),)
    text = feature_step(feature_status(5, mods)).text
    assert text.startswith("feature dark-mode:")
    assert "bull gates --all" in text


def test_feature_merge_step_names_the_feature_base() -> None:
    mods = (module("Counter", ModuleState.IN_PROGRESS, (unit(1, UnitState.DONE),)),)
    text = feature_step(feature_status(5, mods)).text
    assert "merge feature/dark-mode/module/Counter into feature/dark-mode/main" in text


def test_feature_paused_keeps_the_prefix() -> None:
    status = replace(feature_status(3), pause=Pause("usage", SAMPLE_TIME, None))
    text = feature_step(status).text
    assert text.startswith("feature dark-mode:")
    assert "paused (usage): run /bull:resume" in text


def test_feature_switch_prefix_comes_first() -> None:
    mods = (module("Counter", ModuleState.IN_PROGRESS, (unit(1, UnitState.TESTS),)),)
    text = feature_step(feature_status(5, mods), "main").text
    assert text.startswith("switch to feature/dark-mode/module/Counter, then")
    assert "feature dark-mode:" in text


def test_adopt_steps_start_with_adoption() -> None:
    result = adopt_step(adopt_status(1))
    assert result.text.startswith("adoption:")
    assert result.mode == Mode.ADOPT


def test_adopt_uses_the_adopt_command_instead_of_discuss() -> None:
    text = adopt_step(adopt_status(1)).text
    assert "/bull:adopt" in text
    assert "/bull:discuss" not in text


@pytest.mark.parametrize("stage", [2, 3, 4, 6])
def test_adopt_stages_use_the_adopt_command(stage: int) -> None:
    text = adopt_step(adopt_status(stage)).text
    assert "/bull:adopt" in text
    for other in (
        "/bull:outline",
        "/bull:setup",
        "/bull:skeleton",
        "/bull:prototype",
        "/bull:verify",
    ):
        assert other not in text


def test_adopt_stage_5_uses_prefixed_branches_and_switch_over() -> None:
    mods = (
        module(
            "Counter",
            ModuleState.IN_PROGRESS,
            (unit(1, UnitState.DONE), unit(2, UnitState.PENDING, UnitKind.SWITCH_OVER)),
        ),
    )
    text = adopt_step(adopt_status(5, mods)).text
    assert text.startswith("adoption:")
    assert "switch-over" in text


def test_adopt_start_names_the_adopt_module_branch() -> None:
    text = adopt_step(adopt_status(5, (module("Counter"),))).text
    assert "start Counter on adopt/module/Counter" in text


def test_adopt_switch_prefix_names_the_adopt_module_branch() -> None:
    mods = (module("Counter", ModuleState.IN_PROGRESS, (unit(1, UnitState.TESTS),)),)
    text = adopt_step(adopt_status(5, mods), "main").text
    assert text.startswith("switch to adopt/module/Counter, then")


# --- coverage triage: nothing can start ----------------------------------------------------


def test_stage_5_with_no_module_able_to_start_says_which_are_not_done() -> None:
    mods = (
        module("Counter", depends=("Store",)),
        module("Store", depends=("Counter",)),
    )
    assert (
        step(app(5, mods)).text
        == "no module can start (not done: Counter, Store): ask the human"
    )


def test_stage_5_stuck_list_leaves_out_finished_modules() -> None:
    mods = (
        module("Store", ModuleState.DONE),
        module("Counter", depends=("Cache",)),
        module("Cache", depends=("Counter",)),
    )
    text = step(app(5, mods)).text
    assert "not done: Counter, Cache" in text
    assert "Store" not in text


def test_adopt_mode_without_an_adoption_is_refused() -> None:
    with pytest.raises(StatusError):
        next_step_module.next_step(EMPTY, Mode.ADOPT, MockRefs("adopt/"), None)


def test_feature_mode_without_a_feature_is_refused() -> None:
    with pytest.raises(StatusError):
        next_step_module.next_step(EMPTY, Mode.FEATURE, MockRefs(), None)
