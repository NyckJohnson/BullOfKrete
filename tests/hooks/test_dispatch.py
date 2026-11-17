"""Tests for `bull.Modules.hooks.dispatch`: `LiveHooks` routes events to the safeguards."""

from __future__ import annotations

from pathlib import Path

import pytest

from bull.Modules.events.Contracts import EventKind, EventValue
from bull.Modules.events.mocks import MockEventLog
from bull.Modules.foundation.Contracts import AppLayout, FileFormatError
from bull.Modules.foundation.mocks import MockFiles, MockLayouts, sample_layout
from bull.Modules.hooks.Contracts import HookDecision, HookEvent, HookKind
from bull.Modules.hooks.dispatch import LiveHooks
from bull.Modules.hooks.merge_guard import MergeGuard
from bull.Modules.hooks.protection import Protection
from bull.Modules.hooks.session import SessionStart
from bull.Modules.hooks.usage_guard import UsageGuard


class _SpyMergeGuard(MergeGuard):
    def __init__(self, decision: HookDecision) -> None:
        self.decision = decision
        self.seen: list[tuple[AppLayout, str]] = []

    def check(self, app: AppLayout, command: str) -> HookDecision:
        self.seen.append((app, command))
        return self.decision


class _SpyProtection(Protection):
    def __init__(self, decision: HookDecision) -> None:
        self.decision = decision
        self.seen: list[tuple[AppLayout, HookEvent]] = []

    def check(self, app: AppLayout, event: HookEvent) -> HookDecision:
        self.seen.append((app, event))
        return self.decision


class _SpyUsageGuard(UsageGuard):
    def __init__(self, decision: HookDecision) -> None:
        self.decision = decision
        self.seen: list[tuple[AppLayout, HookEvent]] = []

    def check(self, app: AppLayout, event: HookEvent) -> HookDecision:
        self.seen.append((app, event))
        return self.decision


class _SpySession(SessionStart):
    def __init__(self, decision: HookDecision) -> None:
        self.decision = decision
        self.seen: list[tuple[AppLayout, HookEvent]] = []

    def check(self, app: AppLayout, event: HookEvent) -> HookDecision:
        self.seen.append((app, event))
        return self.decision


class _Rig:
    def __init__(self, root: Path) -> None:
        self.app = sample_layout(root)
        self.layouts = MockLayouts(root)
        self.layouts.found = self.app
        self.events = MockEventLog()
        self.events.events.clear()
        self.files = MockFiles()
        self.merge = _SpyMergeGuard(HookDecision(False, "merge-says-no"))
        self.protection = _SpyProtection(HookDecision(False, "protection-says-no"))
        self.usage = _SpyUsageGuard(HookDecision(False, "usage-says-no"))
        self.session = _SpySession(HookDecision(True, "session-context"))
        self.hooks = LiveHooks(
            layouts=self.layouts,
            session=self.session,
            usage_guard=self.usage,
            merge_guard=self.merge,
            protection=self.protection,
            events=self.events,
            files=self.files,
        )

    def event(
        self,
        kind: HookKind,
        *,
        agent: str | None = None,
        target: str | None = None,
        command: str | None = None,
        paths: tuple[Path, ...] = (),
    ) -> HookEvent:
        return HookEvent(kind, self.app.root, agent, target, "p", command, paths)


@pytest.mark.parametrize("kind", list(HookKind))
def test_outside_a_bull_app_every_hook_allows_with_an_empty_message(
    tmp_path: Path, kind: HookKind
) -> None:
    rig = _Rig(tmp_path)
    rig.layouts.found = None
    decision = rig.hooks.handle(
        rig.event(kind, command="git merge x", paths=(tmp_path / "a",))
    )
    assert decision == HookDecision(True, "")
    assert rig.merge.seen == []
    assert rig.protection.seen == []
    assert rig.usage.seen == []
    assert rig.session.seen == []
    assert rig.events.events == []


