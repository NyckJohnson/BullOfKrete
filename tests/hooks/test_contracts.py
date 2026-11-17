"""Tests for the hooks contract types."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from bull.Modules.hooks.Contracts import HookDecision, HookEvent, HookKind, Hooks


def _event(**overrides: object) -> HookEvent:
    fields: dict[str, object] = {
        "kind": HookKind.BEFORE_SHELL,
        "cwd": Path("/tmp/app"),
        "agent": None,
        "target_agent": None,
        "prompt": None,
        "command": None,
        "paths": (),
    }
    fields.update(overrides)
    return HookEvent(**fields)  # type: ignore[arg-type]  # overrides are dynamic test kwargs


def test_hook_kind_values_are_the_six_hook_names() -> None:
    assert {k.name: k.value for k in HookKind} == {
        "SESSION_START": "session-start",
        "BEFORE_AGENT": "before-agent",
        "BEFORE_SHELL": "before-shell",
        "BEFORE_EDIT": "before-edit",
        "BEFORE_READ": "before-read",
        "AGENT_END": "agent-end",
    }


@pytest.mark.parametrize("kind", list(HookKind))
def test_hook_kind_round_trips_through_its_value(kind: HookKind) -> None:
    assert HookKind(kind.value) is kind


def test_hook_kind_rejects_an_unknown_value() -> None:
    with pytest.raises(ValueError):
        HookKind("before-lunch")


def test_hook_event_field_names() -> None:
    assert [f.name for f in dataclasses.fields(HookEvent)] == [
        "kind",
        "cwd",
        "agent",
        "target_agent",
        "prompt",
        "command",
        "paths",
    ]


def test_hook_event_keeps_the_values_it_is_given() -> None:
    event = _event(
        kind=HookKind.BEFORE_EDIT,
        agent="code-writer",
        paths=(Path("a.py"), Path("b.py")),
        command="ls",
        prompt="p",
        target_agent="test-writer",
    )
    assert event.kind is HookKind.BEFORE_EDIT
    assert event.cwd == Path("/tmp/app")
    assert event.agent == "code-writer"
    assert event.target_agent == "test-writer"
    assert event.prompt == "p"
    assert event.command == "ls"
    assert event.paths == (Path("a.py"), Path("b.py"))


def test_hook_event_optional_fields_accept_none() -> None:
    event = _event()
    assert event.agent is None
    assert event.target_agent is None
    assert event.prompt is None
    assert event.command is None
    assert event.paths == ()


def test_hook_event_is_frozen() -> None:
    event = _event()
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.agent = "x"  # type: ignore[misc]  # frozen on purpose


def test_hook_event_equal_events_compare_equal() -> None:
    assert _event(agent="a") == _event(agent="a")
    assert _event(agent="a") != _event(agent="b")


def test_hook_decision_field_names() -> None:
    assert [f.name for f in dataclasses.fields(HookDecision)] == ["allow", "message"]


def test_hook_decision_holds_allow_and_message() -> None:
    decision = HookDecision(False, "no")
    assert decision.allow is False
    assert decision.message == "no"


def test_hook_decision_is_frozen() -> None:
    decision = HookDecision(True, "")
    with pytest.raises(dataclasses.FrozenInstanceError):
        decision.allow = False  # type: ignore[misc]  # frozen on purpose


def test_hooks_protocol_declares_handle_and_merge_targets() -> None:
    assert callable(Hooks.handle)
    assert callable(Hooks.merge_targets)


def test_a_class_with_both_methods_satisfies_the_protocol() -> None:
    class Impl:
        def handle(self, event: HookEvent) -> HookDecision:
            return HookDecision(True, "")

        def merge_targets(self, command: str) -> list[str]:
            return []

    hooks: Hooks = Impl()
    assert hooks.handle(_event()) == HookDecision(True, "")
    assert hooks.merge_targets("git merge x") == []
