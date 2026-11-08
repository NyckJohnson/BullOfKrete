"""Tests for the gitrepo contract (`GitError` and the `Git` protocol)."""

from __future__ import annotations

from bull.Modules.foundation.Contracts import BullError
from bull.Modules.gitrepo.Contracts import Git, GitError

PROTOCOL_METHODS = [
    "is_repo",
    "toplevel",
    "init",
    "current_branch",
    "head",
    "is_clean",
    "branch_exists",
    "create_branch",
    "switch",
    "commit_all",
    "tag",
    "tags",
    "changed_paths",
    "show_file",
    "parents",
    "submodules",
    "active_hooks",
]


def test_git_error_is_a_bull_error() -> None:
    assert issubclass(GitError, BullError)


def test_git_error_carries_message_and_fix() -> None:
    error = GitError("git tag x failed", "pick another name")
    assert error.message == "git tag x failed"
    assert error.fix == "pick another name"
    assert str(error) == "git tag x failed"


def test_git_error_can_be_caught_as_bull_error() -> None:
    try:
        raise GitError("boom")
    except BullError as e:
        assert e.message == "boom"
        assert e.fix == ""


def test_git_protocol_declares_every_operation() -> None:
    for name in PROTOCOL_METHODS:
        assert callable(getattr(Git, name)), name
