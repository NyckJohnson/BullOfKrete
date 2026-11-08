"""Branch and tag names for the current mode.

Prefix per mode: none (APP), `feature/<slug>/` (FEATURE), `adopt/` (ADOPT). The trunk is the
`base_branch` setting; the base branch is the trunk, `feature/<slug>/main` or `adopt/main`.
"""

from __future__ import annotations

from bull.Modules.settings.Contracts import Settings
from bull.Modules.status.Contracts import Refs, StatusError, StatusStore

_MODULE = "module/"
_UNPREFIXED_TAGS = frozenset({"adopted"})


class LiveRefs(Refs):
    """Names derived from the settings and the mode of the stored status."""

    def __init__(self, settings: Settings, store: StatusStore) -> None:
        self._settings = settings
        self._store = store

    def _prefix(self) -> str:
        """The prefix for the mode, read from one `store.load()` (not `store.mode()`, so
        the mode and the feature slug always come from the same status)."""
        status = self._store.load()
        if status.adoption is not None:
            return "adopt/"
        if status.feature is not None:
            return f"feature/{status.feature.slug}/"
        return ""

    def trunk(self) -> str:
        value = self._settings.get("base_branch", None)
        if not isinstance(value, str) or not value:
            raise StatusError(
                f"setting base_branch must be a branch name, not {value!r}"
            )
        return value

    def base(self) -> str:
        prefix = self._prefix()
        return f"{prefix}main" if prefix else self.trunk()

    def module_branch(self, module: str) -> str:
        return f"{self._prefix()}{_MODULE}{module}"

    def tag(self, label: str) -> str:
        if label in _UNPREFIXED_TAGS:
            return label
        return f"{self._prefix()}{label}"

    def module_for_branch(self, branch: str) -> str | None:
        start = f"{self._prefix()}{_MODULE}"
        if not branch.startswith(start):
            return None
        name = branch[len(start) :]
        if not name or "/" in name:
            return None
        return name
