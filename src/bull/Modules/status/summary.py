"""Progress: the next step, the summary, the JSON view and the pipeline's tags."""

from __future__ import annotations

import fnmatch

from bull.Modules.foundation.Contracts import AppLayout
from bull.Modules.gitrepo.Contracts import Git
from bull.Modules.status.Contracts import (
    Mode,
    NextStep,
    Progress,
    Refs,
    Status,
    StatusStore,
    UnitState,
)
from bull.Modules.status.model import mode_of, status_to_json, track_of
from bull.Modules.status.next_step import next_step

# Every checkpoint name of every mode (app, feature, adopt).
_CHECKPOINTS = frozenset(
    {
        "outline-approved",
        "setup",
        "skeleton",
        "ui-approved",
        "app-accepted",
        "accepted",
        "baseline",
        "scaffold",
        "adopted",
    }
)
_TAG_PATTERNS = ("done/*", "module/*", "feature/*", "adopt/*")


def _is_pipeline_tag(name: str) -> bool:
    return name in _CHECKPOINTS or any(
        fnmatch.fnmatchcase(name, pattern) for pattern in _TAG_PATTERNS
    )


def _unit_counts(status: Status) -> tuple[int, int]:
    """(units done, units total) across every module."""
    units = [u for m in status.modules for u in m.units]
    return sum(1 for u in units if u.state == UnitState.DONE), len(units)


def _mode_label(status: Status, mode: Mode) -> str:
    if mode == Mode.FEATURE and status.feature is not None:
        return f"feature {status.feature.slug}"
    return mode.value


class LiveProgress(Progress):
    """Reads the status through `store` and the current branch and tags through `git`."""

    def __init__(
        self, app: AppLayout, store: StatusStore, refs: Refs, git: Git
    ) -> None:
        self._app = app
        self._store = store
        self._refs = refs
        self._git = git

    def _current(self) -> tuple[Status, Mode, NextStep]:
        # One load; the mode comes from that status, never a second read.
        status = self._store.load()
        mode = mode_of(status)
        branch = self._git.current_branch(self._app.root)
        return status, mode, next_step(status, mode, self._refs, branch)

    def next_step(self) -> NextStep:
        return self._current()[2]

    def summary(self) -> str:
        status, mode, step = self._current()
        track = track_of(status)
        done, total = _unit_counts(status)
        lines = [
            f"stage {track.stage} ({_mode_label(status, mode)}) · units {done}/{total}",
            "checkpoints: "
            + (", ".join(track.checkpoints) if track.checkpoints else "none"),
        ]
        if status.pause is not None:
            lines.append(f"paused: {status.pause.reason}")
        if status.waiting is not None:
            lines.append(f"waiting: {status.waiting.module}: {status.waiting.what}")
        if status.modules:
            width = max(len(m.name) for m in status.modules)
            state_width = max(len(m.state.value) for m in status.modules)
            for module in status.modules:
                units = ", ".join(
                    f"unit {u.number} {u.state.value}" for u in module.units
                )
                lines.append(
                    f"  {module.name:<{width}}  {module.state.value:<{state_width}}"
                    f"  {units}".rstrip()
                )
        if status.plan is not None:
            items = ", ".join(
                f"[{'x' if i.done else ' '}] {i.name}" for i in status.plan.items
            )
            lines.append(f"plan {status.plan.label}: {items}")
        lines.append(f"next: {step.text}")
        return "\n".join(lines) + "\n"

    def as_json(self) -> dict[str, object]:
        status, mode, step = self._current()
        done, total = _unit_counts(status)
        data = status_to_json(status)
        data.update(
            {
                "mode": mode.value,
                "next": step.text,
                "units_done": done,
                "units_total": total,
            }
        )
        return data

    def tags(self) -> list[str]:
        names = self._git.tags(self._app.root, "*")
        return sorted({name for name in names if _is_pipeline_tag(name)})