def test_the_app_is_looked_up_from_the_event_cwd(tmp_path: Path) -> None:
    rig = _Rig(tmp_path)
    rig.hooks.handle(rig.event(HookKind.SESSION_START))
    assert ("find", (tmp_path,)) in rig.layouts.calls


def test_session_start_returns_the_session_context(tmp_path: Path) -> None:
    rig = _Rig(tmp_path)
    decision = rig.hooks.handle(rig.event(HookKind.SESSION_START))
    assert decision == HookDecision(True, "session-context")
    assert rig.session.seen[0][0] == rig.app


def test_before_agent_returns_the_usage_guard_decision(tmp_path: Path) -> None:
    rig = _Rig(tmp_path)
    event = rig.event(HookKind.BEFORE_AGENT, target="code-writer")
    decision = rig.hooks.handle(event)
    assert decision == HookDecision(False, "usage-says-no")
    assert rig.usage.seen == [(rig.app, event)]


def test_before_shell_goes_to_the_merge_guard_with_the_command(
    tmp_path: Path,
) -> None:
    rig = _Rig(tmp_path)
    decision = rig.hooks.handle(
        rig.event(HookKind.BEFORE_SHELL, command="git merge module/Counter")
    )
    assert decision == HookDecision(False, "merge-says-no")
    assert rig.merge.seen == [(rig.app, "git merge module/Counter")]


def test_before_shell_without_a_command_is_allowed(tmp_path: Path) -> None:
    rig = _Rig(tmp_path)
    decision = rig.hooks.handle(rig.event(HookKind.BEFORE_SHELL, command=None))
    assert decision.allow


@pytest.mark.parametrize("kind", [HookKind.BEFORE_EDIT, HookKind.BEFORE_READ])
def test_edit_and_read_go_to_protection(tmp_path: Path, kind: HookKind) -> None:
    rig = _Rig(tmp_path)
    event = rig.event(kind, agent="code-writer", paths=(tmp_path / "a.py",))
    decision = rig.hooks.handle(event)
    assert decision == HookDecision(False, "protection-says-no")
    assert rig.protection.seen == [(rig.app, event)]


def test_agent_end_appends_agent_end_and_allows(tmp_path: Path) -> None:
    rig = _Rig(tmp_path)
    decision = rig.hooks.handle(rig.event(HookKind.AGENT_END, agent="code-writer"))
    assert decision.allow
    ends = [e for e in rig.events.events if e.kind is EventKind.AGENT_END]
    assert len(ends) == 1
    assert ends[0].data["agent"] == "code-writer"


def test_agent_end_does_not_consult_the_other_safeguards(tmp_path: Path) -> None:
    rig = _Rig(tmp_path)
    rig.hooks.handle(rig.event(HookKind.AGENT_END, agent="reviewer"))
    assert rig.merge.seen == []
    assert rig.protection.seen == []
    assert rig.usage.seen == []


def test_merge_targets_delegates_to_merge_guard_parsing(tmp_path: Path) -> None:
    hooks = _Rig(tmp_path).hooks
    assert hooks.merge_targets("git switch main && git merge --no-ff -m x a b") == [
        "a",
        "b",
    ]
    assert hooks.merge_targets("git status") == []


class _Raiser:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def check(self, app: AppLayout, event: HookEvent) -> HookDecision:
        raise self.error


class _FailingEvents(MockEventLog):
    def append(self, kind: EventKind, **data: EventValue) -> None:
        raise OSError("disk full")


_GUARDED = [
    HookKind.BEFORE_AGENT,
    HookKind.BEFORE_SHELL,
    HookKind.BEFORE_EDIT,
    HookKind.BEFORE_READ,
]


def _break(rig: _Rig, error: Exception) -> None:
    raiser = _Raiser(error)
    rig.session.check = raiser.check  # type: ignore[method-assign]
    rig.usage.check = raiser.check  # type: ignore[method-assign]
    rig.merge.check = lambda app, command: raiser.check(app, None)  # type: ignore[method-assign,arg-type]
    rig.protection.check = raiser.check  # type: ignore[method-assign]


