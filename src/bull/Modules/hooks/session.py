"""The session-start context."""

from __future__ import annotations

from bull.Modules.foundation.Contracts import AppLayout
from bull.Modules.hooks.Contracts import HookDecision, HookEvent
from bull.Modules.status.Contracts import Progress, Status, StatusStore


def _active_stage(status: Status) -> int:
    """The stage of the active track: the feature's, else the adoption's, else the app's."""
    if status.feature is not None:
        return status.feature.track.stage
    if status.adoption is not None:
        return status.adoption.stage
    return status.app.stage


class SessionStart:
    """Builds the context text a new session starts with; always allows.

    Lines: stage and mode, the pause (unit, reason, resume command) if paused, the
    contract change waiting for approval if any, and the next step.
    """

    def __init__(self, status: StatusStore, progress: Progress) -> None:
        self._status = status
        self._progress = progress

    def check(self, app: AppLayout, event: HookEvent) -> HookDecision:
        status = self._status.load()
        mode = self._status.mode()
        lines = [f"bull: stage {_active_stage(status)}, mode {mode.value}"]
        if status.feature is not None:
            lines[0] += f" (feature {status.feature.slug})"
        if status.pause is not None:
            where = f" at {status.pause.unit}" if status.pause.unit else ""
            lines.append(
                f"Paused{where}: {status.pause.reason}; run `/bull:resume` to continue."
            )
        if status.waiting is not None:
            lines.append(
                f"Waiting for the human to approve the {status.waiting.module} "
                f"contract change: {status.waiting.what}"
            )
        lines.append(f"Next step: {self._progress.next_step().text}")
        return HookDecision(True, "\n".join(lines))
