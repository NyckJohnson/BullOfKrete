"""Git operations through the runner."""

from __future__ import annotations

import os
from pathlib import Path

from bull.Modules.foundation.Contracts import Runner, RunResult
from bull.Modules.gitrepo.Contracts import Git, GitError

_STDERR_LINES = 5


def _failure(result: RunResult) -> GitError:
    """Build the GitError for a failed command: the command and git's first stderr lines."""
    command = " ".join(result.argv)
    lines = [line for line in result.stderr.strip().splitlines() if line.strip()]
    detail = "\n".join(lines[:_STDERR_LINES]) or f"exit code {result.returncode}"
    return GitError(f"`{command}` failed: {detail}")


class LiveGit(Git):
    """`Git` backed by the `git` executable, run through a foundation `Runner`.

    Every call runs `git` with an argument list in the given folder; nothing goes
    through a shell. Expected negatives (unknown ref, missing file, nothing to commit,
    not a repo) return None, False or [] as the contract says; any other failure
    raises `GitError` naming the command and git's stderr.
    """

    def __init__(self, runner: Runner) -> None:
        self._runner = runner

    # --- helpers

    def _try(self, cwd: Path, *args: str) -> RunResult:
        """Run `git <args>` in `cwd` and return the result, whatever its exit code."""
        return self._runner.run(["git", *args], cwd=cwd)

    def _run(self, cwd: Path, *args: str) -> str:
        """Run `git <args>` in `cwd`; return stdout, or raise `GitError` on failure."""
        result = self._try(cwd, *args)
        if result.returncode != 0:
            raise _failure(result)
        return result.stdout

    def _resolve(self, root: Path, ref: str) -> str | None:
        """Full commit sha of `ref`, or None when it doesn't name a commit."""
        result = self._try(
            root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
        if result.returncode == 1:
            return None
        raise _failure(result)

    # --- repository

    def is_repo(self, path: Path) -> bool:
        if not path.is_dir():
            return False
        result = self._try(path, "rev-parse", "--is-inside-work-tree")
        return result.returncode == 0 and result.stdout.strip() == "true"

    def toplevel(self, path: Path) -> Path | None:
        if not path.is_dir():
            return None
        result = self._try(path, "rev-parse", "--show-toplevel")
        if result.returncode != 0:
            return None
        top = result.stdout.strip()
        return Path(top) if top else None

    def init(self, path: Path, branch: str) -> None:
        self._run(path, "init", "--quiet")
        # symbolic-ref instead of `init -b` so older gits name the branch too.
        self._run(path, "symbolic-ref", "HEAD", f"refs/heads/{branch}")

    def current_branch(self, root: Path) -> str | None:
        result = self._try(root, "symbolic-ref", "--short", "--quiet", "HEAD")
        if result.returncode == 0:
            return result.stdout.strip() or None
        if result.returncode == 1:  # detached HEAD
            return None
        raise _failure(result)

    def head(self, root: Path, ref: str = "HEAD") -> str | None:
        return self._resolve(root, ref)

    def is_clean(self, root: Path) -> bool:
        out = self._run(root, "status", "--porcelain", "--untracked-files=normal")
        return out.strip() == ""

    # --- branches

    def branch_exists(self, root: Path, name: str) -> bool:
        result = self._try(
            root, "rev-parse", "--verify", "--quiet", f"refs/heads/{name}"
        )
        if result.returncode == 0:
            return True
        if result.returncode == 1:
            return False
        raise _failure(result)

    def create_branch(
        self, root: Path, name: str, start: str, switch: bool = True
    ) -> None:
        if switch:
            self._run(root, "switch", "--quiet", "--no-guess", "-c", name, start)
        else:
            self._run(root, "branch", name, start)

    def switch(self, root: Path, name: str) -> None:
        self._run(root, "switch", "--quiet", "--no-guess", name)

    # --- commits and tags

    def commit_all(self, root: Path, message: str) -> str | None:
        self._run(root, "add", "-A")
        staged = self._run(root, "status", "--porcelain", "--untracked-files=no")
        if staged.strip() == "":
            return None
        self._run(root, "commit", "--quiet", "-m", message)
        return self._resolve(root, "HEAD")

    def tag(self, root: Path, name: str, ref: str = "HEAD") -> None:
        self._run(root, "tag", name, ref)

    def tags(self, root: Path, pattern: str = "*") -> list[str]:
        out = self._run(root, "tag", "--list", pattern)
        return sorted(line for line in out.splitlines() if line)

    def changed_paths(self, root: Path, a: str, b: str) -> list[str]:
        out = self._run(
            root,
            "diff",
            "--name-only",
            "--no-renames",
            "--no-ext-diff",
            "-z",
            a,
            b,
            "--",
        )
        return sorted(path for path in out.split("\0") if path)

    def show_file(self, root: Path, ref: str, path: str) -> str | None:
        result = self._try(root, "cat-file", "blob", f"{ref}:{path}")
        if result.returncode == 0:
            return result.stdout
        # A bad ref is an error; a good ref without the file is the expected "missing".
        if self._resolve(root, ref) is None:
            raise _failure(result)
        return None

    def parents(self, root: Path, ref: str) -> list[str]:
        out = self._run(root, "rev-list", "--parents", "--max-count=1", ref, "--")
        shas = out.split()
        return shas[1:]

    # --- repo setup

    def submodules(self, root: Path) -> list[str]:
        if not (root / ".gitmodules").is_file():
            return []
        result = self._try(
            root,
            "config",
            "--file",
            ".gitmodules",
            "--get-regexp",
            r"^submodule\..*\.path$",
        )
        if result.returncode == 1:  # no matching keys
            return []
        if result.returncode != 0:
            raise _failure(result)
        paths = []
        for line in result.stdout.splitlines():
            _, _, value = line.partition(" ")
            if value:
                paths.append(value)
        return sorted(paths)

    def active_hooks(self, root: Path) -> list[str]:
        # --git-path honours core.hooksPath; the answer may be relative to `root`.
        hooks = root / self._run(root, "rev-parse", "--git-path", "hooks").strip()
        if not hooks.is_dir():
            return []
        return sorted(
            entry.name
            for entry in hooks.iterdir()
            if entry.is_file()
            and not entry.name.endswith(".sample")
            and os.access(entry, os.X_OK)
        )
