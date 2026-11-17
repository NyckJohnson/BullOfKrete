"""The usage guard on agent launches."""

from __future__ import annotations

from pathlib import Path

from bull.Modules.events.Contracts import EventKind, EventLog
from bull.Modules.foundation.Contracts import AppLayout
from bull.Modules.hooks.Contracts import HookDecision, HookEvent, HookKind
from bull.Modules.hooks.protection import REFERENCE_BARRED, agent_name, reference_folder
from bull.Modules.settings.Contracts import Settings
from bull.Modules.status.Contracts import StatusStore
from bull.Modules.usage.Contracts import Usage, UsageVerdict


class UsageGuard:
    """Decides whether a subagent may be launched (BEFORE_AGENT; other kinds are allowed).

    In order: a usage PAUSE blocks with its reason; a contract change waiting for approval
    blocks; a test-writer or code-writer whose prompt names the reference folder blocks (only
    when the folder exists). Otherwise the launch is allowed, with a warning when usage is
    UNKNOWN, and an `agent_start` event is appended. Blocks append nothing.
    """

    def __init__(
        self,
        usage: Usage,
        status: StatusStore,
        settings: Settings,
        events: EventLog,
    ) -> None:
        self._usage = usage
        self._status = status
        self._settings = settings
        self._events = events

    def check(self, app: AppLayout, event: HookEvent) -> HookDecision:
        if event.kind is not HookKind.BEFORE_AGENT:
            return HookDecision(True, "")
        usage = self._usage.check()
        if usage.verdict is UsageVerdict.PAUSE:
            return HookDecision(False, f"usage check says pause: {usage.reason}")
        waiting = self._status.load().waiting
        if waiting is not None:
            return HookDecision(
                False,
                f"waiting for the human to approve the {waiting.module} contract change",
            )
        target = agent_name(event.target_agent)
        if target in REFERENCE_BARRED and self._names_reference(app, event.prompt):
            return HookDecision(
                False, "never give the reference folder to test-writer or code-writer"
            )
        self._events.append(EventKind.AGENT_START, agent=target)
        if usage.verdict is UsageVerdict.UNKNOWN:
            return HookDecision(True, f"warning: usage unknown ({usage.reason})")
        return HookDecision(True, "")

    def _names_reference(self, app: AppLayout, prompt: str | None) -> bool:
        """Whether the prompt mentions the existing reference folder.

        Matches the setting as written followed by `/` (e.g. `reference/`) and the folder's
        absolute path, both as given and resolved (symlinked temp folders differ).
        """
        if not prompt:
            return False
        folder = reference_folder(app, self._settings)
        if not folder.is_dir():
            return False
        value = self._settings.get("reference_dir", None)
        needles = {str(folder), str(folder.resolve())}
        if isinstance(value, str) and not Path(value).is_absolute():
            needles.add(value.rstrip("/") + "/")
        return any(needle in prompt for needle in needles)