def _stack_repo(rig: _Rig) -> None:
    rig.files.texts[rig.app.status_file] = '{"kind": "stack", "format": 1}'


@pytest.mark.parametrize("kind", list(HookKind))
def test_in_a_stack_repo_every_hook_allows_with_an_empty_message(
    tmp_path: Path, kind: HookKind
) -> None:
    rig = _Rig(tmp_path)
    _stack_repo(rig)
    decision = rig.hooks.handle(
        rig.event(kind, agent="code-writer", command="git merge x", paths=(tmp_path,))
    )
    assert decision == HookDecision(True, "")
    assert rig.merge.seen == []
    assert rig.protection.seen == []
    assert rig.usage.seen == []
    assert rig.session.seen == []
    assert rig.events.events == []


def test_a_status_file_of_another_kind_is_not_a_stack_repo(tmp_path: Path) -> None:
    rig = _Rig(tmp_path)
    rig.files.texts[rig.app.status_file] = '{"kind": "app"}'
    decision = rig.hooks.handle(rig.event(HookKind.SESSION_START))
    assert decision == HookDecision(True, "session-context")


@pytest.mark.parametrize("kind", _GUARDED)
def test_a_failing_safeguard_blocks_guarded_kinds_with_the_cause(
    tmp_path: Path, kind: HookKind
) -> None:
    rig = _Rig(tmp_path)
    _break(rig, TypeError("bad setting value"))
    decision = rig.hooks.handle(
        rig.event(kind, agent="code-writer", command="git merge x", paths=(tmp_path,))
    )
    assert not decision.allow
    assert decision.message.startswith("bull safeguard could not run:")
    assert "bad setting value" in decision.message


@pytest.mark.parametrize("kind", _GUARDED)
def test_a_failing_safeguard_message_includes_the_fix_when_there_is_one(
    tmp_path: Path, kind: HookKind
) -> None:
    rig = _Rig(tmp_path)
    _break(rig, FileFormatError("status.json: invalid JSON", "fix status.json by hand"))
    decision = rig.hooks.handle(
        rig.event(kind, agent="code-writer", command="git merge x", paths=(tmp_path,))
    )
    assert not decision.allow
    assert decision.message.startswith("bull safeguard could not run:")
    assert "status.json: invalid JSON" in decision.message
    assert "fix status.json by hand" in decision.message


def test_a_failing_session_start_allows_with_the_message(tmp_path: Path) -> None:
    rig = _Rig(tmp_path)
    _break(rig, FileFormatError("status.json: invalid JSON", "repair it"))
    decision = rig.hooks.handle(rig.event(HookKind.SESSION_START))
    assert decision.allow
    assert decision.message.startswith("bull safeguard could not run:")
    assert "status.json: invalid JSON" in decision.message
    assert "repair it" in decision.message


def test_a_failing_event_log_on_agent_end_allows_with_the_message(
    tmp_path: Path,
) -> None:
    rig = _Rig(tmp_path)
    rig.hooks = LiveHooks(
        layouts=rig.layouts,
        session=rig.session,
        usage_guard=rig.usage,
        merge_guard=rig.merge,
        protection=rig.protection,
        events=_FailingEvents(),
        files=rig.files,
    )
    decision = rig.hooks.handle(rig.event(HookKind.AGENT_END, agent="code-writer"))
    assert decision.allow
    assert decision.message.startswith("bull safeguard could not run:")
    assert "disk full" in decision.message


@pytest.mark.parametrize(
    ("agent", "recorded"),
    [
        ("bull:reviewer", "reviewer"),
        ("code-writer", "code-writer"),
        (None, None),
    ],
)
def test_agent_end_records_the_stripped_agent_name(
    tmp_path: Path, agent: str | None, recorded: str | None
) -> None:
    rig = _Rig(tmp_path)
    decision = rig.hooks.handle(rig.event(HookKind.AGENT_END, agent=agent))
    assert decision.allow
    ends = [e for e in rig.events.events if e.kind is EventKind.AGENT_END]
    assert [e.data["agent"] for e in ends] == [recorded]
