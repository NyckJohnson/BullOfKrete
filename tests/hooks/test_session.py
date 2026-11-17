"""Tests for `bull.Modules.hooks.session`: the session-start context."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from bull.Modules.foundation.mocks import sample_layout
from bull.Modules.hooks.Contracts import HookDecision, HookEvent, HookKind
from bull.Modules.hooks.session import SessionStart
from bull.Modules.status.Contracts import (
    ActiveFeature,
    Mode,
    NextStep,
    Pause,
    Track,
    Waiting,
)
from bull.Modules.status.mocks import MockProgress, MockStatusStore, sample_status

NOW = datetime(2026, 11, 7, 12, 0, 0, tzinfo=UTC)


def _start(
    store: MockStatusStore, progress: MockProgress, tmp_path: Path
) -> HookDecision:
    app = sample_layout(tmp_path)
    event = HookEvent(HookKind.SESSION_START, tmp_path, None, None, None, None, ())
    return SessionStart(store, progress).check(app, event)


def test_message_names_stage_and_mode(tmp_path: Path) -> None:
    decision = _start(MockStatusStore(sample_status()), MockProgress(), tmp_path)
    assert decision.allow
    first = decision.message.splitlines()[0]
    assert "stage 5" in first
    assert "mode app" in first
    assert "feature" not in first


def test_message_names_a_feature_mode(tmp_path: Path) -> None:
    status = replace(
        sample_status(),
        feature=ActiveFeature("dark-mode", Track(2, ()), ()),
    )
    progress = MockProgress()
    progress.step = NextStep("go", Mode.FEATURE)
    decision = _start(MockStatusStore(status), progress, tmp_path)
    first = decision.message.splitlines()[0]
    assert "stage 2" in first
    assert "mode feature" in first
    assert "dark-mode" in first


def test_message_names_an_adopt_mode_and_the_adoption_stage(tmp_path: Path) -> None:
    status = replace(sample_status(), adoption=Track(3, ()))
    progress = MockProgress()
    progress.step = NextStep("go", Mode.ADOPT)
    decision = _start(MockStatusStore(status), progress, tmp_path)
    first = decision.message.splitlines()[0]
    assert "stage 3" in first
    assert "mode adopt" in first


def test_message_includes_the_next_step(tmp_path: Path) -> None:
    progress = MockProgress()
    progress.step = NextStep("Counter unit 2: reviewer", Mode.APP)
    decision = _start(MockStatusStore(sample_status()), progress, tmp_path)
    assert "Counter unit 2: reviewer" in decision.message


def test_paused_message_has_unit_reason_and_resume_command(tmp_path: Path) -> None:
    status = replace(
        sample_status(),
        pause=Pause("5-hour usage 90% ≥ 85%", NOW, "Counter unit 2"),
    )
    decision = _start(MockStatusStore(status), MockProgress(), tmp_path)
    assert decision.allow
    assert "Counter unit 2" in decision.message
    assert "5-hour usage 90% ≥ 85%" in decision.message
    assert "run `/bull:resume`" in decision.message


def test_paused_without_a_unit_still_gives_reason_and_resume(tmp_path: Path) -> None:
    status = replace(sample_status(), pause=Pause("weekly limit", NOW, None))
    decision = _start(MockStatusStore(status), MockProgress(), tmp_path)
    assert "weekly limit" in decision.message
    assert "/bull:resume" in decision.message


def test_not_paused_message_does_not_mention_resume(tmp_path: Path) -> None:
    decision = _start(MockStatusStore(sample_status()), MockProgress(), tmp_path)
    assert "/bull:resume" not in decision.message


def test_waiting_approval_is_in_the_message(tmp_path: Path) -> None:
    status = replace(sample_status(), waiting=Waiting("Counter", "api changed", NOW))
    decision = _start(MockStatusStore(status), MockProgress(), tmp_path)
    assert "Counter" in decision.message
    assert "approv" in decision.message
