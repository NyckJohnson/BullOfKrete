"""Tests for the status mocks other modules' tests rely on."""

from __future__ import annotations

from bull.Modules.memo.mocks import sample_memo
from bull.Modules.status.Contracts import (
    Mode,
    ModuleState,
    Progress,
    Refs,
    Status,
    StatusStore,
    Track,
    UnitState,
)
from bull.Modules.status.mocks import (
    SAMPLE_TIME,
    MockProgress,
    MockRefs,
    MockStatusStore,
    sample_status,
)


def _unit_state(status: Status, module: str, number: int) -> UnitState:
    mod = next(m for m in status.modules if m.name == module)
    return next(u for u in mod.units if u.number == number).state


def test_sample_status_has_store_done_and_counter_in_progress() -> None:
    status = sample_status()
    assert status.app.stage == 5
    states = {m.name: m.state for m in status.modules}
    assert states == {"Store": ModuleState.DONE, "Counter": ModuleState.IN_PROGRESS}
    assert _unit_state(status, "Counter", 1) is UnitState.TESTS
    assert _unit_state(status, "Counter", 2) is UnitState.PENDING


def test_mocks_satisfy_their_protocols() -> None:
    store: StatusStore = MockStatusStore()
    refs: Refs = MockRefs()
    progress: Progress = MockProgress()
    assert store is not None and refs is not None and progress is not None


def test_store_starts_with_the_sample_status_and_records_calls() -> None:
    store = MockStatusStore()
    assert store.load() == sample_status()
    assert store.calls == [("load", ())]


def test_store_can_start_from_a_given_status() -> None:
    status = sample_status()
    other = Status(1, Track(2, ()), (), None, None, (), None, None, None)
    assert MockStatusStore(other).load() == other
    assert MockStatusStore(status).load() is status


def test_create_resets_to_stage_zero_with_no_modules() -> None:
    store = MockStatusStore()
    status = store.create()
    assert status.app == Track(0, ())
    assert status.modules == ()


def test_mode_is_app_feature_or_adopt() -> None:
    store = MockStatusStore()
    assert store.mode() is Mode.APP
    store.start_feature("dark")
    assert store.mode() is Mode.FEATURE
    store.end_feature()
    store.start_adoption()
    assert store.mode() is Mode.ADOPT


def test_set_stage_changes_the_app_stage() -> None:
    assert MockStatusStore().set_stage(6).app.stage == 6


def test_checkpoint_appends_once() -> None:
    store = MockStatusStore()
    store.checkpoint("app-accepted")
    status = store.checkpoint("app-accepted")
    assert status.app.checkpoints.count("app-accepted") == 1


def test_init_modules_adds_the_memo_modules_as_pending() -> None:
    store = MockStatusStore(
        Status(1, Track(2, ()), (), None, None, (), None, None, None)
    )
    status = store.init_modules(sample_memo())
    assert [m.name for m in status.modules] == ["Store", "Counter"]
    assert all(m.state is ModuleState.PENDING for m in status.modules)
    counter = status.modules[1]
    assert counter.depends == ("Store",)
    assert [u.number for u in counter.units] == [1, 2]
    assert counter.units[0].files == ("Contracts/counter.fx", "counter.fx")
    assert counter.part == "app"


def test_set_module_changes_module_state() -> None:
    status = MockStatusStore().set_module("Counter", ModuleState.BLOCKED)
    counter = next(m for m in status.modules if m.name == "Counter")
    assert counter.state is ModuleState.BLOCKED


def test_set_unit_changes_unit_state() -> None:
    status = MockStatusStore().set_unit("Counter", 1, UnitState.CODE)
    assert _unit_state(status, "Counter", 1) is UnitState.CODE


def test_attempt_increments_attempts_and_returns_the_unit() -> None:
    store = MockStatusStore()
    unit = store.attempt("Counter", 1)
    assert unit.attempts == 2
    assert unit.number == 1


def test_unblock_resets_attempts_to_one() -> None:
    store = MockStatusStore()
    store.attempt("Counter", 1)
    status = store.unblock("Counter", 1)
    counter = next(m for m in status.modules if m.name == "Counter")
    assert counter.units[0].attempts == 1
    assert counter.units[0].state is not UnitState.BLOCKED


def test_pause_and_resume_set_and_clear_the_pause() -> None:
    store = MockStatusStore()
    paused = store.pause("usage")
    assert paused.pause is not None
    assert paused.pause.reason == "usage"
    assert paused.pause.since == SAMPLE_TIME
    assert store.resume().pause is None


def test_wait_records_what_the_module_waits_for() -> None:
    waiting = MockStatusStore().wait("Counter", "contract change").waiting
    assert waiting is not None
    assert (waiting.module, waiting.what) == ("Counter", "contract change")


def test_approve_clears_the_wait_and_logs_the_approval() -> None:
    store = MockStatusStore()
    store.wait("Counter", "contract change")
    status = store.approve("Counter", "ok")
    assert status.waiting is None
    assert [(a.module, a.note) for a in status.approvals] == [("Counter", "ok")]


