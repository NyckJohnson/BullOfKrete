"""The stack repo workflow: stages, checkpoints, test passes and refs.

A stack repo is a git repo created by `bull init --stack` where a stack is built in stages
(`StackStage`). Its state lives in `.bull/status.json` (`kind: "stack"`), written only here.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import replace
from pathlib import Path

from bull.Modules.foundation.Contracts import (
    AppLayout,
    BullError,
    FileFormatError,
    Files,
    Layouts,
)
from bull.Modules.gitrepo.Contracts import Git
from bull.Modules.stackflow.Contracts import StackRepoStatus, StackStage, StackWorkflow
from bull.Modules.stacks.Contracts import StackRegistry
from bull.Modules.stacktest.Contracts import StackTestReport

_FORMAT = 1
_KIND = "stack"
_BRANCH = "main"
_INIT_MESSAGE = "chore: bull init --stack"
_NAME_PATTERN = re.compile(r"[a-z][a-z0-9_]*")
_RESERVED_NAME = "_template"
_TEMPLATE_DIR = Path(__file__).parent / "template"

_DESIGN_APPROVED = "design-approved"
_RULES_APPROVED = "rules-approved"
_ACCEPTED = "accepted"
_CHECKPOINTS = (_DESIGN_APPROVED, _RULES_APPROVED, _ACCEPTED)

# Branch names per stage: the enum name in lowercase with dashes (`gate-code`).
_STAGE_NAMES = {stage: stage.name.lower().replace("_", "-") for stage in StackStage}

_NEXT_STEPS = {
    StackStage.DISCUSS: (
        "Discuss the design and fill DESIGN.md; "
        f"then `bull status checkpoint {_DESIGN_APPROVED}`."
    ),
    StackStage.SCAFFOLD: (
        "Fill stack.toml, rules.md and setup.md, and add readers.py; "
        "then `bull status stage 3`."
    ),
    StackStage.FIXTURE: (
        "Write the fixture and cases.json until `bull stack test . --static` passes; "
        "commit, then `bull status stage 4`."
    ),
    StackStage.GATE_CODE: (
        "Write the gate commands and readers until `bull stack test .` passes; "
        "commit, then `bull status stage 5`."
    ),
    StackStage.REVIEW: (
        "Review rules.md and setup.md with the human; "
        f"then `bull status checkpoint {_RULES_APPROVED}`, commit, run `bull stack test .` "
        f"and `bull status checkpoint {_ACCEPTED}`."
    ),
    StackStage.ACCEPTED: (
        "The stack is accepted; install it with `bull stack install <path>`."
    ),
}


class LiveStackWorkflow(StackWorkflow):
    """The stack workflow over real files and git.

    Args:
        files: reads and writes the repo's files atomically.
        layouts: locates `.bull/` paths and bull apps.
        git: git operations on the stack repo.
        registry: known stacks; `init` refuses a built-in stack's name.
    """

    def __init__(
        self, files: Files, layouts: Layouts, git: Git, registry: StackRegistry
    ) -> None:
        self._files = files
        self._layouts = layouts
        self._git = git
        self._registry = registry

    # --- init

    def init(self, path: Path) -> StackRepoStatus:
        """Create a stack repo at `path`; refused (creating nothing) by `BullError`."""
        path = path.absolute()
        name = path.name
        self._check_init(path, name)
        created = not path.exists()
        try:
            path.mkdir(parents=True, exist_ok=True)
            self._git.init(path, _BRANCH)
            self._files.write_atomic(path / "stack.toml", self._stack_toml(name))
            self._files.write_atomic(path / "DESIGN.md", self._template("DESIGN.md"))
            ignores = "".join(
                f"{line}\n" for line in self._layouts.machine_local_ignores()
            )
            self._files.write_atomic(path / ".gitignore", ignores)
            status = StackRepoStatus(
                format=_FORMAT,
                name=name,
                stage=StackStage.DISCUSS,
                checkpoints=(),
                static_pass=None,
                test_pass=None,
            )
            self._save(path, status)
            self._git.commit_all(path, _INIT_MESSAGE)
        except BaseException:
            _undo_init(path, created)
            raise
        return status

    def _check_init(self, path: Path, name: str) -> None:
        if name == _RESERVED_NAME:
            raise BullError(
                f"`{_RESERVED_NAME}` is reserved for the stack template",
                "choose another folder name",
            )
        if not _NAME_PATTERN.fullmatch(name):
            raise BullError(
                f"`{name}` is not a valid stack name: use lowercase letters, digits and "
                "`_`, starting with a letter",
                "choose a folder name like `my_stack`",
            )
        builtin = {
            stack.manifest.name
            for stack in self._registry.all(include_test=True)
            if stack.builtin
        }
        if name in builtin:
            raise BullError(
                f"`{name}` is the name of a built-in stack",
                "choose another folder name",
            )
        app = self._layouts.find(path.parent)
        if (
            app is not None
            and _status_kind(self._files.read_json(app.status_file)) != _KIND
        ):
            raise BullError(
                f"{path} is inside the bull app at {app.root}",
                "create the stack repo outside any bull app",
            )
        if path.exists():
            if not path.is_dir():
                raise BullError(
                    f"{path} exists and is not a folder", "choose another path"
                )
            if any(path.iterdir()):
                raise BullError(
                    f"{path} is not empty",
                    "choose a new or empty folder for the stack repo",
                )

    def _template(self, file: str) -> str:
        text = self._files.read_text(_TEMPLATE_DIR / file)
        if text is None:
            raise BullError(
                f"the stack template file {file} is missing from bull's installation",
                "reinstall bull",
            )
        return text

    def _stack_toml(self, name: str) -> str:
        """The stack.toml template with its first `name = …` line (in `[stack]`) filled."""
        text, count = re.subn(
            r'^name = ".*"$',
            f'name = "{name}"',
            self._template("stack.toml"),
            count=1,
            flags=re.MULTILINE,
        )
        if count != 1:
            raise BullError(
                "the stack.toml template has no `name` line", "reinstall bull"
            )
        return text

    # --- load and save

    def load(self, path: Path) -> StackRepoStatus:
        """Read the stack repo's status; `BullError` when `path` is not a stack repo."""
        status_file = self._layout(path).status_file
        data = self._files.read_json(status_file)
        if data is None:
            raise BullError(
                f"{path} is not a stack repo (no {status_file.name})",
                "run `bull init --stack <path>` to create one",
            )
        if _status_kind(data) != _KIND:
            raise BullError(
                f"{path} is not a stack repo (its status file is not a stack's)",
                "run stack workflow commands inside a stack repo",
            )
        return _parse(data, status_file)

    def _save(self, path: Path, status: StackRepoStatus) -> None:
        data: dict[str, object] = {
            "format": status.format,
            "kind": _KIND,
            "name": status.name,
            "stage": int(status.stage),
            "checkpoints": list(status.checkpoints),
        }
        if status.static_pass is not None:
            data["static_pass"] = status.static_pass
        if status.test_pass is not None:
            data["test_pass"] = status.test_pass
        self._files.write_json(self._layout(path).status_file, data)

    def _layout(self, path: Path) -> AppLayout:
        return self._layouts.at(path)

    # --- stages and checkpoints

    def set_stage(self, path: Path, stage: int) -> StackRepoStatus:
        """Move to `stage` (back freely, forward one at a time) if its rule holds."""
        status = self.load(path)
        if stage not in {int(s) for s in StackStage}:
            raise BullError(
                f"there is no stack stage {stage}", "use a stage from 1 to 6"
            )
        target = StackStage(stage)
        if target > status.stage + 1:
            raise BullError(
                f"stage {int(target)} can't follow stage {int(status.stage)}",
                f"move one stage at a time: `bull status stage {int(status.stage) + 1}`",
            )
        if target > status.stage:
            self._check_stage_rule(path, status, target)
        updated = replace(status, stage=target)
        self._save(path, updated)
        return updated

    def _check_stage_rule(
        self, path: Path, status: StackRepoStatus, target: StackStage
    ) -> None:
        if target is StackStage.SCAFFOLD and _DESIGN_APPROVED not in status.checkpoints:
            raise BullError(
                f"stage 2 needs the {_DESIGN_APPROVED} checkpoint",
                f"approve DESIGN.md, then `bull status checkpoint {_DESIGN_APPROVED}`",
            )
        if target is StackStage.GATE_CODE and (
            status.static_pass is None or status.static_pass != self._git.head(path)
        ):
            raise BullError(
                "stage 4 needs a static self-test pass at HEAD",
                "commit, then run `bull stack test . --static` until it passes",
            )
        if target is StackStage.REVIEW and status.test_pass is None:
            raise BullError(
                "stage 5 needs a full test pass recorded",
                "commit, then run `bull stack test .` until it passes",
            )
        if target is StackStage.ACCEPTED and _ACCEPTED not in status.checkpoints:
            raise BullError(
                f"stage 6 needs the {_ACCEPTED} checkpoint",
                f"`bull status checkpoint {_ACCEPTED}`",
            )

    def checkpoint(self, path: Path, name: str) -> StackRepoStatus:
        """Record checkpoint `name` if its rule holds; recording twice is a no-op."""
        status = self.load(path)
        if name not in _CHECKPOINTS:
            raise BullError(
                f"`{name}` is not a stack checkpoint",
                "use one of: " + ", ".join(_CHECKPOINTS),
            )
        if name == _RULES_APPROVED and status.stage < StackStage.REVIEW:
            raise BullError(
                f"{_RULES_APPROVED} needs stage 5 (review); "
                f"the repo is at stage {int(status.stage)}",
                "finish the earlier stages first; `bull status next` says what's next",
            )
        if name == _ACCEPTED:
            self._check_accept(path, status)
        if name in status.checkpoints:
            return status
        updated = replace(status, checkpoints=(*status.checkpoints, name))
        self._save(path, updated)
        return updated

    def _check_accept(self, path: Path, status: StackRepoStatus) -> None:
        if _RULES_APPROVED not in status.checkpoints:
            raise BullError(
                f"{_ACCEPTED} needs the {_RULES_APPROVED} checkpoint",
                f"review the rules, then `bull status checkpoint {_RULES_APPROVED}`",
            )
        if not self._is_clean(path):
            raise BullError(
                f"{_ACCEPTED} needs a clean working tree",
                "commit or discard your changes",
            )
        if status.test_pass is None or status.test_pass != self._git.head(path):
            raise BullError(
                f"{_ACCEPTED} needs a full test pass at HEAD",
                "run `bull stack test .` until it passes",
            )

    # --- test passes

    def record_test(self, path: Path, report: StackTestReport) -> StackRepoStatus:
        """Store HEAD as the static or full pass when `report` is ok and the tree clean.

        A report that is not ok, or a dirty tree, leaves the earlier pass in place.
        Recording writes the status file but never commits.
        """
        status = self.load(path)
        if not report.ok or not self._is_clean(path):
            return status
        sha = self._git.head(path)
        if sha is None:
            return status
        if report.static:
            updated = replace(status, static_pass=sha)
        else:
            updated = replace(status, test_pass=sha)
        self._save(path, updated)
        return updated

    def _is_clean(self, path: Path) -> bool:
        """Whether the tree is clean, ignoring changes to the status file (bookkeeping).

        `Git` only reports the whole tree, so when it is dirty the committed status file
        is put back for a second check and the current one restored afterwards. Other
        `.bull/` files are machine-local and git-ignored by `init`.
        """
        if self._git.is_clean(path):
            return True
        status_file = self._layout(path).status_file
        current = self._files.read_text(status_file)
        committed = self._git.show_file(
            path, "HEAD", status_file.relative_to(path).as_posix()
        )
        if current is None or committed is None or current == committed:
            return False
        self._files.write_atomic(status_file, committed)
        try:
            return self._git.is_clean(path)
        finally:
            self._files.write_atomic(status_file, current)

    # --- guidance and refs

    def next_step(self, path: Path) -> str:
        """What to do next at the repo's current stage."""
        return _NEXT_STEPS[self.load(path).stage]

    def ref(self, kind: str, name: str) -> str:
        """`stack/<checkpoint>` for kind `tag`; `stack/<stage name>` for kind `branch`."""
        if kind == "tag":
            if name not in _CHECKPOINTS:
                raise BullError(
                    f"`{name}` is not a stack checkpoint",
                    "use one of: " + ", ".join(_CHECKPOINTS),
                )
            return f"stack/{name}"
        if kind == "branch":
            names = tuple(_STAGE_NAMES.values())
            if name not in names:
                raise BullError(
                    f"`{name}` is not a stack stage name",
                    "use one of: " + ", ".join(names),
                )
            return f"stack/{name}"
        raise BullError(f"unknown ref kind `{kind}`", "use `tag` or `branch`")


