"""Tests for `bull.Modules.gitrepo.git` against real git in temporary repos."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from bull.Modules.foundation.Contracts import RunResult
from bull.Modules.foundation.mocks import MockRunner
from bull.Modules.foundation.runner import LiveRunner
from bull.Modules.gitrepo.Contracts import GitError
from bull.Modules.gitrepo.git import LiveGit


@pytest.fixture(autouse=True)
def isolated_git_env(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@example.com")
    yield


def sh(root: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    )
    return done.stdout.strip()


def write(root: Path, name: str, text: str = "x\n") -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture
def git() -> LiveGit:
    return LiveGit(LiveRunner())


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repo on `main` with one commit containing a.txt."""
    root = tmp_path / "repo"
    root.mkdir()
    sh(root, "init", "-b", "main")
    sh(root, "config", "user.name", "Test")
    sh(root, "config", "user.email", "test@example.com")
    write(root, "a.txt", "one\n")
    sh(root, "add", "-A")
    sh(root, "commit", "-m", "first")
    return root


# --- is_repo, toplevel, init


def test_is_repo_true_inside_a_repo(git: LiveGit, repo: Path) -> None:
    assert git.is_repo(repo) is True


def test_is_repo_true_in_a_subfolder(git: LiveGit, repo: Path) -> None:
    (repo / "sub").mkdir()
    assert git.is_repo(repo / "sub") is True


