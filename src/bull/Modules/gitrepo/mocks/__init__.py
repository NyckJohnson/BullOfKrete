"""Mocks of the gitrepo contract, for tests and previews."""

from __future__ import annotations

import fnmatch
from pathlib import Path

from bull.Modules.gitrepo.Contracts import Git, GitError

SAMPLE_SHA = "3f9c2a1e8b7d6c5f4a3b2c1d0e9f8a7b6c5d4e3f"


def _is_sha(ref: str) -> bool:
    return len(ref) == 40 and all(c in "0123456789abcdef" for c in ref)


class MockGit(Git):
    """A repo on `main` with one commit; branches, tags and file contents are editable.

    Like the live git, it raises `GitError` on a duplicate tag or branch name and on
    switching to an unknown branch. A tag resolves through `head` to its ref's sha.
    """

    def __init__(self) -> None:
        self.branch: str | None = "main"
        self.branches: set[str] = {"main"}
        self.heads: dict[str, str] = {"HEAD": SAMPLE_SHA, "main": SAMPLE_SHA}
        self.clean = True
        self.tag_names: list[str] = ["outline-approved", "setup"]
        self.files_at: dict[tuple[str, str], str] = {}
        self.changed: list[str] = ["docs/api/Counter.md"]
        self.commits = 0
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def is_repo(self, path: Path) -> bool:
        self.calls.append(("is_repo", (path,)))
        return True

    def toplevel(self, path: Path) -> Path | None:
        self.calls.append(("toplevel", (path,)))
        return path

    def init(self, path: Path, branch: str) -> None:
        self.calls.append(("init", (path, branch)))
        self.branch = branch
        self.branches = {branch}

    def current_branch(self, root: Path) -> str | None:
        self.calls.append(("current_branch", (root,)))
        return self.branch

    def head(self, root: Path, ref: str = "HEAD") -> str | None:
        self.calls.append(("head", (root, ref)))
        return self.heads.get(ref)

    def is_clean(self, root: Path) -> bool:
        self.calls.append(("is_clean", (root,)))
        return self.clean

    def branch_exists(self, root: Path, name: str) -> bool:
        self.calls.append(("branch_exists", (root, name)))
        return name in self.branches

    def create_branch(
        self, root: Path, name: str, start: str, switch: bool = True
    ) -> None:
        self.calls.append(("create_branch", (root, name, start, switch)))
        if name in self.branches:
            raise GitError(f"`git switch -c {name} {start}` failed: '{name}' exists")
        self.branches.add(name)
        self.heads[name] = self.heads.get(start, SAMPLE_SHA)
        if switch:
            self.branch = name

    def switch(self, root: Path, name: str) -> None:
        self.calls.append(("switch", (root, name)))
        if name not in self.branches:
            raise GitError(f"`git switch {name}` failed: invalid reference: {name}")
        self.branch = name

    def commit_all(self, root: Path, message: str) -> str | None:
        self.calls.append(("commit_all", (root, message)))
        self.commits += 1
        sha = f"{self.commits:040x}"
        self.heads["HEAD"] = sha
        if self.branch is not None:
            self.heads[self.branch] = sha
        return sha

    def tag(self, root: Path, name: str, ref: str = "HEAD") -> None:
        self.calls.append(("tag", (root, name, ref)))
        if name in self.tag_names:
            raise GitError(
                f"`git tag {name} {ref}` failed: tag '{name}' already exists"
            )
        self.tag_names.append(name)
        sha = self.heads.get(ref) or (ref if _is_sha(ref) else None)
        if sha is not None:
            self.heads[name] = sha

    def tags(self, root: Path, pattern: str = "*") -> list[str]:
        self.calls.append(("tags", (root, pattern)))
        return sorted(t for t in self.tag_names if fnmatch.fnmatch(t, pattern))

    def changed_paths(self, root: Path, a: str, b: str) -> list[str]:
        self.calls.append(("changed_paths", (root, a, b)))
        return sorted(self.changed)

    def show_file(self, root: Path, ref: str, path: str) -> str | None:
        self.calls.append(("show_file", (root, ref, path)))
        return self.files_at.get((ref, path))

    def parents(self, root: Path, ref: str) -> list[str]:
        self.calls.append(("parents", (root, ref)))
        return [SAMPLE_SHA]

    def submodules(self, root: Path) -> list[str]:
        self.calls.append(("submodules", (root,)))
        return []

    def active_hooks(self, root: Path) -> list[str]:
        self.calls.append(("active_hooks", (root,)))
        return []
