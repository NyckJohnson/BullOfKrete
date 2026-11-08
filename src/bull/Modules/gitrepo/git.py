"""Git operations through the runner."""

from __future__ import annotations

from pathlib import Path

from bull.Modules.gitrepo.Contracts import Git


class LiveGit(Git):
    def is_repo(self, path: Path) -> bool:
        raise NotImplementedError(f"{type(self).__name__}.is_repo")

    def toplevel(self, path: Path) -> Path | None:
        raise NotImplementedError(f"{type(self).__name__}.toplevel")

    def init(self, path: Path, branch: str) -> None:
        raise NotImplementedError(f"{type(self).__name__}.init")

    def current_branch(self, root: Path) -> str | None:
        raise NotImplementedError(f"{type(self).__name__}.current_branch")

    def head(self, root: Path, ref: str = "HEAD") -> str | None:
        raise NotImplementedError(f"{type(self).__name__}.head")

    def is_clean(self, root: Path) -> bool:
        raise NotImplementedError(f"{type(self).__name__}.is_clean")

    def branch_exists(self, root: Path, name: str) -> bool:
        raise NotImplementedError(f"{type(self).__name__}.branch_exists")

    def create_branch(
        self, root: Path, name: str, start: str, switch: bool = True
    ) -> None:
        raise NotImplementedError(f"{type(self).__name__}.create_branch")

    def switch(self, root: Path, name: str) -> None:
        raise NotImplementedError(f"{type(self).__name__}.switch")

    def commit_all(self, root: Path, message: str) -> str | None:
        raise NotImplementedError(f"{type(self).__name__}.commit_all")

    def tag(self, root: Path, name: str, ref: str = "HEAD") -> None:
        raise NotImplementedError(f"{type(self).__name__}.tag")

    def tags(self, root: Path, pattern: str = "*") -> list[str]:
        raise NotImplementedError(f"{type(self).__name__}.tags")

    def changed_paths(self, root: Path, a: str, b: str) -> list[str]:
        raise NotImplementedError(f"{type(self).__name__}.changed_paths")

    def show_file(self, root: Path, ref: str, path: str) -> str | None:
        raise NotImplementedError(f"{type(self).__name__}.show_file")

    def parents(self, root: Path, ref: str) -> list[str]:
        raise NotImplementedError(f"{type(self).__name__}.parents")

    def submodules(self, root: Path) -> list[str]:
        raise NotImplementedError(f"{type(self).__name__}.submodules")

    def active_hooks(self, root: Path) -> list[str]:
        raise NotImplementedError(f"{type(self).__name__}.active_hooks")
