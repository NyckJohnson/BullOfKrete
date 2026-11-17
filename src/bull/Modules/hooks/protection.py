"""Test protection and reference-folder protection."""

from __future__ import annotations

from pathlib import Path

from bull.Modules.foundation.Contracts import AppLayout
from bull.Modules.hooks.Contracts import HookDecision, HookEvent, HookKind
from bull.Modules.parts.Contracts import Parts
from bull.Modules.settings.Contracts import Settings

_ALLOW = HookDecision(True, "")
# Agents kept away from the reference folder.
REFERENCE_BARRED = frozenset({"test-writer", "code-writer"})


def agent_name(agent: str | None) -> str | None:
    """The agent's name without its namespace (`bull:code-writer` -> `code-writer`)."""
    if agent is None:
        return None
    return agent.rsplit(":", 1)[-1]


def _inside(path: Path, folder: Path) -> bool:
    """Whether `path` is `folder` or below it, compared component by component."""
    return path.parts[: len(folder.parts)] == folder.parts


def reference_folder(app: AppLayout, settings: Settings) -> Path:
    """The `reference_dir` setting, relative to the app root unless absolute.

    Raises:
        TypeError: the setting is not a string (the settings schema says it is).
    """
    value = settings.get("reference_dir", None)
    if not isinstance(value, str):
        raise TypeError(f"reference_dir must be a string, got {value!r}")
    folder = Path(value)
    return folder if folder.is_absolute() else app.root / folder


class Protection:
    """Keeps code-writer out of the tests and test/code-writers out of the reference folder.

    Handles BEFORE_EDIT and BEFORE_READ events; every other kind is allowed.
    """

    def __init__(self, parts: Parts, settings: Settings) -> None:
        self._parts = parts
        self._settings = settings

    def check(self, app: AppLayout, event: HookEvent) -> HookDecision:
        agent = agent_name(event.agent)
        if event.kind is HookKind.BEFORE_EDIT:
            return self._check_edit(app, agent, event.paths)
        if event.kind is HookKind.BEFORE_READ:
            return self._check_read(app, agent, event.cwd, event.paths)
        return _ALLOW

    def _check_edit(
        self, app: AppLayout, agent: str | None, paths: tuple[Path, ...]
    ) -> HookDecision:
        if agent != "code-writer":
            return _ALLOW
        for path in paths:
            if self._parts.is_test_path(app, path):
                return HookDecision(False, f"code-writer may not edit tests ({path})")
        return _ALLOW

    def _check_read(
        self,
        app: AppLayout,
        agent: str | None,
        cwd: Path,
        paths: tuple[Path, ...],
    ) -> HookDecision:
        if agent not in REFERENCE_BARRED:
            return _ALLOW
        reference = reference_folder(app, self._settings)
        if not reference.is_dir():
            return _ALLOW
        reference = reference.resolve()
        for path in paths:
            absolute = path if path.is_absolute() else cwd / path
            if _inside(absolute.resolve(), reference):
                return HookDecision(
                    False,
                    f"{agent} may not read the reference folder ({reference}); "
                    "only legacy-test-scanner reads it",
                )
        return _ALLOW
