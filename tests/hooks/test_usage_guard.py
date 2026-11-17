"""Tests for `bull.Modules.hooks.usage_guard`: the BEFORE_AGENT checks."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from bull.Modules.events.Contracts import EventKind
from bull.Modules.events.mocks import MockEventLog
from bull.Modules.foundation.Contracts import AppLayout
from bull.Modules.foundation.mocks import sample_layout
from bull.Modules.hooks.Contracts import HookDecision, HookEvent, HookKind
from bull.Modules.hooks.usage_guard import UsageGuard
from bull.Modules.settings.Contracts import SettingValue
from bull.Modules.settings.mocks import MockSettings
from bull.Modules.status.Contracts import Waiting
from bull.Modules.status.mocks import MockStatusStore, sample_status
from bull.Modules.usage.Contracts import UsageCheck, UsageVerdict
from bull.Modules.usage.mocks import MockUsage

NOW = datetime(2026, 11, 7, 12, 0, 0, tzinfo=UTC)


class _Settings(MockSettings):
    """Settings that serve `reference_dir` from a plain value."""

    def __init__(self, reference_dir: str) -> None:
        super().__init__()
        self.reference_dir = reference_dir

    def get(self, key: str, part: str | None = None) -> SettingValue:
        if key == "reference_dir":
            return self.reference_dir
        return super().get(key, part)


class _Rig:
    def __init__(self, root: Path, reference_dir: str = "reference") -> None:
        self.app: AppLayout = sample_layout(root)
        self.usage = MockUsage()
        self.store = MockStatusStore(sample_status())
        self.events = MockEventLog()
        self.events.events.clear()
        self.guard = UsageGuard(
            self.usage, self.store, _Settings(reference_dir), self.events
        )

    def launch(
        self,
        target: str | None = "code-writer",
        prompt: str | None = "do the unit",
        agent: str | None = None,
    ) -> HookDecision:
        event = HookEvent(
            HookKind.BEFORE_AGENT, self.app.root, agent, target, prompt, None, ()
        )
        return self.guard.check(self.app, event)


def test_usage_pause_blocks_the_launch_with_its_reason(tmp_path: Path) -> None:
    rig = _Rig(tmp_path)
    rig.usage.result = UsageCheck(UsageVerdict.PAUSE, "5-hour usage 90% ≥ 85%", NOW)
    decision = rig.launch()
    assert not decision.allow
    assert "5-hour usage 90% ≥ 85%" in decision.message


def test_launch_is_allowed_when_usage_is_ok(tmp_path: Path) -> None:
    rig = _Rig(tmp_path)
    rig.usage.result = UsageCheck(UsageVerdict.OK, "fine", None)
    assert rig.launch().allow


def test_waiting_for_approval_blocks_the_launch(tmp_path: Path) -> None:
    rig = _Rig(tmp_path)
    rig.store.status = replace(
        rig.store.status, waiting=Waiting("Counter", "api changed", NOW)
    )
    decision = rig.launch()
    assert not decision.allow
    assert (
        "waiting for the human to approve the Counter contract change"
        in decision.message
    )


def test_unknown_usage_allows_with_a_warning(tmp_path: Path) -> None:
    rig = _Rig(tmp_path)
    rig.usage.result = UsageCheck(UsageVerdict.UNKNOWN, "no usage data yet", None)
    decision = rig.launch()
    assert decision.allow
    assert decision.message != ""


@pytest.mark.parametrize("target", ["test-writer", "code-writer", "bull:code-writer"])
def test_prompt_naming_reference_folder_blocks_test_and_code_writers(
    tmp_path: Path, target: str
) -> None:
    (tmp_path / "reference").mkdir()
    decision = _Rig(tmp_path).launch(target, "look in reference/v1-tests for ideas")
    assert not decision.allow
    assert (
        "never give the reference folder to test-writer or code-writer"
        in decision.message
    )


def test_prompt_naming_reference_absolute_path_blocks(tmp_path: Path) -> None:
    (tmp_path / "reference").mkdir()
    prompt = f"read {tmp_path / 'reference'}/a.py"
    decision = _Rig(tmp_path).launch("test-writer", prompt)
    assert not decision.allow
    assert "never give the reference folder" in decision.message


def test_absolute_reference_dir_setting_is_matched_in_prompts(tmp_path: Path) -> None:
    ref = tmp_path / "elsewhere"
    ref.mkdir()
    decision = _Rig(tmp_path, str(ref)).launch("code-writer", f"see {ref}/x.py")
    assert not decision.allow


def test_reference_mention_is_allowed_when_the_folder_does_not_exist(
    tmp_path: Path,
) -> None:
    decision = _Rig(tmp_path).launch("code-writer", "look in reference/ please")
    assert decision.allow


@pytest.mark.parametrize("target", ["legacy-test-scanner", "reviewer", None])
def test_other_agents_may_be_given_the_reference_folder(
    tmp_path: Path, target: str | None
) -> None:
    (tmp_path / "reference").mkdir()
    decision = _Rig(tmp_path).launch(target, "scan reference/v1-tests")
    assert decision.allow


def test_prompt_without_reference_mention_is_allowed(tmp_path: Path) -> None:
    (tmp_path / "reference").mkdir()
    assert _Rig(tmp_path).launch("code-writer", "implement the counter").allow


def test_missing_prompt_is_allowed(tmp_path: Path) -> None:
    (tmp_path / "reference").mkdir()
    assert _Rig(tmp_path).launch("code-writer", None).allow


def test_allowed_launch_appends_agent_start_with_the_agent(tmp_path: Path) -> None:
    rig = _Rig(tmp_path)
    decision = rig.launch("code-writer", "implement")
    assert decision.allow
    starts = [e for e in rig.events.events if e.kind is EventKind.AGENT_START]
    assert len(starts) == 1
    assert starts[0].data["agent"] == "code-writer"


def test_blocked_launch_appends_no_agent_start(tmp_path: Path) -> None:
    rig = _Rig(tmp_path)
    rig.usage.result = UsageCheck(UsageVerdict.PAUSE, "too busy", NOW)
    rig.launch()
    assert [e for e in rig.events.events if e.kind is EventKind.AGENT_START] == []
