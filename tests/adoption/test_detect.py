"""Tests for `bull.Modules.adoption.detect`, reached through `LiveAdoption.detect`.

`LiveAdoption(files, git, runner, stacks, ops, parts, memo, settings, store, refs)` is built with
keyword arguments; `settings`, `store` and `refs` are callables taking the app layout.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path

import pytest

from bull.Modules.adoption.adopt import LiveAdoption
from bull.Modules.foundation.Contracts import RunResult
from bull.Modules.foundation.mocks import MockFiles, MockRunner
from bull.Modules.gitrepo.mocks import MockGit
from bull.Modules.memo.mocks import MockMemoReader
from bull.Modules.parts.mocks import MockParts, sample_part
from bull.Modules.settings.mocks import MockSettings
from bull.Modules.stacks.Contracts import (
    Detection,
    Issue,
    IssueLevel,
    Maturity,
    Stack,
)
from bull.Modules.stacks.mocks import (
    MockStackOps,
    MockStackRegistry,
    sample_stack,
)
from bull.Modules.status.mocks import MockRefs, MockStatusStore

FOR_EACH_REF = (
    "git",
    "for-each-ref",
    "--format=%(refname:short)",
    "refs/heads/module/",
    "refs/heads/feature/",
    "refs/heads/adopt/",
)


class RepoGit(MockGit):
    """MockGit whose toplevel, submodules and hooks can be set."""

    def __init__(self) -> None:
        super().__init__()
        self.top: Path | None = None
        self.top_is_root = True
        self.submodule_paths: list[str] = []
        self.hooks: list[str] = []

    def toplevel(self, path: Path) -> Path | None:
        self.calls.append(("toplevel", (path,)))
        if self.top_is_root:
            return path
        return self.top

    def submodules(self, root: Path) -> list[str]:
        self.calls.append(("submodules", (root,)))
        return list(self.submodule_paths)

    def active_hooks(self, root: Path) -> list[str]:
        self.calls.append(("active_hooks", (root,)))
        return list(self.hooks)


def _detection(
    confidence: float,
    summary: str = "found",
    settings: Mapping[str, str] | None = None,
    issues: tuple[Issue, ...] = (),
) -> Detection:
    return Detection(confidence, summary, settings or {}, issues)


def _with_detect(
    name: str,
    detect: Callable[[Path], Detection] | None,
    maturity: Maturity = Maturity.EXPERIMENTAL,
) -> Stack:
    base = sample_stack(name, maturity)
    return replace(base, optional=replace(base.optional, detect=detect))


class Rig:
    def __init__(self, tmp_path: Path) -> None:
        self.root = tmp_path
        self.files = MockFiles()
        self.git = RepoGit()
        self.runner = MockRunner()
        self.registry = MockStackRegistry()
        self.registry.stacks = {}
        self.ops = MockStackOps()
        self.parts = MockParts()
        self.parts.parts = [sample_part(tmp_path)]
        self.memo = MockMemoReader()
        self.settings = MockSettings()
        self.store = MockStatusStore()
        self.refs = MockRefs()
        self.adoption = LiveAdoption(
            files=self.files,
            git=self.git,
            runner=self.runner,
            stacks=self.registry,
            ops=self.ops,
            parts=self.parts,
            memo=self.memo,
            settings=lambda app: self.settings,
            store=lambda app: self.store,
            refs=lambda app: self.refs,
        )

    def add_stack(
        self,
        name: str,
        detection: Detection | None,
        maturity: Maturity = Maturity.EXPERIMENTAL,
    ) -> None:
        detect = None if detection is None else (lambda _root: detection)
        self.registry.stacks[name] = _with_detect(name, detect, maturity)

    def branches(self, *names: str) -> None:
        self.runner.results["git"] = RunResult(
            argv=FOR_EACH_REF,
            returncode=0,
            stdout="".join(f"{n}\n" for n in names),
            stderr="",
            seconds=0.01,
        )


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    return Rig(tmp_path)


def _names(calls: list[tuple[str, tuple[object, ...]]]) -> list[str]:
    return [name for name, _ in calls]


# --- stack choice ------------------------------------------------------------------------


def test_detect_chooses_the_stack_with_the_highest_confidence(rig: Rig) -> None:
    low = _detection(0.6, "low")
    high = _detection(0.9, "high")
    rig.add_stack("alpha", low)
    rig.add_stack("beta", high)
    report = rig.adoption.detect(rig.root)
    assert report.stack == "beta"
    assert report.detection is high


def test_detect_picks_the_best_whatever_the_registry_order(rig: Rig) -> None:
    rig.add_stack("alpha", _detection(0.95))
    rig.add_stack("beta", _detection(0.7))
    assert rig.adoption.detect(rig.root).stack == "alpha"


def test_detect_on_a_tie_picks_one_of_the_tied_stacks(rig: Rig) -> None:
    rig.add_stack("alpha", _detection(0.8))
    rig.add_stack("beta", _detection(0.8))
    report = rig.adoption.detect(rig.root)
    assert report.stack in {"alpha", "beta"}
    assert report.detection is not None
    assert report.detection.confidence == 0.8


def test_detect_ignores_confidence_of_exactly_half(rig: Rig) -> None:
    rig.add_stack("alpha", _detection(0.5))
    report = rig.adoption.detect(rig.root)
    assert report.stack is None
    assert report.detection is None


def test_detect_ignores_confidence_below_half(rig: Rig) -> None:
    rig.add_stack("alpha", _detection(0.1))
    assert rig.adoption.detect(rig.root).stack is None


def test_detect_chooses_a_stack_just_above_half(rig: Rig) -> None:
    rig.add_stack("alpha", _detection(0.51))
    assert rig.adoption.detect(rig.root).stack == "alpha"


def test_detect_skips_a_stack_whose_detect_raises(rig: Rig) -> None:
    def broken(_root: Path) -> Detection:
        raise ValueError("cannot read project")

    rig.registry.stacks["alpha"] = _with_detect("alpha", broken)
    rig.add_stack("beta", _detection(0.6))
    assert rig.adoption.detect(rig.root).stack == "beta"


def test_detect_with_only_a_raising_stack_finds_no_stack(rig: Rig) -> None:
    def broken(_root: Path) -> Detection:
        raise ValueError("cannot read project")

    rig.registry.stacks["alpha"] = _with_detect("alpha", broken)
    assert rig.adoption.detect(rig.root).stack is None


def test_detect_skips_stacks_without_a_detect_reader(rig: Rig) -> None:
    rig.add_stack("alpha", None)
    rig.add_stack("beta", _detection(0.7))
    assert rig.adoption.detect(rig.root).stack == "beta"


def test_detect_includes_test_stacks(rig: Rig) -> None:
    rig.registry.stacks["fixture"] = _with_detect(
        "fixture", lambda _root: _detection(0.9), Maturity.TEST
    )
    # The mock registry hides test-maturity stacks unless include_test is True.
    assert rig.adoption.detect(rig.root).stack == "fixture"
    assert ("all", (True,)) in rig.registry.calls


def test_detect_passes_the_root_to_each_stack(rig: Rig) -> None:
    seen: list[Path] = []

    def detect(root: Path) -> Detection:
        seen.append(root)
        return _detection(0.9)

    rig.registry.stacks["alpha"] = _with_detect("alpha", detect)
    rig.adoption.detect(rig.root)
    assert seen == [rig.root]


def test_detect_puts_the_winners_issues_before_bulls(rig: Rig) -> None:
    own = Issue(IssueLevel.FIX, "stack thing", "do it")
    rig.add_stack("alpha", _detection(0.9, issues=(own,)))
    rig.git.clean = False
    report = rig.adoption.detect(rig.root)
    assert report.issues[0] == own
    assert report.issues[1] == Issue(
        IssueLevel.FIX, "uncommitted changes", "commit or stash them"
    )


def test_detect_leaves_out_the_issues_of_stacks_that_lose(rig: Rig) -> None:
    loser = Issue(IssueLevel.BLOCK, "loser problem", "n/a")
    rig.add_stack("alpha", _detection(0.6, issues=(loser,)))
    rig.add_stack("beta", _detection(0.9))
    report = rig.adoption.detect(rig.root)
    assert loser not in report.issues


# --- bull's own issues ---------------------------------------------------------------------


def test_clean_repo_has_no_issues(rig: Rig) -> None:
    rig.add_stack("alpha", _detection(0.9))
    report = rig.adoption.detect(rig.root)
    assert report.issues == ()
    assert not report.blocked


def test_detect_blocks_when_not_the_root_of_its_own_repo(
    rig: Rig, tmp_path: Path
) -> None:
    rig.add_stack("alpha", _detection(0.9))
    rig.git.top_is_root = False
    rig.git.top = tmp_path.parent
    report = rig.adoption.detect(rig.root)
    assert report.issues == (
        Issue(
            IssueLevel.BLOCK,
            "not the root of its own git repository",
            "run bull from the repository root, or `git init`",
        ),
    )
    assert report.blocked


def test_detect_blocks_when_not_in_a_repo_at_all(rig: Rig) -> None:
    rig.add_stack("alpha", _detection(0.9))
    rig.git.top_is_root = False
    rig.git.top = None
    report = rig.adoption.detect(rig.root)
    assert [i.item for i in report.issues] == ["not the root of its own git repository"]
    assert report.blocked


def test_first_check_failure_skips_the_other_repo_checks(rig: Rig) -> None:
    rig.add_stack("alpha", _detection(0.9))
    rig.git.top_is_root = False
    rig.git.top = None
    rig.git.submodule_paths = ["vendor/lib"]
    rig.git.hooks = ["pre-commit"]
    rig.git.clean = False
    rig.git.tag_names = ["module/Counter"]
    rig.branches("module/Counter")
    report = rig.adoption.detect(rig.root)
    assert len(report.issues) == 1
    skipped = {"submodules", "tags", "active_hooks", "is_clean"}
    assert not skipped & set(_names(rig.git.calls))
    assert not any(name == "run" for name, _ in rig.runner.calls)


def test_detect_blocks_on_each_git_submodule(rig: Rig) -> None:
    rig.add_stack("alpha", _detection(0.9))
    rig.git.submodule_paths = ["vendor/lib", "third/party"]
    report = rig.adoption.detect(rig.root)
    fix = "remove the submodule or vendor its files"
    assert report.issues == (
        Issue(IssueLevel.BLOCK, "git submodule vendor/lib", fix),
        Issue(IssueLevel.BLOCK, "git submodule third/party", fix),
    )
    assert report.blocked


def test_detect_lists_clashing_branches_through_for_each_ref(rig: Rig) -> None:
    rig.add_stack("alpha", _detection(0.9))
    rig.branches("module/Counter", "feature/x/main", "adopt/main")
    report = rig.adoption.detect(rig.root)
    fix = "rename or delete it"
    assert report.issues == (
        Issue(
            IssueLevel.FIX,
            "branch module/Counter clashes with bull's branch names",
            fix,
        ),
        Issue(
            IssueLevel.FIX,
            "branch feature/x/main clashes with bull's branch names",
            fix,
        ),
        Issue(
            IssueLevel.FIX, "branch adopt/main clashes with bull's branch names", fix
        ),
    )
    assert not report.blocked


def test_detect_asks_git_for_clashing_branches_in_the_repo_root(rig: Rig) -> None:
    rig.add_stack("alpha", _detection(0.9))
    rig.adoption.detect(rig.root)
    runs = [args for name, args in rig.runner.calls if name == "run"]
    assert runs
    argv, cwd, _env, _timeout = runs[0]
    assert argv == FOR_EACH_REF
    assert cwd == rig.root


def test_detect_ignores_blank_lines_in_the_branch_listing(rig: Rig) -> None:
    rig.add_stack("alpha", _detection(0.9))
    rig.runner.results["git"] = RunResult(FOR_EACH_REF, 0, "\nmodule/A\n\n", "", 0.01)
    report = rig.adoption.detect(rig.root)
    assert [i.item for i in report.issues] == [
        "branch module/A clashes with bull's branch names"
    ]


def test_detect_lists_clashing_tags_for_each_prefix(rig: Rig) -> None:
    rig.add_stack("alpha", _detection(0.9))
    rig.git.tag_names = [
        "v1.0",
        "module/Counter",
        "feature/x/ui-approved",
        "adopt/setup",
    ]
    report = rig.adoption.detect(rig.root)
    fix = "rename or delete it"
    assert report.issues == (
        Issue(IssueLevel.FIX, "tag module/Counter clashes with bull's tag names", fix),
        Issue(
            IssueLevel.FIX,
            "tag feature/x/ui-approved clashes with bull's tag names",
            fix,
        ),
        Issue(IssueLevel.FIX, "tag adopt/setup clashes with bull's tag names", fix),
    )


def test_detect_asks_for_tags_matching_each_bull_prefix(rig: Rig) -> None:
    rig.add_stack("alpha", _detection(0.9))
    rig.adoption.detect(rig.root)
    patterns = {args[1] for name, args in rig.git.calls if name == "tags"}
    assert patterns == {"module/*", "feature/*", "adopt/*"}


def test_detect_notes_each_active_git_hook(rig: Rig) -> None:
    rig.add_stack("alpha", _detection(0.9))
    rig.git.hooks = ["pre-commit", "pre-push"]
    report = rig.adoption.detect(rig.root)
    fix = "bull's gates do not run it"
    assert report.issues == (
        Issue(IssueLevel.NOTE, "active git hook pre-commit", fix),
        Issue(IssueLevel.NOTE, "active git hook pre-push", fix),
    )
    assert not report.blocked


def test_detect_asks_to_fix_a_dirty_tree(rig: Rig) -> None:
    rig.add_stack("alpha", _detection(0.9))
    rig.git.clean = False
    report = rig.adoption.detect(rig.root)
    assert report.issues == (
        Issue(IssueLevel.FIX, "uncommitted changes", "commit or stash them"),
    )
    assert not report.blocked


def test_bull_issues_come_in_a_fixed_order(rig: Rig) -> None:
    own = Issue(IssueLevel.NOTE, "stack note", "")
    rig.add_stack("alpha", _detection(0.9, issues=(own,)))
    rig.git.submodule_paths = ["vendor/lib"]
    rig.branches("module/A")
    rig.git.tag_names = ["module/B"]
    rig.git.hooks = ["pre-commit"]
    rig.git.clean = False
    report = rig.adoption.detect(rig.root)
    assert [i.item for i in report.issues] == [
        "stack note",
        "git submodule vendor/lib",
        "branch module/A clashes with bull's branch names",
        "tag module/B clashes with bull's tag names",
        "active git hook pre-commit",
        "uncommitted changes",
    ]


# --- no stack ---------------------------------------------------------------------------------


NO_STACK = Issue(
    IssueLevel.BLOCK,
    "no stack recognizes this project",
    "pick one with `bull stack detect --apply <stack>` or `bull stack select`",
)


def test_no_stack_reports_a_blocking_issue(rig: Rig) -> None:
    report = rig.adoption.detect(rig.root)
    assert report.stack is None
    assert report.detection is None
    assert report.issues == (NO_STACK,)
    assert report.blocked


def test_no_stack_issue_comes_before_bulls_repo_issues(rig: Rig) -> None:
    rig.git.clean = False
    rig.git.hooks = ["pre-commit"]
    report = rig.adoption.detect(rig.root)
    assert report.issues[0] == NO_STACK
    assert [i.item for i in report.issues[1:]] == [
        "active git hook pre-commit",
        "uncommitted changes",
    ]


def test_no_stack_issue_comes_before_the_not_a_root_issue(rig: Rig) -> None:
    rig.git.top_is_root = False
    rig.git.top = None
    report = rig.adoption.detect(rig.root)
    assert [i.item for i in report.issues] == [
        "no stack recognizes this project",
        "not the root of its own git repository",
    ]


def test_detect_changes_nothing(rig: Rig) -> None:
    rig.add_stack("alpha", _detection(0.9))
    rig.adoption.detect(rig.root)
    assert rig.files.calls == []
    assert rig.ops.calls == []
    assert rig.store.calls == []
    assert not {"commit_all", "create_branch", "switch", "tag"} & set(
        _names(rig.git.calls)
    )
