"""`bull init` and `bull open`."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TextIO

from bull.Modules.adoption.Contracts import Adoption, DetectionReport
from bull.Modules.appinit.Contracts import AppInit, InitResult
from bull.Modules.claude_code.Contracts import Provider
from bull.Modules.formats.Contracts import Formats
from bull.Modules.foundation.Contracts import AppLayout, BullError, Files, Layouts
from bull.Modules.gitrepo.Contracts import Git
from bull.Modules.settings.Contracts import Settings
from bull.Modules.stackflow.Contracts import StackWorkflow
from bull.Modules.status.Contracts import StatusStore

_TRUNK = "main"
_INIT_COMMIT = "chore: bull init"
_ADOPT_COMMIT = "chore: bull init --adopt stack settings"
_STACK_COMMIT = "chore: bull init --stack provider files"
_CONFIG_TEXT = "format = 1\n"
_EMPTY_BACKLOG: dict[str, object] = {"format": 1, "items": []}


class LiveAppInit(AppInit):
    """Sets up app folders and stack repos, and builds the `bull open` command line.

    `status` and `settings` build the status store and the settings for a given app.
    `out` receives the adoption detection report.
    """

    def __init__(
        self,
        *,
        layouts: Layouts,
        git: Git,
        files: Files,
        formats: Formats,
        status: Callable[[AppLayout], StatusStore],
        adoption: Adoption,
        stackflow: StackWorkflow,
        provider: Provider,
        settings: Callable[[AppLayout], Settings],
        version: str,
        out: TextIO,
    ) -> None:
        self._layouts = layouts
        self._git = git
        self._files = files
        self._formats = formats
        self._status = status
        self._adoption = adoption
        self._stackflow = stackflow
        self._provider = provider
        self._settings = settings
        self._version = version
        self._out = out

    # --- bull init

    def init(self, path: Path, adopt: bool = False) -> InitResult:
        """Create a new app, relink an existing one, or start adopting an existing project.

        Raises:
            BullError: `path` is inside a bull app (below its root); `path` is not empty and
                not a bull app (without `adopt`); with `adopt`, it is not a git repo root on a
                clean tree, or detection reports a blocking issue (after printing the report).
        """
        root = path.absolute()
        found = self._layouts.find(root)
        if found is not None:
            if _same(found.root, root):
                return self._relink(found, root)
            raise BullError(
                f"{root} is inside the bull app at {found.root}",
                f"run `bull init .` in the app root {found.root} to relink it, "
                "or pick a folder outside it",
            )
        if self._is_empty_git_repo(root):
            return self._create(root, git_init=False)
        if _has_content(root):
            if not adopt:
                raise BullError(
                    f"{root} is not empty and not a bull app; to bring an existing app "
                    "under bull use `bull init --adopt`",
                    f"bull init --adopt {root}",
                )
            return self._adopt(root)
        return self._create(root)

    def init_stack(self, path: Path) -> InitResult:
        """`bull init --stack`: create a stack repo, then write and commit the provider's files."""
        root = path.absolute()
        self._stackflow.init(root)
        self._write_provider_files(self._layouts.at(root))
        self._git.commit_all(root, _STACK_COMMIT)
        return InitResult(root=root, created=True, relinked=False, adopting=False)

    def _is_empty_git_repo(self, root: Path) -> bool:
        """True when `root` holds only `.git` and that repository has no commits yet."""
        if not root.is_dir() or [p.name for p in root.iterdir()] != [".git"]:
            return False
        return self._git.is_repo(root) and self._git.head(root, "HEAD") is None

    def _create(self, root: Path, *, git_init: bool = True) -> InitResult:
        """Set up a new app; `git_init=False` reuses an existing, commit-less repo."""
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise BullError(
                f"cannot create {root}: {error.strerror}", "pick a writable folder"
            ) from error
        if git_init:
            self._git.init(root, _TRUNK)
        self._write_app(self._layouts.at(root))
        self._git.commit_all(root, _INIT_COMMIT)
        return InitResult(root=root, created=True, relinked=False, adopting=False)

    def _relink(self, app: AppLayout, root: Path) -> InitResult:
        changed = self._merge_gitignore(app)
        changed = self._write_provider_files(app) or changed
        if changed:
            self._git.commit_all(app.root, _INIT_COMMIT)
        return InitResult(root=root, created=False, relinked=True, adopting=False)

    def _adopt(self, root: Path) -> InitResult:
        top = self._git.toplevel(root) if self._git.is_repo(root) else None
        if top is None or not _same(top, root):
            raise BullError(
                f"{root} is not the root of a git repository; adoption needs one",
                "run `bull init --adopt` in the repository's top folder"
                if top is not None
                else "put the project under git first (git init, then commit)",
            )
        if not self._git.is_clean(root):
            raise BullError(
                f"{root} has uncommitted changes; adoption needs a clean tree",
                "commit or stash your changes",
            )
        app = self._layouts.at(root)
        self._write_app(app)
        self._git.commit_all(root, _INIT_COMMIT)
        report = self._adoption.detect(root)
        self._out.write(_render_report(report))
        if report.blocked:
            raise BullError(
                "detection found blocking issues; adoption not started",
                "fix the issues above, then run `bull stack detect --apply` "
                "and `bull adopt start`",
            )
        self._adoption.apply(app, report)
        self._git.commit_all(root, _ADOPT_COMMIT)
        self._adoption.start(app)
        return InitResult(root=root, created=False, relinked=False, adopting=True)

    def _write_app(self, app: AppLayout) -> None:
        """Write a new app's state files, `.gitignore` lines and provider files."""
        self._files.write_atomic(app.config_file, _CONFIG_TEXT)
        self._status(app).create()
        self._files.write_json(app.backlog_file, _EMPTY_BACKLOG)
        self._merge_gitignore(app)
        self._write_provider_files(app)

    def _merge_gitignore(self, app: AppLayout) -> bool:
        """Add the missing machine-local lines to `.gitignore`; True when it changed."""
        path = app.root / ".gitignore"
        text = self._files.read_text(path) or ""
        present = set(text.splitlines())
        missing = [
            line
            for line in self._layouts.machine_local_ignores()
            if line not in present
        ]
        if not missing:
            return False
        if text and not text.endswith("\n"):
            text += "\n"
        self._files.write_atomic(path, text + "".join(f"{line}\n" for line in missing))
        return True

    def _write_provider_files(self, app: AppLayout) -> bool:
        """Write the provider's app files whose content differs; True when any changed."""
        changed = False
        for path, text in self._provider.app_files(app).items():
            if self._files.read_text(path) != text:
                self._files.write_atomic(path, text)
                changed = True
        return changed

    # --- bull open

    def open_argv(self, path: Path, extra: Sequence[str]) -> list[str]:
        """Render the plugin for the app or stack repo at `path` and return the launch argv.

        Raises:
            BullError: `path` is not in a bull app or stack repo; an app's file formats are
                not current (`formats` errors).
        """
        root = path.absolute()
        app = self._layouts.find(root)
        if app is None:
            raise BullError(
                f"{root} is not a bull app or stack repo",
                "run `bull init` to make it one",
            )
        if not self._is_stack_repo(app):
            self._formats.check(app)
        self._provider.render_plugin(app.plugin_dir, self._settings(app), self._version)
        return self._provider.launch_argv(app, extra)

    def _is_stack_repo(self, app: AppLayout) -> bool:
        data = self._files.read_json(app.status_file)
        return isinstance(data, dict) and data.get("kind") == "stack"


def _same(a: Path, b: Path) -> bool:
    return a.resolve() == b.resolve()


def _has_content(root: Path) -> bool:
    """True when `root` exists and is not an empty folder (a file counts as content)."""
    if not root.exists():
        return False
    if not root.is_dir():
        return True
    return any(root.iterdir())


def _render_report(report: DetectionReport) -> str:
    lines = [f"stack: {report.stack or 'none'}"]
    if report.detection is not None:
        lines.append(f"detected: {report.detection.summary}")
    for issue in report.issues:
        line = f"{issue.level.name.lower()}: {issue.item}"
        if issue.fix:
            line += f" (fix: {issue.fix})"
        lines.append(line)
    return "".join(f"{line}\n" for line in lines)
