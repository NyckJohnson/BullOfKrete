"""Shared helpers for the `LiveStackWorkflow` tests: real temporary git repos."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from bull.Modules.foundation.files import LiveFiles
from bull.Modules.foundation.layout import LiveLayouts
from bull.Modules.foundation.runner import LiveRunner
from bull.Modules.gitrepo.git import LiveGit
from bull.Modules.stackflow.Contracts import StackRepoStatus
from bull.Modules.stackflow.workflow import LiveStackWorkflow
from bull.Modules.stacks.mocks import MockStackRegistry
from bull.Modules.stacktest.Contracts import (
    CaseResult,
    CaseVerdict,
    StackTestReport,
)


def git_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give git a committer and ignore the user's own git configuration."""
    for key, value in {
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
    }.items():
        monkeypatch.setenv(key, value)


def make_workflow() -> LiveStackWorkflow:
    """The workflow over live files, layouts and git, with a mock stack registry.

    The mock registry knows the built-in stacks `fixture` and `python_cli`.
    """
    runner = LiveRunner()
    return LiveStackWorkflow(
        LiveFiles(), LiveLayouts(), LiveGit(runner), MockStackRegistry()
    )


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=True
    )
    return result.stdout


def commit(root: Path, message: str = "change") -> str:
    """Commit everything in the repo and return the new HEAD sha."""
    git(root, "add", "-A")
    git(root, "commit", "-q", "--allow-empty", "-m", message)
    return git(root, "rev-parse", "HEAD").strip()


def head(root: Path) -> str:
    return git(root, "rev-parse", "HEAD").strip()


def report(
    ok: bool = True, static: bool = False, stack: str = "my_stack"
) -> StackTestReport:
    """A stacktest report that is ok or not, static or full."""
    if ok:
        cases = (CaseResult("clean", CaseVerdict.PASS, "pass", "pass"),)
        return StackTestReport(stack, static, (), cases)
    return StackTestReport(stack, static, ("stack.toml: missing key",), ())


def new_repo(root: Path, name: str = "my_stack") -> Path:
    """A freshly initialised stack repo at `root/name`."""
    path = root / name
    make_workflow().init(path)
    return path


def at_stage(path: Path, stage: int) -> StackRepoStatus:
    """Walk a stack repo (fresh from `init`) up to `stage` (1 to 5) by the rules.

    Every state change is committed; the last recorded pass is for the final HEAD.
    """
    workflow = make_workflow()
    status = workflow.load(path)
    if stage >= 2:
        workflow.checkpoint(path, "design-approved")
        commit(path)
        status = workflow.set_stage(path, 2)
    if stage >= 3:
        status = workflow.set_stage(path, 3)
    if stage >= 4:
        commit(path)
        workflow.record_test(path, report(static=True))
        status = workflow.set_stage(path, 4)
    if stage >= 5:
        commit(path)
        workflow.record_test(path, report(static=False))
        status = workflow.set_stage(path, 5)
    return status