def test_take_approval_returns_and_removes_the_approval() -> None:
    store = MockStatusStore()
    store.approve("Counter", "ok")
    taken = store.take_approval("Counter")
    assert taken is not None and taken.note == "ok"
    assert store.take_approval("Counter") is None
    assert store.load().approvals == ()


def test_take_approval_for_unknown_module_returns_none() -> None:
    assert MockStatusStore().take_approval("Nope") is None


def test_record_scan_stores_the_counts_on_the_module() -> None:
    status = MockStatusStore().record_scan("Counter", 4, 3, 2, 1)
    scan = next(m for m in status.modules if m.name == "Counter").scan
    assert scan is not None
    assert (scan.covered, scan.missed, scan.contradicts, scan.not_in_spec) == (
        4,
        3,
        2,
        1,
    )


def test_plan_set_tick_and_clear() -> None:
    store = MockStatusStore()
    plan = store.set_plan("proto", ["a", "b"]).plan
    assert plan is not None
    assert plan.label == "proto"
    assert [(i.name, i.done) for i in plan.items] == [("a", False), ("b", False)]
    ticked = store.tick("a").plan
    assert ticked is not None
    assert [(i.name, i.done) for i in ticked.items] == [("a", True), ("b", False)]
    assert store.clear_plan().plan is None


def test_tick_without_a_plan_changes_nothing() -> None:
    store = MockStatusStore()
    assert store.tick("a").plan is None


def test_feature_start_end_and_mark_contract_applied() -> None:
    store = MockStatusStore()
    feature = store.start_feature("dark").feature
    assert feature is not None and feature.slug == "dark"
    applied = store.mark_contract_applied("Counter").feature
    assert applied is not None and applied.applied_contracts == ("Counter",)
    assert store.end_feature().feature is None


def test_mark_contract_applied_without_a_feature_changes_nothing() -> None:
    store = MockStatusStore()
    assert store.mark_contract_applied("Counter").feature is None


def test_reopen_sets_units_with_those_files_pending_with_one_attempt() -> None:
    store = MockStatusStore()
    status = store.reopen("Counter", ["cli.fx"])
    counter = next(m for m in status.modules if m.name == "Counter")
    assert counter.state is ModuleState.PENDING
    assert counter.units[1].state is UnitState.PENDING
    assert counter.units[1].attempts == 1
    assert counter.units[0].state is UnitState.TESTS


def test_add_modules_appends_pending_modules() -> None:
    store = MockStatusStore()
    entry = sample_memo().modules[0]
    status = store.add_modules([entry])
    assert [m.name for m in status.modules] == ["Store", "Counter", "Store"]
    assert status.modules[-1].state is ModuleState.PENDING


def test_adoption_start_finish_and_abandon() -> None:
    store = MockStatusStore()
    assert store.start_adoption().adoption is not None
    finished = store.finish_adoption()
    assert finished.adoption is None
    assert "app-accepted" in finished.app.checkpoints
    store.start_adoption()
    assert store.abandon_adoption().adoption is None


def test_store_calls_are_recorded_in_order() -> None:
    store = MockStatusStore()
    store.pause("x")
    store.resume()
    assert [name for name, _ in store.calls] == ["pause", "resume"]
    assert store.calls[0] == ("pause", ("x",))


def test_refs_default_to_the_main_trunk() -> None:
    refs = MockRefs()
    assert refs.trunk() == "main"
    assert refs.base() == "main"
    assert refs.module_branch("Store") == "module/Store"
    assert refs.tag("skeleton") == "skeleton"


def test_refs_with_a_prefix_prefix_branches_and_tags() -> None:
    refs = MockRefs("adopt/")
    assert refs.trunk() == "main"
    assert refs.base() == "adopt/main"
    assert refs.module_branch("Store") == "adopt/module/Store"
    assert refs.tag("setup") == "adopt/setup"


def test_refs_adopted_tag_is_never_prefixed() -> None:
    assert MockRefs("adopt/").tag("adopted") == "adopted"


def test_refs_module_for_branch_inverts_module_branch() -> None:
    refs = MockRefs("feature/x/")
    assert refs.module_for_branch(refs.module_branch("Store")) == "Store"
    assert refs.module_for_branch("main") is None


def test_refs_record_calls() -> None:
    refs = MockRefs()
    refs.tag("setup")
    assert refs.calls == [("tag", ("setup",))]


def test_progress_next_step_returns_its_step() -> None:
    progress = MockProgress()
    assert progress.next_step() == progress.step
    assert progress.step.mode is Mode.APP


def test_progress_summary_includes_the_next_step_text() -> None:
    progress = MockProgress()
    assert f"next: {progress.step.text}" in progress.summary()


def test_progress_as_json_reflects_the_step() -> None:
    progress = MockProgress()
    data = progress.as_json()
    assert data["next"] == progress.step.text
    assert data["mode"] == "app"
    assert data["format"] == 1


def test_progress_tags_are_sorted() -> None:
    progress = MockProgress()
    tags = progress.tags()
    assert tags == sorted(progress.tag_names)
    assert "module/Store" in tags
