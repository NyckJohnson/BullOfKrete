"""Tests for `bull.Modules.hooks.merge_guard`: `git merge` parsing and the gate-pass guard."""

from __future__ import annotations

import dataclasses
import json
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


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("GIT_EDITOR=true git merge feature/a/main", ["feature/a/main"]),
        ("env X=1 git merge x", ["x"]),
        ("command git merge x", ["x"]),
        ("exec git merge x", ["x"]),
        ("time git merge x", ["x"]),
        ("nohup git merge x", ["x"]),
        ("sudo git merge x", ["x"]),
        ("{ git merge x; }", ["x"]),
        ("! git merge x", ["x"]),
        ("if true; then git merge x; fi", ["x"]),
        ("for b in a; do git merge x; done", ["x"]),
        ("if false; then :; else git merge x; fi", ["x"]),
        ("sh -c 'git merge x'", ["x"]),
        ('bash -c "git merge x && git merge y"', ["x", "y"]),
        ('echo "git merge fake"', []),
        ("git log --merges", []),
        ("git mergetool", []),
    ],
)
def test_merge_targets_sees_through_wrappers_and_ignores_quoted_text(
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


STATUS_PATH = ".bull/status.json"
SCAN_JSON = {
    "time": "2026-11-07T00:00:00+00:00",
    "covered": 3,
    "missed": 1,
    "contradicts": 0,
    "not_in_spec": 0,
}


def _branch_status(
    rig: Rig, sha: str, *, reference_tests: bool, scan: bool, text: str | None = None
) -> None:
    """Put a `.bull/status.json` at `sha` as the module branch committed it."""
    if text is None:
        text = json.dumps(
            {
                "format": 1,
                "kind": "app",
                "stage": 5,
                "checkpoints": [],
                "modules": [
                    {
                        "name": "Counter",
                        "part": "app",
                        "depends": [],
                        "state": "in_progress",
                        "reference_tests": reference_tests,
                        "scan": SCAN_JSON if scan else None,
                        "units": [],
                    }
                ],
                "pause": None,
                "waiting": None,
                "approvals": [],
                "plan": None,
                "feature": None,
                "adoption": None,
            }
        )
    rig.git.files_at[(sha, STATUS_PATH)] = text


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
    _branch_status(rig, SHA_A, reference_tests=True, scan=False)
    decision = rig.guard.check(rig.app, "git merge --no-ff module/Counter")
    assert not decision.allow
    assert "record the reference-test scan for Counter first" in decision.message


def test_module_branch_with_reference_tests_and_a_scan_is_allowed(
    tmp_path: Path,
) -> None:
    rig = _rig(tmp_path)
    _record(rig, SHA_A, "module/Counter")
    _branch_status(rig, SHA_A, reference_tests=True, scan=True)
    assert rig.guard.check(rig.app, "git merge --no-ff module/Counter").allow


def test_scan_recorded_only_on_the_branch_head_allows_the_merge(
    tmp_path: Path,
) -> None:
    rig = _rig(tmp_path)
    _record(rig, SHA_A, "module/Counter")
    _needs_scan(rig, None)
    _branch_status(rig, SHA_A, reference_tests=True, scan=True)
    assert rig.guard.check(rig.app, "git merge --no-ff module/Counter").allow


def test_branch_without_a_scan_blocks_even_when_the_working_tree_has_one(
    tmp_path: Path,
) -> None:
    rig = _rig(tmp_path)
    _record(rig, SHA_A, "module/Counter")
    _needs_scan(rig, ScanRecord(datetime(2026, 11, 7, tzinfo=UTC), 3, 1, 0, 0))
    _branch_status(rig, SHA_A, reference_tests=True, scan=False)
    decision = rig.guard.check(rig.app, "git merge --no-ff module/Counter")
    assert not decision.allow
    assert "record the reference-test scan for Counter first" in decision.message


def test_branch_status_is_read_at_the_head_sha_of_the_target(tmp_path: Path) -> None:
    rig = _rig(tmp_path)
    _record(rig, SHA_A, "module/Counter")
    _branch_status(rig, SHA_A, reference_tests=True, scan=True)
    rig.guard.check(rig.app, "git merge --no-ff module/Counter")
    asked = [c for c in rig.git.calls if c[0] == "show_file"]
    assert asked
    assert all(c[1][1] == SHA_A and c[1][2] == STATUS_PATH for c in asked)


def test_status_file_at_another_sha_is_not_used(tmp_path: Path) -> None:
    rig = _rig(tmp_path)
    _record(rig, SHA_A, "module/Counter")
    _needs_scan(rig, None)
    _branch_status(rig, SHA_B, reference_tests=True, scan=True)
    decision = rig.guard.check(rig.app, "git merge --no-ff module/Counter")
    assert not decision.allow


@pytest.mark.parametrize("scan_in_working_tree", [True, False])
def test_branch_without_a_status_file_falls_back_to_the_working_tree(
    tmp_path: Path, scan_in_working_tree: bool
) -> None:
    rig = _rig(tmp_path)
    _record(rig, SHA_A, "module/Counter")
    scan = (
        ScanRecord(datetime(2026, 11, 7, tzinfo=UTC), 3, 1, 0, 0)
        if scan_in_working_tree
        else None
    )
    _needs_scan(rig, scan)
    decision = rig.guard.check(rig.app, "git merge --no-ff module/Counter")
    assert decision.allow is scan_in_working_tree


def _one_module(**overrides: object) -> str:
    module: dict[str, object] = {
        "name": "Counter",
        "part": "app",
        "depends": [],
        "state": "in_progress",
        "reference_tests": True,
        "scan": None,
        "units": [],
    }
    module.update(overrides)
    return json.dumps({"format": 1, "modules": [module]})


@pytest.mark.parametrize(
    "text",
    [
        "",
        "not json {",
        "[1, 2]",
        '{"unrelated": true}',
        json.dumps({"format": 1, "modules": [1]}),
        _one_module(name=5),
        _one_module(reference_tests="yes"),
        _one_module(scan=5),
    ],
)
@pytest.mark.parametrize("scan_in_working_tree", [True, False])
def test_branch_status_that_is_not_valid_status_json_falls_back_to_the_working_tree(
    tmp_path: Path, text: str, scan_in_working_tree: bool
) -> None:
    rig = _rig(tmp_path)
    _record(rig, SHA_A, "module/Counter")
    scan = (
        ScanRecord(datetime(2026, 11, 7, tzinfo=UTC), 3, 1, 0, 0)
        if scan_in_working_tree
        else None
    )
    _needs_scan(rig, scan)
    _branch_status(rig, SHA_A, reference_tests=True, scan=False, text=text)
    decision = rig.guard.check(rig.app, "git merge --no-ff module/Counter")
    assert decision.allow is scan_in_working_tree


def test_branch_without_reference_tests_needs_no_scan_even_if_working_tree_does(
    tmp_path: Path,
) -> None:
    rig = _rig(tmp_path)
    _record(rig, SHA_A, "module/Counter")
    _needs_scan(rig, None)
    _branch_status(rig, SHA_A, reference_tests=False, scan=False)
    assert rig.guard.check(rig.app, "git merge --no-ff module/Counter").allow


def test_branch_status_blocking_leaves_a_hook_block_event(tmp_path: Path) -> None:
    rig = _rig(tmp_path)
    _record(rig, SHA_A, "module/Counter")
    _branch_status(rig, SHA_A, reference_tests=True, scan=False)
    rig.guard.check(rig.app, "git merge --no-ff module/Counter")
    assert len(_blocks(rig)) == 1


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


def test_unknown_ref_message_says_unknown_ref_and_names_it(tmp_path: Path) -> None:
    rig = _rig(tmp_path)
    decision = rig.guard.check(rig.app, "git merge ghost")
    assert not decision.allow
    assert "unknown ref ghost" in decision.message


def test_block_message_never_contains_shell_redirection_fragments(
    tmp_path: Path,
) -> None:
    rig = _rig(tmp_path)
    decision = rig.guard.check(
        rig.app, "git merge --no-ff module/Counter 2>&1 | tail -3"
    )
    assert not decision.allow
    assert "module/Counter" in decision.message
    assert "2>&1" not in decision.message


# --- coverage triage: quoting, comments, wrappers


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("echo ok # git merge x", []),
        ("git merge \\\nfeature/x", ["feature/x"]),
        ("git merge feat\\ x", ["feat x"]),
        ("git merge x\\", ["x"]),
        ('git merge "a\\"b"', ['a"b']),
        ('echo "x\\"; git merge y"', []),
        ("sudo -- git merge x", ["x"]),
        ("env -- git merge x", ["x"]),
        ("sudo -u root git merge x", ["x"]),
        ("sudo -E git merge x", ["x"]),
        ("sudo", []),
        ("env FOO=1", []),
        ("sudo -u root", []),
        ("bash -x script.sh", []),
        ("bash -c", []),
    ],
)
def test_merge_targets_handles_escapes_comments_and_wrapper_options(
    command: str, expected: list[str]
) -> None:
    assert merge_targets(command) == expected


def test_trailing_lone_backslash_does_not_crash() -> None:
    assert isinstance(merge_targets("git merge x \\"), list)


def test_module_branch_absent_from_status_with_a_pass_is_allowed(
    tmp_path: Path,
) -> None:
    rig = _rig(tmp_path)
    rig.git.heads["module/Ghost"] = SHA_A
    _record(rig, SHA_A, "module/Ghost")
    assert rig.guard.check(rig.app, "git merge --no-ff module/Ghost").allow
