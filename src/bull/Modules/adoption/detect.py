"""Detection: every stack's `detect` plus bull's own issues."""

from __future__ import annotations

import os
from pathlib import Path

from bull.Modules.adoption.Contracts import DetectionReport
from bull.Modules.foundation.Contracts import Runner
from bull.Modules.gitrepo.Contracts import Git, GitError
from bull.Modules.stacks.Contracts import Detection, Issue, IssueLevel, StackRegistry

_MIN_CONFIDENCE = 0.5
_SKIPPED_FOLDERS = frozenset({".git", "__pycache__"})
_PREFIXES = ("module", "feature", "adopt")
# Tags also clash under `done/`, the prefix of a finished module's tag.
_TAG_PREFIXES = ("done", *_PREFIXES)
_FOR_EACH_REF = (
    "git",
    "for-each-ref",
    "--format=%(refname:short)",
    *(f"refs/heads/{prefix}/" for prefix in _PREFIXES),
)

_NO_STACK = Issue(
    IssueLevel.BLOCK,
    "no stack recognizes this project",
    "pick one with `bull stack detect --apply <stack>` or `bull stack select`",
)
_NOT_ROOT = Issue(
    IssueLevel.BLOCK,
    "not the root of its own git repository",
    "run bull from the repository root, or `git init`",
)


def detect(
    root: Path, git: Git, runner: Runner, stacks: StackRegistry
) -> DetectionReport:
    """The detection report for the project at `root`; changes nothing.

    Raises `GitError` when git cannot list the repository's branches.
    """
    name, detection = _best_stack(root, stacks)
    issues: list[Issue] = []
    if detection is None:
        issues.append(_NO_STACK)
    else:
        issues.extend(detection.issues)
    issues.extend(_repo_issues(root, git, runner))
    return DetectionReport(stack=name, detection=detection, issues=tuple(issues))


def _best_stack(
    root: Path, stacks: StackRegistry
) -> tuple[str | None, Detection | None]:
    best_name: str | None = None
    best: Detection | None = None
    for stack in stacks.all(include_test=True):
        reader = stack.optional.detect
        if reader is None:
            continue
        try:
            found = reader(root)
        # A stack's detect reads an unknown project and may fail in any way; the spec says
        # such a stack is skipped, so detection of the others carries on.
        except Exception:  # noqa: BLE001, S112
            continue
        if found.confidence <= _MIN_CONFIDENCE:
            continue
        if best is None or found.confidence > best.confidence:
            best_name, best = stack.manifest.name, found
    return best_name, best


def _repo_issues(root: Path, git: Git, runner: Runner) -> list[Issue]:
    if git.toplevel(root) != root:
        return [_NOT_ROOT]
    submodules = git.submodules(root)
    issues = [
        Issue(
            IssueLevel.BLOCK,
            f"git submodule {path}",
            "remove the submodule or vendor its files",
        )
        for path in submodules
    ]
    issues.extend(
        Issue(
            IssueLevel.FIX,
            f"nested git repository at {path}",
            "remove its `.git` or vendor its files",
        )
        for path in _nested_repos(root, submodules)
    )
    issues.extend(
        Issue(
            IssueLevel.FIX,
            f"branch {name} clashes with bull's branch names",
            "rename or delete it",
        )
        for name in _clashing_branches(root, runner)
    )
    issues.extend(
        Issue(
            IssueLevel.FIX,
            f"tag {name} clashes with bull's tag names",
            "rename or delete it",
        )
        for prefix in _TAG_PREFIXES
        for name in git.tags(root, f"{prefix}/*")
    )
    issues.extend(
        Issue(IssueLevel.NOTE, f"active git hook {name}", "bull's gates do not run it")
        for name in git.active_hooks(root)
    )
    if not git.is_clean(root):
        issues.append(
            Issue(IssueLevel.FIX, "uncommitted changes", "commit or stash them")
        )
    return issues


def _clashing_branches(root: Path, runner: Runner) -> list[str]:
    result = runner.run(_FOR_EACH_REF, root, None, None)
    if result.returncode != 0:
        raise GitError(
            f"git for-each-ref failed: {result.stderr.strip()}",
            "check that git works in this repository",
        )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _nested_repos(root: Path, submodules: list[str]) -> list[str]:
    """Folders below `root` holding a `.git` file or folder, as sorted POSIX relative paths.

    The walk never enters `.git` or `__pycache__` folders, a nested repo it has found, or a
    submodule; submodule paths are not reported (they have their own issue).
    """
    skipped = {Path(path).as_posix() for path in submodules}
    found: list[str] = []
    for dirpath, dirnames, _ in os.walk(root):
        kept: list[str] = []
        for name in dirnames:
            if name in _SKIPPED_FOLDERS:
                continue
            folder = Path(dirpath) / name
            relative = folder.relative_to(root).as_posix()
            if relative in skipped:
                continue
            if (folder / ".git").exists():
                found.append(relative)
                continue
            kept.append(name)
        dirnames[:] = kept
    return sorted(found)
