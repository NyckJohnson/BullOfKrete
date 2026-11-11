"""Adoption: detection report, apply, start, legacy check, finish and abandon."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from bull.Modules.adoption.Contracts import Adoption, DetectionReport, LegacyLeft
from bull.Modules.adoption.detect import detect
from bull.Modules.adoption.legacy import left_lines, legacy_left
from bull.Modules.features.Contracts import ItemState
from bull.Modules.foundation.Contracts import (
    AppLayout,
    BullError,
    FileFormatError,
    Files,
    Runner,
)
from bull.Modules.gitrepo.Contracts import Git
from bull.Modules.memo.Contracts import MemoReader
from bull.Modules.parts.Contracts import Parts
from bull.Modules.settings.Contracts import Layer, Settings
from bull.Modules.stacks.Contracts import StackOps, StackRegistry
from bull.Modules.status.Contracts import Refs, StatusStore

ADOPT_BRANCH = "adopt/main"
_BACKLOG_FORMAT = 1


class LiveAdoption(Adoption):
    """The adoption track over git, the status store and the app's one part.

    `settings`, `store` and `refs` are called for each use, so they see any write made before.
    Refusals are `BullError`s raised before anything changes.
    """

    def __init__(
        self,
        files: Files,
        git: Git,
        runner: Runner,
        stacks: StackRegistry,
        ops: StackOps,
        parts: Parts,
        memo: MemoReader,
        settings: Callable[[AppLayout], Settings],
        store: Callable[[AppLayout], StatusStore],
        refs: Callable[[AppLayout], Refs],
    ) -> None:
        self._files = files
        self._git = git
        self._runner = runner
        self._stacks = stacks
        self._ops = ops
        self._parts = parts
        self._memo = memo
        self._settings = settings
        self._store = store
        self._refs = refs

    def detect(self, root: Path) -> DetectionReport:
        return detect(root, self._git, self._runner, self._stacks)

    def apply(
        self, app: AppLayout, report: DetectionReport, stack: str | None = None
    ) -> None:
        name = stack or report.stack
        if name is None:
            raise BullError(
                "no stack to apply: detection found none",
                "name one with `bull stack detect --apply <stack>`",
            )
        self._ops.select(app, name)
        if name != report.stack or report.detection is None:
            return
        settings = self._settings(app)
        for key, value in report.detection.settings.items():
            settings.set(key, value, Layer.APP, None)

    def start(self, app: AppLayout) -> None:
        root = app.root
        trunk = self._refs(app).trunk()
        branch = self._git.current_branch(root)
        if branch != trunk:
            raise BullError(
                f"adopt start runs on the trunk {trunk}; you are on {branch}",
                f"git switch {trunk}",
            )
        if not self._git.is_clean(root):
            raise BullError(
                "adopt start needs a clean tree", "commit or stash your changes"
            )
        store = self._store(app)
        if store.load().modules:
            raise BullError(
                "this app already has modules; adoption is for apps built outside bull"
            )
        store.start_adoption()
        self._git.commit_all(root, "chore: start adoption")
        self._git.create_branch(root, ADOPT_BRANCH, trunk, switch=True)

    def legacy(self, app: AppLayout) -> LegacyLeft:
        return legacy_left(app, self._files, self._parts, self._memo, self._stacks)

    def finish(self, app: AppLayout) -> None:
        store = self._store(app)
        adoption = store.load().adoption
        if adoption is None or adoption.stage != 6:
            raise BullError(
                "finish needs stage 6 (verify)",
                "finish the adoption's stages first"
                if adoption is not None
                else "no adoption is active",
            )
        left = self.legacy(app)
        if not left.empty:
            raise BullError(
                "legacy code is left to replace:\n" + "\n".join(left_lines(left)),
                "replace or delete it, then run `bull adopt finish` again",
            )
        store.finish_adoption()
        self._git.commit_all(app.root, "chore: adoption finished")

    def abandon(self, app: AppLayout) -> None:
        root = app.root
        store = self._store(app)
        if store.load().adoption is None:
            raise BullError("no adoption is active", "nothing to abandon")
        trunk = self._refs(app).trunk()
        branch = self._git.current_branch(root)
        if branch != trunk:
            raise BullError(
                f"abandon runs on the trunk `{trunk}`, not `{branch}`",
                f"run `git switch {trunk}` first",
            )
        self._carry_backlog(app)
        store.abandon_adoption()
        self._git.commit_all(root, "chore: abandon adoption")

    def _carry_backlog(self, app: AppLayout) -> None:
        """Appends backlog items queued on `adopt/main` that the trunk lacks, as `queued`."""
        relative = app.backlog_file.relative_to(app.root).as_posix()
        text = self._git.show_file(app.root, ADOPT_BRANCH, relative)
        if text is None:
            return
        source = f"{ADOPT_BRANCH}:{relative}"
        try:
            branch_data: object = json.loads(text)
        except json.JSONDecodeError as e:
            raise FileFormatError(
                f"{source}: invalid JSON at line {e.lineno}: {e.msg}"
            ) from e
        branch_items = _items(branch_data, source)
        trunk_data = self._files.read_json(app.backlog_file)
        trunk_items = (
            [] if trunk_data is None else _items(trunk_data, str(app.backlog_file))
        )
        on_trunk = {item["slug"] for item in trunk_items}
        added: list[dict[str, object]] = []
        for item in branch_items:
            slug = item["slug"]
            if slug in on_trunk:
                continue
            on_trunk.add(slug)
            added.append({**item, "state": ItemState.QUEUED.value})
        if not added:
            return
        self._files.write_json(
            app.backlog_file,
            {"format": _BACKLOG_FORMAT, "items": [*trunk_items, *added]},
        )


def _items(data: object, source: str) -> list[dict[str, object]]:
    """The backlog's item objects; `FileFormatError` when the shape is wrong."""
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise FileFormatError(f"{source}: not a backlog (no `items` list)")
    items: list[dict[str, object]] = []
    for raw in data["items"]:
        if not isinstance(raw, dict) or not isinstance(raw.get("slug"), str):
            raise FileFormatError(f"{source}: a backlog item has no `slug`")
        items.append({str(k): v for k, v in raw.items()})
    return items