def test_is_repo_false_outside_a_repo(git: LiveGit, tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    assert git.is_repo(plain) is False


def test_toplevel_of_a_subfolder_is_the_repo_root(git: LiveGit, repo: Path) -> None:
    (repo / "sub").mkdir()
    top = git.toplevel(repo / "sub")
    assert top is not None
    assert top.resolve() == repo.resolve()


def test_toplevel_outside_a_repo_is_none(git: LiveGit, tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    assert git.toplevel(plain) is None


def test_init_creates_a_repo_on_the_given_branch(git: LiveGit, tmp_path: Path) -> None:
    target = tmp_path / "fresh"
    target.mkdir()
    git.init(target, "trunk")
    assert git.is_repo(target) is True
    assert sh(target, "symbolic-ref", "--short", "HEAD") == "trunk"


# --- current_branch, head


def test_current_branch_names_the_branch(git: LiveGit, repo: Path) -> None:
    assert git.current_branch(repo) == "main"


def test_current_branch_is_none_when_head_is_detached(git: LiveGit, repo: Path) -> None:
    sh(repo, "checkout", "--detach")
    assert git.current_branch(repo) is None


def test_head_is_the_full_sha(git: LiveGit, repo: Path) -> None:
    sha = git.head(repo)
    assert sha == sh(repo, "rev-parse", "HEAD")
    assert sha is not None and len(sha) == 40


def test_head_of_a_named_ref(git: LiveGit, repo: Path) -> None:
    first = sh(repo, "rev-parse", "HEAD")
    sh(repo, "tag", "v1")
    write(repo, "b.txt")
    sh(repo, "add", "-A")
    sh(repo, "commit", "-m", "second")
    assert git.head(repo, "v1") == first
    assert git.head(repo) != first


def test_head_of_unknown_ref_is_none(git: LiveGit, repo: Path) -> None:
    assert git.head(repo, "no-such-ref") is None


# --- is_clean


def test_is_clean_true_for_a_fresh_commit(git: LiveGit, repo: Path) -> None:
    assert git.is_clean(repo) is True


def test_is_clean_false_with_staged_changes(git: LiveGit, repo: Path) -> None:
    write(repo, "b.txt")
    sh(repo, "add", "b.txt")
    assert git.is_clean(repo) is False


def test_is_clean_false_with_unstaged_changes(git: LiveGit, repo: Path) -> None:
    write(repo, "a.txt", "changed\n")
    assert git.is_clean(repo) is False


def test_is_clean_false_with_untracked_files(git: LiveGit, repo: Path) -> None:
    write(repo, "new.txt")
    assert git.is_clean(repo) is False


def test_is_clean_ignores_ignored_files(git: LiveGit, repo: Path) -> None:
    write(repo, ".gitignore", "*.log\n")
    sh(repo, "add", "-A")
    sh(repo, "commit", "-m", "ignore")
    write(repo, "debug.log")
    assert git.is_clean(repo) is True


# --- branches


def test_branch_exists_true_and_false(git: LiveGit, repo: Path) -> None:
    assert git.branch_exists(repo, "main") is True
    assert git.branch_exists(repo, "nope") is False


def test_create_branch_switches_by_default(git: LiveGit, repo: Path) -> None:
    git.create_branch(repo, "feature", "main")
    assert git.branch_exists(repo, "feature") is True
    assert git.current_branch(repo) == "feature"


def test_create_branch_without_switch_stays_on_current(
    git: LiveGit, repo: Path
) -> None:
    git.create_branch(repo, "feature", "main", switch=False)
    assert git.branch_exists(repo, "feature") is True
    assert git.current_branch(repo) == "main"


def test_create_branch_starts_at_the_given_ref(git: LiveGit, repo: Path) -> None:
    first = sh(repo, "rev-parse", "HEAD")
    write(repo, "b.txt")
    sh(repo, "add", "-A")
    sh(repo, "commit", "-m", "second")
    git.create_branch(repo, "old", first, switch=False)
    assert git.head(repo, "old") == first


def test_create_branch_with_existing_name_raises(git: LiveGit, repo: Path) -> None:
    with pytest.raises(GitError):
        git.create_branch(repo, "main", "main")


def test_switch_changes_branch(git: LiveGit, repo: Path) -> None:
    git.create_branch(repo, "other", "main", switch=False)
    git.switch(repo, "other")
    assert git.current_branch(repo) == "other"


def test_switch_to_unknown_branch_raises(git: LiveGit, repo: Path) -> None:
    with pytest.raises(GitError):
        git.switch(repo, "ghost")


# --- commit_all


def test_commit_all_stages_everything_and_returns_the_new_sha(
    git: LiveGit, repo: Path
) -> None:
    write(repo, "a.txt", "modified\n")
    write(repo, "new/deep.txt")
    sha = git.commit_all(repo, "everything")
    assert sha == sh(repo, "rev-parse", "HEAD")
    assert sh(repo, "log", "-1", "--format=%s") == "everything"
    assert sh(repo, "status", "--porcelain") == ""
    assert git.show_file(repo, "HEAD", "new/deep.txt") == "x\n"


def test_commit_all_includes_deletions(git: LiveGit, repo: Path) -> None:
    (repo / "a.txt").unlink()
    assert git.commit_all(repo, "remove") is not None
    assert git.show_file(repo, "HEAD", "a.txt") is None


def test_commit_all_with_nothing_to_commit_is_none(git: LiveGit, repo: Path) -> None:
    before = sh(repo, "rev-parse", "HEAD")
    assert git.commit_all(repo, "empty") is None
    assert sh(repo, "rev-parse", "HEAD") == before


# --- tag, tags


def test_tag_creates_a_tag_at_head(git: LiveGit, repo: Path) -> None:
    git.tag(repo, "v1")
    assert sh(repo, "rev-parse", "v1^{commit}") == sh(repo, "rev-parse", "HEAD")


def test_tag_at_a_given_ref(git: LiveGit, repo: Path) -> None:
    first = sh(repo, "rev-parse", "HEAD")
    write(repo, "b.txt")
    sh(repo, "add", "-A")
    sh(repo, "commit", "-m", "second")
    git.tag(repo, "old", first)
    assert sh(repo, "rev-parse", "old^{commit}") == first


def test_tag_with_existing_name_raises_git_error_naming_it(
    git: LiveGit, repo: Path
) -> None:
    git.tag(repo, "dupe-tag")
    with pytest.raises(GitError) as info:
        git.tag(repo, "dupe-tag")
    assert "dupe-tag" in str(info.value)


def test_tags_are_sorted(git: LiveGit, repo: Path) -> None:
    for name in ["zeta", "alpha", "module/b", "module/a"]:
        sh(repo, "tag", name)
    assert git.tags(repo) == ["alpha", "module/a", "module/b", "zeta"]


def test_tags_filtered_by_pattern(git: LiveGit, repo: Path) -> None:
    for name in ["module/b", "zeta", "module/a"]:
        sh(repo, "tag", name)
    assert git.tags(repo, "module/*") == ["module/a", "module/b"]


def test_tags_empty_when_none_match(git: LiveGit, repo: Path) -> None:
    assert git.tags(repo) == []
    sh(repo, "tag", "v1")
    assert git.tags(repo, "zzz*") == []


# --- changed_paths, show_file, parents


def test_changed_paths_are_sorted_names_between_commits(
    git: LiveGit, repo: Path
) -> None:
    first = sh(repo, "rev-parse", "HEAD")
    write(repo, "z.txt")
    write(repo, "dir/m.txt")
    write(repo, "a.txt", "changed\n")
    sh(repo, "add", "-A")
    sh(repo, "commit", "-m", "second")
    second = sh(repo, "rev-parse", "HEAD")
    assert git.changed_paths(repo, first, second) == ["a.txt", "dir/m.txt", "z.txt"]


def test_changed_paths_empty_for_identical_commits(git: LiveGit, repo: Path) -> None:
    assert git.changed_paths(repo, "HEAD", "HEAD") == []


def test_changed_paths_with_unknown_ref_raises(git: LiveGit, repo: Path) -> None:
    with pytest.raises(GitError):
        git.changed_paths(repo, "HEAD", "no-such-ref")


def test_show_file_returns_content_at_ref(git: LiveGit, repo: Path) -> None:
    first = sh(repo, "rev-parse", "HEAD")
    write(repo, "a.txt", "two\n")
    sh(repo, "add", "-A")
    sh(repo, "commit", "-m", "second")
    assert git.show_file(repo, first, "a.txt") == "one\n"
    assert git.show_file(repo, "HEAD", "a.txt") == "two\n"


def test_show_file_missing_path_is_none(git: LiveGit, repo: Path) -> None:
    assert git.show_file(repo, "HEAD", "missing.txt") is None


def test_show_file_with_unknown_ref_raises_git_error(git: LiveGit, repo: Path) -> None:
    with pytest.raises(GitError):
        git.show_file(repo, "no-such-ref", "a.txt")


def test_parents_of_root_commit_is_empty(git: LiveGit, repo: Path) -> None:
    assert git.parents(repo, "HEAD") == []


def test_parents_of_a_normal_commit_is_one_sha(git: LiveGit, repo: Path) -> None:
    first = sh(repo, "rev-parse", "HEAD")
    write(repo, "b.txt")
    sh(repo, "add", "-A")
    sh(repo, "commit", "-m", "second")
    assert git.parents(repo, "HEAD") == [first]


def test_parents_of_a_merge_commit_are_two_in_order(git: LiveGit, repo: Path) -> None:
    sh(repo, "checkout", "-b", "side")
    write(repo, "side.txt")
    sh(repo, "add", "-A")
    sh(repo, "commit", "-m", "side")
    side = sh(repo, "rev-parse", "HEAD")
    sh(repo, "checkout", "main")
    write(repo, "main.txt")
    sh(repo, "add", "-A")
    sh(repo, "commit", "-m", "main")
    main = sh(repo, "rev-parse", "HEAD")
    sh(repo, "merge", "--no-ff", "-m", "merge", "side")
    assert git.parents(repo, "HEAD") == [main, side]


# --- submodules, active_hooks


def test_submodules_empty_without_any(git: LiveGit, repo: Path) -> None:
    assert git.submodules(repo) == []


def test_submodules_lists_registered_paths(
    git: LiveGit, repo: Path, tmp_path: Path
) -> None:
    inner = tmp_path / "inner"
    inner.mkdir()
    sh(inner, "init", "-b", "main")
    sh(inner, "config", "user.name", "Test")
    sh(inner, "config", "user.email", "test@example.com")
    write(inner, "f.txt")
    sh(inner, "add", "-A")
    sh(inner, "commit", "-m", "inner")
    sh(
        repo,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        str(inner),
        "vendor/inner",
    )
    assert git.submodules(repo) == ["vendor/inner"]


def test_active_hooks_lists_only_executable_non_sample_hooks(
    git: LiveGit, repo: Path
) -> None:
    hooks = repo / ".git" / "hooks"
    hooks.mkdir(exist_ok=True)
    for name in list(hooks.iterdir()):
        name.unlink()
    (hooks / "pre-commit").write_text("#!/bin/sh\n")
    (hooks / "pre-commit").chmod(0o755)
    (hooks / "commit-msg").write_text("#!/bin/sh\n")
    (hooks / "commit-msg").chmod(0o644)
    (hooks / "pre-push.sample").write_text("#!/bin/sh\n")
    (hooks / "pre-push.sample").chmod(0o755)
    assert git.active_hooks(repo) == ["pre-commit"]


def test_active_hooks_honors_core_hooks_path(
    git: LiveGit, repo: Path, tmp_path: Path
) -> None:
    custom = tmp_path / "custom-hooks"
    custom.mkdir()
    (custom / "pre-commit").write_text("#!/bin/sh\n")
    (custom / "pre-commit").chmod(0o755)
    (custom / "pre-push.sample").write_text("#!/bin/sh\n")
    (custom / "pre-push.sample").chmod(0o755)
    sh(repo, "config", "core.hooksPath", str(custom))
    assert git.active_hooks(repo) == ["pre-commit"]


def test_active_hooks_empty_when_only_samples(git: LiveGit, repo: Path) -> None:
    hooks = repo / ".git" / "hooks"
    hooks.mkdir(exist_ok=True)
    for name in list(hooks.iterdir()):
        name.unlink()
    (hooks / "pre-commit.sample").write_text("#!/bin/sh\n")
    (hooks / "pre-commit.sample").chmod(0o755)
    assert git.active_hooks(repo) == []


# --- failures


def test_failing_command_raises_git_error_with_stderr_and_command(
    git: LiveGit, repo: Path
) -> None:
    with pytest.raises(GitError) as info:
        git.switch(repo, "ghost-branch")
    text = str(info.value)
    assert "ghost-branch" in text
    assert "git" in text
    assert "switch" in text or "checkout" in text


# --- scripted failures and edge cases


def failing_git(returncode: int = 128, stderr: str = "fatal: boom\n") -> LiveGit:
    runner = MockRunner()
    runner.results["git"] = RunResult(
        argv=("git", "scripted"),
        returncode=returncode,
        stdout="",
        stderr=stderr,
        seconds=0.0,
    )
    return LiveGit(runner)


def test_head_unexpected_failure_raises_git_error_with_command_and_stderr(
    tmp_path: Path,
) -> None:
    with pytest.raises(GitError) as info:
        failing_git().head(tmp_path)
    assert "git scripted" in str(info.value)
    assert "fatal: boom" in str(info.value)


def test_is_repo_false_for_a_nonexistent_path(git: LiveGit, tmp_path: Path) -> None:
    assert git.is_repo(tmp_path / "missing") is False


def test_is_repo_false_for_a_file(git: LiveGit, tmp_path: Path) -> None:
    file = tmp_path / "file.txt"
    file.write_text("x")
    assert git.is_repo(file) is False


def test_toplevel_none_for_a_nonexistent_path(git: LiveGit, tmp_path: Path) -> None:
    assert git.toplevel(tmp_path / "missing") is None


def test_current_branch_unexpected_failure_raises_git_error(tmp_path: Path) -> None:
    with pytest.raises(GitError) as info:
        failing_git().current_branch(tmp_path)
    assert "fatal: boom" in str(info.value)


def test_current_branch_exit_one_means_detached_and_is_none(tmp_path: Path) -> None:
    assert failing_git(returncode=1, stderr="").current_branch(tmp_path) is None


def test_branch_exists_unexpected_failure_raises_git_error(tmp_path: Path) -> None:
    with pytest.raises(GitError) as info:
        failing_git().branch_exists(tmp_path, "main")
    assert "fatal: boom" in str(info.value)


def test_submodules_empty_when_gitmodules_has_no_paths(
    git: LiveGit, repo: Path
) -> None:
    (repo / ".gitmodules").write_text("# nothing here\n")
    assert git.submodules(repo) == []


def test_submodules_config_failure_raises_git_error(tmp_path: Path) -> None:
    (tmp_path / ".gitmodules").write_text('[submodule "x"]\n\tpath = x\n')
    with pytest.raises(GitError) as info:
        failing_git().submodules(tmp_path)
    assert "fatal: boom" in str(info.value)


def test_active_hooks_empty_when_hooks_folder_is_missing(
    git: LiveGit, repo: Path
) -> None:
    shutil.rmtree(repo / ".git" / "hooks", ignore_errors=True)
    assert git.active_hooks(repo) == []
