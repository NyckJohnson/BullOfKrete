"""Tests for `bull.Modules.status.store`: create, load, mode and the write path."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from dataclasses import replace
from typing import Any

import pytest

from bull.Modules.events.Contracts import EventKind
from bull.Modules.events.mocks import MockEventLog
from bull.Modules.foundation.mocks import MockClock, MockFiles, sample_layout
from bull.Modules.memo.Contracts import MemoProblem
from bull.Modules.memo.mocks import MockMemoReader
from bull.Modules.parts.mocks import MockParts, sample_part
from bull.Modules.settings.mocks import MockSettings
from bull.Modules.status import model, modules, transitions
from bull.Modules.status.Contracts import (
    ActiveFeature,
    Approval,
    Mode,
    ModuleState,
    Pause,
    Status,
    StatusError,
    Track,
    Unit,
    UnitState,
    Waiting,
)
from bull.Modules.status.mocks import SAMPLE_TIME, sample_status
from bull.Modules.status.store import LiveStatusStore

LAYOUT = sample_layout()
EMPTY = Status(1, Track(0, ()), (), None, None, (), None, None, None)


class Env:
    def __init__(self) -> None:
        self.files = MockFiles()
        self.events = MockEventLog()
        self.events.events.clear()
        self.settings = MockSettings()
        self.parts = MockParts()
        self.reader = MockMemoReader()
        self.store = LiveStatusStore(
            LAYOUT,
            self.files,
            self.events,
            MockClock(),
            self.settings,
            self.parts,
            self.reader,
        )

    def seed(self, status: Status) -> None:
        self.files.texts[LAYOUT.status_file] = (
            json.dumps(model.status_to_json(status), indent=2, sort_keys=True) + "\n"
        )

    def on_disk(self) -> Any:
        return json.loads(self.files.texts[LAYOUT.status_file])

    def status_writes(self) -> list[str]:
        return [
            name
            for name, args in self.files.calls
            if name in ("write_atomic", "write_json") and args[0] == LAYOUT.status_file
        ]


def test_create_writes_a_new_app_status() -> None:
    env = Env()
    status = env.store.create()
    assert status == EMPTY
    data = env.on_disk()
    assert data["format"] == 1
    assert data["kind"] == "app"
    assert data["stage"] == 0
    assert data["checkpoints"] == []
    assert data["modules"] == []


def test_create_writes_through_an_atomic_write() -> None:
    env = Env()
    env.store.create()
    assert len(env.status_writes()) == 1


def test_create_file_round_trips_through_the_model() -> None:
    env = Env()
    env.store.create()
    assert model.status_from_json(env.on_disk()) == EMPTY


def test_create_appends_one_status_event_named_create() -> None:
    env = Env()
    env.store.create()
    assert len(env.events.events) == 1
    event = env.events.events[0]
    assert event.kind == EventKind.STATUS
    assert event.data["what"] == "create"


def test_create_refuses_when_the_file_exists() -> None:
    env = Env()
    env.seed(sample_status())
    before = env.files.texts[LAYOUT.status_file]
    with pytest.raises(StatusError):
        env.store.create()
    assert env.files.texts[LAYOUT.status_file] == before
    assert env.events.events == []


def test_create_twice_refuses_the_second_time() -> None:
    env = Env()
    env.store.create()
    with pytest.raises(StatusError):
        env.store.create()


def test_load_returns_the_stored_status() -> None:
    env = Env()
    env.seed(sample_status())
    assert env.store.load() == sample_status()


def test_load_after_create_returns_the_new_status() -> None:
    env = Env()
    env.store.create()
    assert env.store.load() == EMPTY


def test_load_missing_file_says_not_a_bull_app() -> None:
    env = Env()
    with pytest.raises(StatusError) as caught:
        env.store.load()
    assert "not a bull app (no .bull/status.json)" in caught.value.message


def test_load_a_stack_repo_says_so() -> None:
    env = Env()
    data = model.status_to_json(EMPTY)
    data["kind"] = "stack"
    env.files.texts[LAYOUT.status_file] = json.dumps(data)
    with pytest.raises(StatusError) as caught:
        env.store.load()
    assert "this is a stack repo" in caught.value.message


def test_load_does_not_write_or_log() -> None:
    env = Env()
    env.seed(sample_status())
    env.store.load()
    assert env.status_writes() == []
    assert env.events.events == []


def test_mode_is_app_by_default() -> None:
    env = Env()
    env.seed(sample_status())
    assert env.store.mode() == Mode.APP


def test_mode_is_feature_when_a_feature_is_active() -> None:
    env = Env()
    feature = ActiveFeature("dark-mode", Track(1, ()), ())
    env.seed(replace(sample_status(), feature=feature))
    assert env.store.mode() == Mode.FEATURE


def test_mode_is_adopt_when_an_adoption_is_active() -> None:
    env = Env()
    env.seed(replace(sample_status(), adoption=Track(1, ())))
    assert env.store.mode() == Mode.ADOPT


def test_mode_adopt_wins_over_feature() -> None:
    env = Env()
    feature = ActiveFeature("dark-mode", Track(1, ()), ())
    env.seed(replace(sample_status(), feature=feature, adoption=Track(1, ())))
    assert env.store.mode() == Mode.ADOPT


def test_mode_on_a_missing_file_is_refused() -> None:
    env = Env()
    with pytest.raises(StatusError):
        env.store.mode()


# The write path, with one delegated transition replaced so these tests do not
# depend on the transition rules (unit 3).


def patch(monkeypatch: pytest.MonkeyPatch, name: str, fn: Callable[..., Any]) -> None:
    monkeypatch.setattr(transitions, name, fn, raising=False)


def test_a_change_writes_the_new_status_and_returns_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env()
    env.seed(sample_status())
    new = replace(sample_status(), app=Track(6, ()))
    patch(monkeypatch, "set_stage", lambda status, *a, **k: new)
    result = env.store.set_stage(6)
    assert result == new
    assert model.status_from_json(env.on_disk()) == new
    assert env.store.load() == new


def test_a_change_passes_the_current_status_to_the_transition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env()
    env.seed(sample_status())
    seen: list[Status] = []

    def fake(status: Status, *a: Any, **k: Any) -> Status:
        seen.append(status)
        return status

    patch(monkeypatch, "set_stage", fake)
    env.store.set_stage(4)
    assert seen == [sample_status()]


def test_a_change_writes_atomically_once(monkeypatch: pytest.MonkeyPatch) -> None:
    env = Env()
    env.seed(sample_status())
    patch(
        monkeypatch,
        "set_stage",
        lambda status, *a, **k: replace(status, app=Track(4, status.app.checkpoints)),
    )
    env.store.set_stage(4)
    assert len(env.status_writes()) == 1


def test_a_change_appends_one_status_event_named_after_the_method(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env()
    env.seed(sample_status())
    patch(
        monkeypatch,
        "set_stage",
        lambda status, *a, **k: replace(status, app=Track(6, ())),
    )
    env.store.set_stage(6)
    status_events = [e for e in env.events.events if e.kind == EventKind.STATUS]
    assert len(status_events) == 1
    assert status_events[0].data["what"] == "set_stage"


def test_a_refused_change_raises_and_writes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env()
    env.seed(sample_status())
    before = env.files.texts[LAYOUT.status_file]

    def refuse(status: Status, *a: Any, **k: Any) -> Status:
        raise StatusError("stage 6 needs every module done")

    patch(monkeypatch, "set_stage", refuse)
    with pytest.raises(StatusError, match="every module done"):
        env.store.set_stage(6)
    assert env.files.texts[LAYOUT.status_file] == before
    assert env.status_writes() == []
    assert env.events.events == []


def test_a_change_on_a_missing_file_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env()
    patch(monkeypatch, "set_stage", lambda status, *a, **k: status)
    with pytest.raises(StatusError) as caught:
        env.store.set_stage(1)
    assert "not a bull app" in caught.value.message
    assert env.status_writes() == []


def test_attempt_returns_the_unit_from_the_transition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env()
    base = sample_status()
    env.seed(base)
    unit = Unit(
        1,
        base.modules[1].units[0].files,
        base.modules[1].units[0].kind,
        UnitState.TESTS,
        2,
    )
    new = replace(
        base,
        modules=(
            base.modules[0],
            replace(base.modules[1], units=(unit, base.modules[1].units[1])),
        ),
    )
    patch(monkeypatch, "attempt", lambda status, *a, **k: (new, unit))
    result = env.store.attempt("Counter", 1)
    assert result == unit
    assert model.status_from_json(env.on_disk()) == new
    assert [e.data["what"] for e in env.events.events] == ["attempt"]


def test_take_approval_returns_the_approval_and_writes_the_rest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env()
    approval = Approval("Store", "ok", SAMPLE_TIME)
    env.seed(replace(sample_status(), approvals=(approval,)))
    patch(
        monkeypatch,
        "take_approval",
        lambda status, *a, **k: (replace(status, approvals=()), approval),
    )
    assert env.store.take_approval("Store") == approval
    assert env.on_disk()["approvals"] == []
    assert [e.data["what"] for e in env.events.events] == ["take_approval"]


def test_written_file_has_sorted_keys_and_a_trailing_newline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env()
    env.seed(sample_status())
    patch(
        monkeypatch,
        "set_stage",
        lambda status, *a, **k: replace(status, app=Track(4, status.app.checkpoints)),
    )
    env.store.set_stage(4)
    text = env.files.texts[LAYOUT.status_file]
    assert text.endswith("\n")
    assert text == json.dumps(json.loads(text), indent=2, sort_keys=True) + "\n"


# --- unit 3: attempt at the limit, no-ops, event sets, known parts and problems -----------


def seed_counter_unit(env: Env, state: UnitState, attempts: int) -> Status:
    base = sample_status()
    counter = base.modules[1]
    units = (
        replace(counter.units[0], state=state, attempts=attempts),
        counter.units[1],
    )
    status = replace(base, modules=(base.modules[0], replace(counter, units=units)))
    env.seed(status)
    return status


def test_attempt_at_the_limit_saves_blocked_logs_then_raises() -> None:
    env = Env()
    seed_counter_unit(env, UnitState.CODE, 3)
    with pytest.raises(StatusError) as caught:
        env.store.attempt("Counter", 1)
    assert caught.value.message == "unit 1 blocked after 3 attempts; ask the human"
    saved = model.status_from_json(env.on_disk())
    assert saved.modules[1].units[0].state == UnitState.BLOCKED
    assert [e.data["what"] for e in env.events.events] == ["attempt"]
    assert env.events.events[0].kind == EventKind.STATUS


def test_attempt_at_the_limit_with_a_faked_transition_still_saves_then_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env()
    base = seed_counter_unit(env, UnitState.CODE, 3)
    blocked = replace(base.modules[1].units[0], state=UnitState.BLOCKED)
    new = replace(
        base,
        modules=(
            base.modules[0],
            replace(base.modules[1], units=(blocked, base.modules[1].units[1])),
        ),
    )
    patch(monkeypatch, "attempt", lambda status, *a, **k: (new, blocked))
    with pytest.raises(
        StatusError, match="unit 1 blocked after 3 attempts; ask the human"
    ):
        env.store.attempt("Counter", 1)
    assert model.status_from_json(env.on_disk()) == new
    assert len(env.events.events) == 1


def test_attempt_message_uses_the_max_attempts_setting() -> None:
    env = Env()
    env.settings.app["max_attempts"] = 2
    seed_counter_unit(env, UnitState.CODE, 2)
    with pytest.raises(
        StatusError, match="unit 1 blocked after 2 attempts; ask the human"
    ):
        env.store.attempt("Counter", 1)


def test_attempt_below_the_limit_returns_the_unit_and_logs_once() -> None:
    env = Env()
    seed_counter_unit(env, UnitState.CODE, 1)
    unit = env.store.attempt("Counter", 1)
    assert unit.attempts == 2
    assert model.status_from_json(env.on_disk()).modules[1].units[0].attempts == 2
    assert [e.data["what"] for e in env.events.events] == ["attempt"]


def test_checkpoint_recorded_twice_writes_and_logs_only_once() -> None:
    env = Env()
    env.seed(replace(sample_status(), app=Track(2, ())))
    env.store.checkpoint("setup")
    env.events.events.clear()
    env.files.calls.clear()
    again = env.store.checkpoint("setup")
    assert "setup" in again.app.checkpoints
    assert env.status_writes() == []
    assert env.events.events == []


def test_resume_when_not_paused_writes_nothing_and_logs_nothing() -> None:
    env = Env()
    env.seed(sample_status())
    env.store.resume()
    assert env.status_writes() == []
    assert env.events.events == []


def test_take_approval_with_none_writes_nothing_and_logs_nothing() -> None:
    env = Env()
    env.seed(sample_status())
    assert env.store.take_approval("Store") is None
    assert env.status_writes() == []
    assert env.events.events == []


def test_take_approval_with_one_writes_and_logs() -> None:
    env = Env()
    approval = Approval("Store", "ok", SAMPLE_TIME)
    env.seed(replace(sample_status(), approvals=(approval,)))
    assert env.store.take_approval("Store") == approval
    assert env.on_disk()["approvals"] == []
    assert [e.data["what"] for e in env.events.events] == ["take_approval"]


def test_a_no_op_change_leaves_the_file_untouched() -> None:
    env = Env()
    env.seed(sample_status())
    before = env.files.texts[LAYOUT.status_file]
    env.store.resume()
    assert env.files.texts[LAYOUT.status_file] == before


def kinds(env: Env) -> list[EventKind]:
    return [e.kind for e in env.events.events]


def test_pause_logs_a_status_event_and_a_pause_event() -> None:
    env = Env()
    env.seed(sample_status())
    env.store.pause("usage limit")
    assert kinds(env) == [EventKind.STATUS, EventKind.PAUSE]
    assert env.events.events[0].data["what"] == "pause"
    assert env.events.events[1].data["reason"] == "usage limit"
    assert env.on_disk()["pause"]["reason"] == "usage limit"


def test_resume_logs_a_status_event_and_a_resume_event() -> None:
    env = Env()
    env.seed(replace(sample_status(), pause=Pause("usage", SAMPLE_TIME, None)))
    env.store.resume()
    assert kinds(env) == [EventKind.STATUS, EventKind.RESUME]
    assert env.events.events[0].data["what"] == "resume"
    assert env.on_disk()["pause"] is None


def test_approve_logs_a_status_event_and_a_decision_event() -> None:
    env = Env()
    env.seed(
        replace(sample_status(), waiting=Waiting("Store", "contract", SAMPLE_TIME))
    )
    env.store.approve("Store", "looks fine")
    assert kinds(env) == [EventKind.STATUS, EventKind.DECISION]
    assert env.events.events[0].data["what"] == "approve"
    assert env.on_disk()["waiting"] is None
    assert env.on_disk()["approvals"][0]["note"] == "looks fine"


def test_wait_logs_only_a_status_event() -> None:
    env = Env()
    env.seed(sample_status())
    env.store.wait("Store", "contract change")
    assert kinds(env) == [EventKind.STATUS]
    assert env.events.events[0].data["what"] == "wait"


def test_set_unit_through_the_store_uses_the_real_rules() -> None:
    env = Env()
    env.seed(sample_status())
    env.store.set_unit("Counter", 1, UnitState.CODE)
    assert env.on_disk()["modules"][1]["units"][0]["state"] == "code"
    with pytest.raises(StatusError):
        env.store.set_unit("Counter", 2, UnitState.DONE)


def test_init_modules_refused_problems_reach_the_error_and_nothing_is_written() -> None:
    env = Env()
    env.seed(EMPTY)
    before = env.files.texts[LAYOUT.status_file]
    env.reader.found_problems = [MemoProblem(33, "Counter has no Files line")]
    with pytest.raises(StatusError) as caught:
        env.store.init_modules(env.reader.memo)
    assert "Counter has no Files line" in caught.value.message + caught.value.fix
    assert "33" in caught.value.message + caught.value.fix
    assert env.files.texts[LAYOUT.status_file] == before
    assert env.events.events == []


def test_init_modules_asks_the_reader_for_problems_with_parts_and_max_files() -> None:
    env = Env()
    env.seed(EMPTY)
    env.parts.parts.append(sample_part(name="web"))
    env.store.init_modules(env.reader.memo)
    calls = [args for name, args in env.reader.calls if name == "problems"]
    assert calls == [(env.reader.memo, ("app", "web"), 4)]


def test_init_modules_uses_the_max_files_per_unit_setting() -> None:
    env = Env()
    env.seed(EMPTY)
    env.settings.app["max_files_per_unit"] = 2
    env.store.init_modules(env.reader.memo)
    assert [a[2] for n, a in env.reader.calls if n == "problems"] == [2]


def test_init_modules_passes_known_parts_and_problems_to_the_function(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env()
    env.seed(EMPTY)
    env.parts.parts.append(sample_part(name="web"))
    problem = MemoProblem(5, "x")
    env.reader.found_problems = [problem]
    seen: dict[str, Any] = {}

    def fake(
        status: Status, memo: Any, replace_: bool = False, **kwargs: Any
    ) -> Status:
        seen.update(kwargs)
        seen["replace"] = replace_
        return status

    monkeypatch.setattr(modules, "init_modules", fake, raising=False)
    env.store.init_modules(env.reader.memo, True)
    assert list(seen["known_parts"]) == ["app", "web"]
    assert list(seen["problems"]) == [problem]
    assert seen["replace"] is True


def test_init_modules_writes_the_modules_and_logs_init_modules() -> None:
    env = Env()
    env.seed(EMPTY)
    env.store.init_modules(env.reader.memo)
    assert [m["name"] for m in env.on_disk()["modules"]] == ["Store", "Counter"]
    assert [e.data["what"] for e in env.events.events] == ["init_modules"]


def test_add_modules_passes_known_parts_to_the_function(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env()
    env.seed(sample_status())
    env.parts.parts.append(sample_part(name="web"))
    seen: dict[str, Any] = {}

    def fake(status: Status, entries: Any, **kwargs: Any) -> Status:
        seen.update(kwargs)
        return replace(status, app=Track(4, status.app.checkpoints))

    monkeypatch.setattr(modules, "add_modules", fake, raising=False)
    env.store.add_modules(env.reader.memo.modules)
    assert list(seen["known_parts"]) == ["app", "web"]


def test_set_module_through_the_store_logs_a_status_event() -> None:
    env = Env()
    env.seed(sample_status())
    env.store.set_module("Counter", ModuleState.BLOCKED)
    assert [e.data["what"] for e in env.events.events] == ["set_module"]
    assert env.on_disk()["modules"][1]["state"] == "blocked"


# --- coverage triage: every remaining change through the store ------------------------------

ACCEPTED_CPS = (
    "outline-approved",
    "setup",
    "skeleton",
    "ui-approved",
    "app-accepted",
)


def accepted() -> Status:
    return replace(sample_status(), app=Track(6, ACCEPTED_CPS))


def whats(env: Env) -> list[object]:
    return [e.data["what"] for e in env.events.events if e.kind == EventKind.STATUS]


def with_counter(**changes: Any) -> Status:
    base = sample_status()
    return replace(base, modules=(base.modules[0], replace(base.modules[1], **changes)))


def test_unblock_returns_the_unit_to_tests_with_one_attempt_and_logs() -> None:
    env = Env()
    seed_counter_unit(env, UnitState.BLOCKED, 3)
    env.store.unblock("Counter", 1)
    unit = model.status_from_json(env.on_disk()).modules[1].units[0]
    assert (unit.state, unit.attempts) == (UnitState.TESTS, 1)
    assert whats(env) == ["unblock"]


def test_record_scan_stores_the_counts_with_the_time_from_the_clock() -> None:
    env = Env()
    env.seed(with_counter(reference_tests=True))
    env.store.record_scan("Counter", 4, 3, 2, 1)
    scan = model.status_from_json(env.on_disk()).modules[1].scan
    assert scan is not None
    assert (scan.covered, scan.missed, scan.contradicts, scan.not_in_spec) == (
        4,
        3,
        2,
        1,
    )
    assert scan.time == MockClock().time
    assert whats(env) == ["record_scan"]


def test_record_scan_for_a_module_without_reference_tests_is_refused() -> None:
    env = Env()
    env.seed(sample_status())
    with pytest.raises(StatusError):
        env.store.record_scan("Counter", 1, 0, 0, 0)
    assert env.status_writes() == []
    assert env.events.events == []


def test_set_plan_writes_the_plan_and_logs() -> None:
    env = Env()
    env.seed(sample_status())
    env.store.set_plan("verify", ["login", "export"])
    plan = model.status_from_json(env.on_disk()).plan
    assert plan is not None
    assert plan.label == "verify"
    assert [(i.name, i.done) for i in plan.items] == [
        ("login", False),
        ("export", False),
    ]
    assert whats(env) == ["set_plan"]


def test_tick_marks_the_item_done_and_logs() -> None:
    env = Env()
    env.seed(sample_status())
    env.store.set_plan("verify", ["login", "export"])
    env.events.events.clear()
    env.store.tick("login")
    plan = model.status_from_json(env.on_disk()).plan
    assert plan is not None
    assert [(i.name, i.done) for i in plan.items] == [
        ("login", True),
        ("export", False),
    ]
    assert whats(env) == ["tick"]


def test_tick_of_an_unknown_item_is_refused_and_writes_nothing() -> None:
    env = Env()
    env.seed(sample_status())
    env.store.set_plan("verify", ["login"])
    before = env.files.texts[LAYOUT.status_file]
    env.events.events.clear()
    with pytest.raises(StatusError):
        env.store.tick("nope")
    assert env.files.texts[LAYOUT.status_file] == before
    assert env.events.events == []


def test_clear_plan_removes_the_plan_and_logs() -> None:
    env = Env()
    env.seed(sample_status())
    env.store.set_plan("verify", ["login"])
    env.events.events.clear()
    env.store.clear_plan()
    assert env.on_disk()["plan"] is None
    assert whats(env) == ["clear_plan"]


def test_start_feature_writes_the_feature_track_and_logs() -> None:
    env = Env()
    env.seed(accepted())
    env.store.start_feature("dark-mode")
    feature = model.status_from_json(env.on_disk()).feature
    assert feature == ActiveFeature("dark-mode", Track(1, ()), ())
    assert whats(env) == ["start_feature"]


def test_end_feature_clears_the_feature_and_logs() -> None:
    env = Env()
    env.seed(replace(accepted(), feature=ActiveFeature("one", Track(2, ()), ())))
    env.store.end_feature()
    assert env.on_disk()["feature"] is None
    assert whats(env) == ["end_feature"]


def test_end_feature_without_a_feature_is_refused_and_writes_nothing() -> None:
    env = Env()
    env.seed(accepted())
    with pytest.raises(StatusError):
        env.store.end_feature()
    assert env.status_writes() == []
    assert env.events.events == []


def test_mark_contract_applied_records_the_module_and_logs() -> None:
    env = Env()
    env.seed(replace(accepted(), feature=ActiveFeature("one", Track(3, ()), ())))
    env.store.mark_contract_applied("Store")
    feature = model.status_from_json(env.on_disk()).feature
    assert feature is not None
    assert feature.applied_contracts == ("Store",)
    assert whats(env) == ["mark_contract_applied"]


def test_mark_contract_applied_twice_writes_and_logs_only_once() -> None:
    env = Env()
    env.seed(replace(accepted(), feature=ActiveFeature("one", Track(3, ()), ())))
    env.store.mark_contract_applied("Store")
    env.events.events.clear()
    env.files.calls.clear()
    env.store.mark_contract_applied("Store")
    assert env.status_writes() == []
    assert env.events.events == []


def test_mark_contract_applied_without_a_feature_is_refused() -> None:
    env = Env()
    env.seed(accepted())
    with pytest.raises(StatusError):
        env.store.mark_contract_applied("Store")
    assert env.status_writes() == []


def test_reopen_resets_the_units_holding_the_files_and_logs() -> None:
    env = Env()
    base = sample_status()
    store_mod = base.modules[0]
    env.seed(replace(base, modules=(store_mod, base.modules[1])))
    env.store.reopen("Store", ["store.fx"])
    new = model.status_from_json(env.on_disk())
    assert new.modules[0].state == ModuleState.PENDING
    assert new.modules[0].units[0].state == UnitState.PENDING
    assert whats(env) == ["reopen"]


def test_reopen_with_unknown_files_is_refused_and_writes_nothing() -> None:
    env = Env()
    env.seed(sample_status())
    with pytest.raises(StatusError):
        env.store.reopen("Store", ["nowhere.fx"])
    assert env.status_writes() == []
    assert env.events.events == []


def test_start_adoption_writes_the_adoption_track_and_logs() -> None:
    env = Env()
    env.seed(EMPTY)
    env.store.start_adoption()
    assert model.status_from_json(env.on_disk()).adoption == Track(1, ())
    assert whats(env) == ["start_adoption"]


def test_start_adoption_while_a_feature_is_active_is_refused() -> None:
    env = Env()
    env.seed(replace(EMPTY, feature=ActiveFeature("one", Track(2, ()), ())))
    with pytest.raises(StatusError):
        env.store.start_adoption()
    assert env.status_writes() == []


def test_finish_adoption_records_app_accepted_clears_the_adoption_and_logs() -> None:
    env = Env()
    env.seed(
        replace(
            EMPTY,
            adoption=Track(6, ("outline-approved", "setup", "baseline", "scaffold")),
        )
    )
    env.store.finish_adoption()
    new = model.status_from_json(env.on_disk())
    assert new.adoption is None
    assert new.app.stage == 6
    assert "app-accepted" in new.app.checkpoints
    assert whats(env) == ["finish_adoption"]


def test_abandon_adoption_clears_it_keeps_the_app_track_and_logs() -> None:
    env = Env()
    env.seed(
        replace(
            EMPTY, app=Track(0, ()), adoption=Track(3, ("outline-approved", "setup"))
        )
    )
    env.store.abandon_adoption()
    new = model.status_from_json(env.on_disk())
    assert new.adoption is None
    assert new.app == Track(0, ())
    assert whats(env) == ["abandon_adoption"]


def test_abandon_adoption_without_an_adoption_is_refused() -> None:
    env = Env()
    env.seed(EMPTY)
    with pytest.raises(StatusError):
        env.store.abandon_adoption()
    assert env.status_writes() == []
    assert env.events.events == []


def test_set_unit_to_the_current_state_writes_nothing_and_logs_nothing() -> None:
    env = Env()
    env.seed(sample_status())
    env.store.set_unit("Counter", 1, UnitState.TESTS)
    assert env.status_writes() == []
    assert env.events.events == []


# --- coverage triage: setting guards -------------------------------------------------------


@pytest.mark.parametrize("value", ["three", True])
def test_attempt_refuses_a_max_attempts_setting_that_is_not_an_integer(
    value: object,
) -> None:
    env = Env()
    seed_counter_unit(env, UnitState.CODE, 1)
    env.settings.app["max_attempts"] = value  # type: ignore[assignment]
    with pytest.raises(StatusError) as caught:
        env.store.attempt("Counter", 1)
    assert "max_attempts" in caught.value.message
    assert env.status_writes() == []


def test_init_modules_refuses_a_max_files_per_unit_setting_that_is_not_an_integer() -> (
    None
):
    env = Env()
    env.seed(EMPTY)
    env.settings.app["max_files_per_unit"] = "many"  # type: ignore[assignment]
    with pytest.raises(StatusError) as caught:
        env.store.init_modules(env.reader.memo)
    assert "max_files_per_unit" in caught.value.message
    assert env.status_writes() == []


def test_pause_with_a_naive_clock_time_is_saved_as_utc_with_z() -> None:
    env = Env()
    env.seed(sample_status())
    env.store = LiveStatusStore(
        LAYOUT,
        env.files,
        env.events,
        MockClock(datetime(2026, 11, 7, 12, 0, 0)),
        env.settings,
        env.parts,
        env.reader,
    )
    env.store.pause("usage limit")
    assert env.on_disk()["pause"]["since"] == "2026-11-07T12:00:00Z"
    loaded = env.store.load().pause
    assert loaded is not None
    assert loaded.since == datetime(2026, 11, 7, 12, 0, 0, tzinfo=UTC)
    assert loaded.since.utcoffset() == UTC.utcoffset(None)
