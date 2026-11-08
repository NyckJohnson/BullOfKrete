"""Tests for `bull.Modules.gitrepo.mocks` (the fake Git other modules' tests use)."""

from __future__ import annotations

from pathlib import Path

from bull.Modules.gitrepo.Contracts import Git
from bull.Modules.gitrepo.mocks import SAMPLE_SHA, MockGit

ROOT = Path("/tmp/apps/tally")


def test_mock_git_satisfies_the_protocol() -> None:
    git: Git = MockGit()
    assert git.is_repo(ROOT) is True


def test_mock_starts_on_main_with_a_sample_head_and_is_clean() -> None:
    git = MockGit()
    assert git.current_branch(ROOT) == "main"
    assert git.head(ROOT) == SAMPLE_SHA
    assert git.is_clean(ROOT) is True
    assert git.branch_exists(ROOT, "main") is True


def test_mock_head_of_unknown_ref_is_none() -> None:
    assert MockGit().head(ROOT, "nope") is None


def test_mock_is_clean_follows_the_clean_attribute() -> None:
    git = MockGit()
    git.clean = False
    assert git.is_clean(ROOT) is False


def test_mock_toplevel_returns_the_path() -> None:
    assert MockGit().toplevel(ROOT) == ROOT


def test_mock_init_sets_branch() -> None:
    git = MockGit()
    git.init(ROOT, "trunk")
    assert git.current_branch(ROOT) == "trunk"
    assert git.branch_exists(ROOT, "trunk") is True


def test_mock_create_branch_switches_by_default() -> None:
    git = MockGit()
    git.create_branch(ROOT, "feature", "main")
    assert git.branch_exists(ROOT, "feature") is True
    assert git.current_branch(ROOT) == "feature"
    assert git.head(ROOT, "feature") == SAMPLE_SHA


def test_mock_create_branch_without_switch_stays_put() -> None:
    git = MockGit()
    git.create_branch(ROOT, "feature", "main", switch=False)
    assert git.branch_exists(ROOT, "feature") is True
    assert git.current_branch(ROOT) == "main"


def test_mock_switch_changes_current_branch() -> None:
    git = MockGit()
    git.create_branch(ROOT, "other", "main", switch=False)
    git.switch(ROOT, "other")
    assert git.current_branch(ROOT) == "other"


def test_mock_commit_all_returns_distinct_shas_and_moves_head() -> None:
    git = MockGit()
    first = git.commit_all(ROOT, "one")
    second = git.commit_all(ROOT, "two")
    assert first is not None and second is not None
    assert first != second
    assert git.head(ROOT) == second
    assert len(second) == 40


def test_mock_tag_is_recorded_and_tags_are_sorted_and_filtered() -> None:
    git = MockGit()
    git.tag(ROOT, "module/a")
    git.tag(ROOT, "module/b")
    assert git.tags(ROOT, "module/*") == ["module/a", "module/b"]
    assert git.tags(ROOT) == sorted(git.tags(ROOT))
    assert "setup" in git.tags(ROOT)


def test_mock_changed_paths_returns_sorted_configured_paths() -> None:
    git = MockGit()
    git.changed = ["b.txt", "a.txt"]
    assert git.changed_paths(ROOT, "x", "y") == ["a.txt", "b.txt"]


def test_mock_show_file_returns_configured_content_or_none() -> None:
    git = MockGit()
    git.files_at[("HEAD", "a.txt")] = "hello"
    assert git.show_file(ROOT, "HEAD", "a.txt") == "hello"
    assert git.show_file(ROOT, "HEAD", "missing.txt") is None


def test_mock_parents_submodules_and_hooks_have_benign_defaults() -> None:
    git = MockGit()
    assert git.parents(ROOT, "HEAD") == [SAMPLE_SHA]
    assert git.submodules(ROOT) == []
    assert git.active_hooks(ROOT) == []


def test_mock_records_calls_in_order() -> None:
    git = MockGit()
    git.is_clean(ROOT)
    git.commit_all(ROOT, "msg")
    assert [name for name, _ in git.calls] == ["is_clean", "commit_all"]
    assert git.calls[1][1] == (ROOT, "msg")