def _undo_init(path: Path, created: bool) -> None:
    """Remove what a failed `init` wrote: the folder it created, or the empty folder's new contents."""
    if created:
        shutil.rmtree(path, ignore_errors=True)
        return
    if path.is_dir():
        for child in path.iterdir():
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)


def _status_kind(data: object) -> object:
    return data.get("kind") if isinstance(data, dict) else None


def _parse(data: object, source: Path) -> StackRepoStatus:
    """Validate a stack status file's JSON; `FileFormatError` naming `source` when malformed."""

    def bad(what: str) -> FileFormatError:
        return FileFormatError(
            f"{source}: {what}", "fix the file or restore it from git"
        )

    if not isinstance(data, dict):
        raise bad("not a JSON object")
    fmt = data.get("format")
    if type(fmt) is not int or fmt != _FORMAT:
        raise bad(f"unsupported format {fmt!r}")
    name = data.get("name")
    if not isinstance(name, str):
        raise bad("`name` is not a string")
    stage = data.get("stage")
    if type(stage) is not int or stage not in {int(s) for s in StackStage}:
        raise bad(f"`stage` {stage!r} is not 1 to 6")
    checkpoints = data.get("checkpoints")
    if not isinstance(checkpoints, list) or not all(
        isinstance(item, str) for item in checkpoints
    ):
        raise bad("`checkpoints` is not a list of names")
    passes: list[str | None] = []
    for key in ("static_pass", "test_pass"):
        value = data.get(key)
        if value is not None and not isinstance(value, str):
            raise bad(f"`{key}` is not a commit sha")
        passes.append(value)
    return StackRepoStatus(
        format=fmt,
        name=name,
        stage=StackStage(stage),
        checkpoints=tuple(checkpoints),
        static_pass=passes[0],
        test_pass=passes[1],
    )
