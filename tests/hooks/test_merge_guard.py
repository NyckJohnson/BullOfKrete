"""Tests for `bull.Modules.hooks.merge_guard`: `git merge` parsing and the gate-pass guard."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from pathlib import Path

import pytest

from bull.Modules.events.Contracts import EventKind
from bull.Modules.events.mocks import MockEventLog
from bull.Modules.foundation.Contracts import AppLayout
from bull.Modules.gates.mocks import MockPassRecords
from bull.Modules.gitrepo.mocks import MockGit
from bull.Modules.hooks.merge_guard import MergeGuard, merge_targets
from bull.Modules.status.Contracts import ScanRecord
from bull.Modules.status.mocks import MockRefs, MockStatusStore, sample_status

SHA_A = "a" * 40
SHA_B = "b" * 40


# --- merge_targets


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("git merge feature", ["feature"]),
        ("git merge --no-ff module/Counter", ["module/Counter"]),
        ("git merge --no-ff -m 'merge counter' module/Counter", ["module/Counter"]),
        ("git merge -m message feature", ["feature"]),
        ("git merge feature -m message", ["feature"]),
        ("git merge --no-ff --message=hello feature", ["feature"]),
        ("git merge -s ours feature", ["feature"]),
        ("git merge -m 'a; b && c' feature", ["feature"]),
        ("git -C /tmp/some/app merge feature", ["feature"]),
        ("git -C ../app merge --no-ff module/Store", ["module/Store"]),
        ("git merge a b", ["a", "b"]),
        ("git merge a && git merge b", ["a", "b"]),
        ("git merge a || git merge b", ["a", "b"]),
        ("git merge a; git merge b", ["a", "b"]),
        ("git merge a | git merge b", ["a", "b"]),
        ("git merge a\ngit merge b", ["a", "b"]),
        ("git switch main && git merge --no-ff module/Counter", ["module/Counter"]),
        ("echo hi; git merge feature; echo done", ["feature"]),
        ("git merge feature > out.txt", ["feature"]),
        ("git merge feature 2>&1", ["feature"]),
        ("git merge feature 2>/dev/null", ["feature"]),
        ("git merge feature >> log.txt 2>&1", ["feature"]),
        ("git -c k=v merge x", ["x"]),
        ("git merge -- x", ["x"]),
        ("a & git merge x", ["x"]),
        ("git merge x &", ["x"]),
        ("(git merge x)", ["x"]),
        ("$(git merge x)", ["x"]),
        ("git merge -mmsg x", ["x"]),
        ("git merge --into-name=a x", ["x"]),
        ("git merge -m 'a & b' x", ["x"]),
        ('git merge -m "a ; b" x', ["x"]),
        ("git merge --continue x", []),
        ("git merge --cleanup strip x", ["x"]),
        ("git merge --abort", []),
        ("git merge --continue", []),
        ("git merge --quit", []),
        ("git -C /x merge --abort", []),
        ("git merge --abort && git merge feature", ["feature"]),
        ("git status", []),
        ("git commit -m done", []),
        ("echo merge", []),
        ("", []),
        ("   ", []),
    ],
)
def test_merge_targets_parses_git_merge_commands(
    command: str, expected: list[str]
) -> None:
    assert merge_targets(command) == expected


# --- the guard


@dataclasses.dataclass
class Rig:
    app: AppLayout
    git: MockGit
    passes: MockPassRecords
    store: MockStatusStore
    events: MockEventLog
    guard: MergeGuard


def _layout(root: Path) -> AppLayout:
    values = {f.name: root / f.name for f in dataclasses.fields(AppLayout)}
    values["root"] = root
    return AppLayout(**values)


def _rig(tmp_path: Path) -> Rig:
    git = MockGit()
    git.heads["module/Counter"] = SHA_A
    git.heads["feature/x"] = SHA_B
    passes = MockPassRecords()
    store = MockStatusStore(sample_status())
    events = MockEventLog()
    events.events.clear()
    guard = MergeGuard(git, passes, MockRefs(), store, events)
    return Rig(_layout(tmp_path), git, passes, store, events, guard)


def _record(rig: Rig, sha: str, branch: str) -> None:
    rig.passes.record(rig.app, sha, branch, "bull gates", ("app",))


def _needs_scan(rig: Rig, scan: ScanRecord | None) -> None:
    status = rig.store.status
    modules = tuple(
        dataclasses.replace(m, reference_tests=True, scan=scan)
        if m.name == "Counter"
        else m
        for m in status.modules
    )
    rig.store.status = dataclasses.replace(status, modules=modules)


def _blocks(rig: Rig) -> list[str]:
    return [e.kind.value for e in rig.events.events if e.kind is EventKind.HOOK_BLOCK]


def test_command_without_a_merge_is_allowed(tmp_path: Path) -> None:
    rig = _rig(tmp_path)
    decision = rig.guard.check(rig.app, "git status && ls")
    assert decision.allow
    assert decision.message == ""
    assert _blocks(rig) == []


def test_merge_of_a_branch_with_a_recorded_pass_is_allowed(tmp_path: Path) -> None:
    rig = _rig(tmp_path)
    _record(rig, SHA_B, "feature/x")
    decision = rig.guard.check(rig.app, "git merge --no-ff feature/x")
    assert decision.allow
    assert _blocks(rig) == []


def test_merge_of_an_unknown_ref_is_blocked(tmp_path: Path) -> None:
    rig = _rig(tmp_path)
    decision = rig.guard.check(rig.app, "git merge nonexistent")
    assert not decision.allow
    assert "nonexistent" in decision.message


def test_merge_without_a_pass_record_is_blocked_naming_ref_and_sha(
    tmp_path: Path,
) -> None:
    rig = _rig(tmp_path)
    decision = rig.guard.check(rig.app, "git merge feature/x")
    assert not decision.allow
    assert f"no recorded full gate pass for feature/x at {SHA_B}" in decision.message
    assert "bull gates" in decision.message


def test_a_pass_for_another_sha_does_not_allow_the_merge(tmp_path: Path) -> None:
    rig = _rig(tmp_path)
    _record(rig, SHA_A, "feature/x")
    decision = rig.guard.check(rig.app, "git merge feature/x")
    assert not decision.allow


def test_module_branch_with_reference_tests_and_no_scan_is_blocked(
    tmp_path: Path,
) -> None:
    rig = _rig(tmp_path)
    _record(rig, SHA_A, "module/Counter")
    _needs_scan(rig, None)
    decision = rig.guard.check(rig.app, "git merge --no-ff module/Counter")
    assert not decision.allow
    assert "record the reference-test scan for Counter first" in decision.message


def test_module_branch_with_reference_tests_and_a_scan_is_allowed(
    tmp_path: Path,
) -> None:
    rig = _rig(tmp_path)
    _record(rig, SHA_A, "module/Counter")
    scan = ScanRecord(datetime(2026, 11, 7, tzinfo=UTC), 3, 1, 0, 0)
    _needs_scan(rig, scan)
    assert rig.guard.check(rig.app, "git merge --no-ff module/Counter").allow


def test_module_branch_without_reference_tests_needs_no_scan(tmp_path: Path) -> None:
    rig = _rig(tmp_path)
    _record(rig, SHA_A, "module/Counter")
    assert rig.guard.check(rig.app, "git merge --no-ff module/Counter").allow


def test_every_target_in_the_command_is_checked(tmp_path: Path) -> None:
    rig = _rig(tmp_path)
    _record(rig, SHA_B, "feature/x")
    decision = rig.guard.check(rig.app, "git merge feature/x && git merge ghost")
    assert not decision.allow
    assert "ghost" in decision.message


def test_a_second_target_without_a_pass_blocks_the_whole_command(
    tmp_path: Path,
) -> None:
    rig = _rig(tmp_path)
    _record(rig, SHA_B, "feature/x")
    decision = rig.guard.check(rig.app, "git merge feature/x; git merge module/Counter")
    assert not decision.allow
    assert SHA_A in decision.message


def test_aborting_a_merge_is_never_blocked(tmp_path: Path) -> None:
    rig = _rig(tmp_path)
    assert rig.guard.check(rig.app, "git merge --abort").allow


def test_a_block_appends_a_hook_block_event(tmp_path: Path) -> None:
    rig = _rig(tmp_path)
    rig.guard.check(rig.app, "git merge feature/x")
    assert len(_blocks(rig)) == 1


def test_each_kind_of_block_appends_a_hook_block_event(tmp_path: Path) -> None:
    rig = _rig(tmp_path)
    rig.guard.check(rig.app, "git merge ghost")
    _record(rig, SHA_A, "module/Counter")
    _needs_scan(rig, None)
    rig.guard.check(rig.app, "git merge module/Counter")
    assert len(_blocks(rig)) == 2


def test_an_allowed_merge_appends_no_event(tmp_path: Path) -> None:
    rig = _rig(tmp_path)
    _record(rig, SHA_B, "feature/x")
    rig.guard.check(rig.app, "git merge feature/x")
    assert rig.events.events == []
