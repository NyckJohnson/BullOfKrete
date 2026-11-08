"""Tests for `bull.Modules.status.store`: create, load, mode and the write path."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import pytest

from bull.Modules.events.Contracts import EventKind
from bull.Modules.events.mocks import MockEventLog
from bull.Modules.foundation.mocks import MockClock, MockFiles, sample_layout
from bull.Modules.memo.mocks import MockMemoReader
from bull.Modules.parts.mocks import MockParts
from bull.Modules.settings.mocks import MockSettings
from bull.Modules.status import model, transitions
from bull.Modules.status.Contracts import (
    ActiveFeature,
    Approval,
    Mode,
    Status,
    StatusError,
    Track,
    Unit,
    UnitState,
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
        self.store = LiveStatusStore(
            LAYOUT,
            self.files,
            self.events,
            MockClock(),
            MockSettings(),
            MockParts(),
            MockMemoReader(),
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
    patch(monkeypatch, "set_stage", lambda status, *a, **k: status)
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
    patch(monkeypatch, "set_stage", lambda status, *a, **k: status)
    env.store.set_stage(5)
    text = env.files.texts[LAYOUT.status_file]
    assert text.endswith("\n")
    assert text == json.dumps(json.loads(text), indent=2, sort_keys=True) + "\n"
