"""The feature cycle: start, plan, accept and abandon."""

from __future__ import annotations

import json
from dataclasses import replace

from bull.Modules.features.backlog import parse_backlog, read_backlog, write_backlog
from bull.Modules.features.Contracts import (
    BacklogItem,
    FeatureCycle,
    FeaturePlan,
    ItemState,
)
from bull.Modules.foundation.Contracts import (
    AppLayout,
    BullError,
    FileFormatError,
    Files,
)
from bull.Modules.gitrepo.Contracts import Git
from bull.Modules.memo.Contracts import MemoReader
from bull.Modules.status.Contracts import ActiveFeature, Refs, StatusStore

_ACCEPTED_APP = "app-accepted"
_ACCEPTED_FEATURE = "accepted"
_FINAL_STAGE = 6


def _feature_branch(slug: str) -> str:
    return f"feature/{slug}/main"


class LiveFeatureCycle(FeatureCycle):
    """Moves one backlog item through the feature cycle.

    The cycle writes `backlog.json` itself (through the shared helpers in `backlog.py`),
    because the `Backlog` protocol cannot change an item's state. Every refusal is a
    `BullError` raised before anything is changed.
    """

    def __init__(
        self,
        app: AppLayout,
        files: Files,
        git: Git,
        memo: MemoReader,
        store: StatusStore,
        refs: Refs,
    ) -> None:
        self._app = app
        self._files = files
        self._git = git
        self._memo = memo
        self._store = store
        self._refs = refs

    # --- helpers ---------------------------------------------------------------------

    def _active_feature(self) -> ActiveFeature:
        feature = self._store.load().feature
        if feature is None:
            raise BullError("No feature is active.", "Run `bull feature start`.")
        return feature

    def _require_branch(self, branch: str, fix: str) -> None:
        current = self._git.current_branch(self._app.root)
        if current != branch:
            raise BullError(f"Not on `{branch}` (on `{current or 'no branch'}`).", fix)

    def _set_state(
        self, items: list[BacklogItem], slug: str, state: ItemState
    ) -> tuple[list[BacklogItem], BacklogItem]:
        """`items` with `slug` set to `state`, and the changed item.

        Raises `BullError` when `slug` isn't in the backlog.
        """
        for n, item in enumerate(items):
            if item.slug == slug:
                changed = replace(item, state=state)
                return [*items[:n], changed, *items[n + 1 :]], changed
        raise BullError(
            f"Feature {slug!r} is not in the backlog.", "Run `bull feature list`."
        )

    # --- start -----------------------------------------------------------------------

    def start(self, slug: str | None = None) -> BacklogItem:
        root = self._app.root
        status = self._store.load()
        if _ACCEPTED_APP not in status.app.checkpoints:
            raise BullError(
                "Features start only after the app is accepted.",
                "Finish the app's stage 6 first.",
            )
        if status.adoption is not None:
            raise BullError(
                "An adoption is in progress; a feature can start after the adoption finishes.",
                "Finish or abandon the adoption first.",
            )
        if status.feature is not None:
            raise BullError(
                f"Feature {status.feature.slug!r} is already active.",
                "Accept or abandon it first.",
            )
        trunk = self._refs.trunk()
        self._require_branch(trunk, f"Run `git switch {trunk}`.")
        if not self._git.is_clean(root):
            raise BullError(
                "The working tree has uncommitted changes.", "Commit or stash them."
            )

        items = read_backlog(self._app, self._files)
        queued = [i for i in items if i.state is ItemState.QUEUED]
        if slug is None:
            if not queued:
                raise BullError(
                    "No feature is queued.", 'Run `bull feature add "<Title>: <desc>"`.'
                )
            slug = queued[0].slug
        elif not any(i.slug == slug for i in queued):
            raise BullError(f"No queued feature {slug!r}.", "Run `bull feature list`.")
        branch = _feature_branch(slug)
        if self._git.branch_exists(root, branch):
            raise BullError(
                f"Branch `{branch}` already exists.", "Delete or rename that branch."
            )

        items, item = self._set_state(items, slug, ItemState.ACTIVE)
        # Record the feature first: if the store refuses, the backlog is left untouched.
        self._store.start_feature(slug)
        write_backlog(self._app, self._files, items)
        # Commit on the trunk first so the feature branch starts with the item active.
        self._git.commit_all(root, f"chore: start feature {slug}")
        self._git.create_branch(root, branch, trunk, True)
        return item

    # --- plan ------------------------------------------------------------------------

    def plan(self) -> FeaturePlan:
        feature = self._active_feature()
        slug = feature.slug
        self._require_branch(
            _feature_branch(slug), f"Run `git switch {_feature_branch(slug)}`."
        )
        text = self._files.read_text(self._app.memo_file)
        if text is None:
            raise BullError(
                f"{self._app.memo_file} is missing.", "Write the memo first."
            )
        memo = self._memo.parse(text)

        # Memo problems are refused here, before anything changes. With `replace`,
        # unchanged units keep their progress and new modules are added in build order.
        known = {m.name for m in self._store.load().modules}
        status = self._store.init_modules(memo, replace=True)

        reopened: dict[str, tuple[int, ...]] = {}
        for entry in memo.modules:
            files = entry.changes.get(slug)
            if not files:
                continue
            status = self._store.reopen(entry.name, files)
            module = next(m for m in status.modules if m.name == entry.name)
            reopened[entry.name] = tuple(
                u.number for u in module.units if set(u.files) & set(files)
            )

        new_modules = tuple(e.name for e in memo.modules if e.name not in known)
        contract_changes = tuple(
            e.name for e in memo.modules if slug in e.contract_changes
        )
        return FeaturePlan(
            reopened=reopened,
            new_modules=new_modules,
            contract_changes=contract_changes,
            skeleton_needed=bool(new_modules or contract_changes),
        )

    # --- accept ----------------------------------------------------------------------

    def accept(self) -> BacklogItem:
        feature = self._active_feature()
        track = feature.track
        if track.stage != _FINAL_STAGE or _ACCEPTED_FEATURE not in track.checkpoints:
            raise BullError(
                f"Feature {feature.slug!r} is not accepted yet.",
                "Finish its stage 6 and record the `accepted` checkpoint.",
            )
        items, item = self._set_state(
            read_backlog(self._app, self._files), feature.slug, ItemState.ACCEPTED
        )
        write_backlog(self._app, self._files, items)
        self._store.end_feature()
        return item

    # --- abandon ---------------------------------------------------------------------

    def abandon(self) -> BacklogItem:
        feature = self._active_feature()
        trunk = self._refs.trunk()
        self._require_branch(trunk, f"Run `git switch {trunk}`, then abandon again.")

        items, item = self._set_state(
            read_backlog(self._app, self._files), feature.slug, ItemState.ABANDONED
        )
        # Ideas queued on the feature branch would be lost with it: keep them as queued.
        on_trunk = {i.slug for i in items}
        for extra in self._branch_items(_feature_branch(feature.slug)):
            if extra.slug not in on_trunk:
                items.append(replace(extra, state=ItemState.QUEUED))
                on_trunk.add(extra.slug)
        write_backlog(self._app, self._files, items)
        self._store.end_feature()
        return item

    def _branch_items(self, branch: str) -> list[BacklogItem]:
        """The backlog items committed on `branch`; none when it has no backlog file.

        Raises `FileFormatError` when that file is not a valid backlog.
        """
        path = self._app.backlog_file.relative_to(self._app.root).as_posix()
        text = self._git.show_file(self._app.root, branch, path)
        if text is None:
            return []
        where = f"{branch}:{path}"
        try:
            data: object = json.loads(text)
        except json.JSONDecodeError as e:
            raise FileFormatError(
                f"{where}: invalid JSON at line {e.lineno}: {e.msg}"
            ) from e
        return parse_backlog(data, where)
