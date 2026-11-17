"""Tests for the hooks mocks."""

from __future__ import annotations

from pathlib import Path

import pytest

from bull.Modules.hooks.Contracts import HookDecision, HookEvent, HookKind, Hooks
from bull.Modules.hooks.mocks import MockHooks


def _event(kind: HookKind = HookKind.BEFORE_SHELL) -> HookEvent:
    return HookEvent(
        kind=kind,
        cwd=Path("/tmp/app"),
        agent=None,
        target_agent=None,
        prompt=None,
        command=None,
        paths=(),
    )


def test_mock_satisfies_protocol() -> None:
    hooks: Hooks = MockHooks()
    assert hooks.merge_targets("ls") == []


def test_mock_starts_with_no_calls_and_no_decision_override() -> None:
    hooks = MockHooks()
    assert hooks.calls == []
    assert hooks.decision is None


@pytest.mark.parametrize(
    "kind",
    [
        HookKind.BEFORE_AGENT,
        HookKind.BEFORE_SHELL,
        HookKind.BEFORE_EDIT,
        HookKind.BEFORE_READ,
        HookKind.AGENT_END,
    ],
)
def test_handle_allows_everything_with_an_empty_message(kind: HookKind) -> None:
    assert MockHooks().handle(_event(kind)) == HookDecision(True, "")


def test_session_start_allows_with_a_short_context_message() -> None:
    decision = MockHooks().handle(_event(HookKind.SESSION_START))
    assert decision.allow is True
    assert decision.message != ""


def test_decision_override_is_returned_for_every_kind() -> None:
    hooks = MockHooks()
    hooks.decision = HookDecision(False, "blocked")
    for kind in HookKind:
        assert hooks.handle(_event(kind)) == HookDecision(False, "blocked")


def test_clearing_the_override_restores_the_default() -> None:
    hooks = MockHooks()
    hooks.decision = HookDecision(False, "blocked")
    hooks.decision = None
    assert hooks.handle(_event()) == HookDecision(True, "")


def test_handle_records_each_call_in_order() -> None:
    hooks = MockHooks()
    first, second = _event(HookKind.BEFORE_EDIT), _event(HookKind.AGENT_END)
    hooks.handle(first)
    hooks.handle(second)
    assert hooks.calls == [("handle", (first,)), ("handle", (second,))]


def test_handle_records_the_call_even_when_overridden() -> None:
    hooks = MockHooks()
    hooks.decision = HookDecision(False, "x")
    event = _event()
    hooks.handle(event)
    assert hooks.calls == [("handle", (event,))]


def test_merge_targets_records_each_call() -> None:
    hooks = MockHooks()
    hooks.merge_targets("git merge a")
    hooks.merge_targets("ls")
    assert hooks.calls == [
        ("merge_targets", ("git merge a",)),
        ("merge_targets", ("ls",)),
    ]


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("git merge feature", ["feature"]),
        ("git merge --no-ff module/foundation", ["module/foundation"]),
        ("git merge --no-ff --no-edit module/x", ["module/x"]),
    ],
)
def test_merge_targets_returns_the_branch_after_merge(
    command: str, expected: list[str]
) -> None:
    assert MockHooks().merge_targets(command) == expected


@pytest.mark.parametrize("command", ["", "git status", "ls -la", "git merge"])
def test_merge_targets_is_empty_without_a_merge_target(command: str) -> None:
    assert MockHooks().merge_targets(command) == []
