"""Dispatches a hook event to its safeguard."""

from __future__ import annotations

from bull.Modules.events.Contracts import EventKind, EventLog
from bull.Modules.foundation.Contracts import AppLayout, BullError, Files, Layouts
from bull.Modules.hooks.Contracts import HookDecision, HookEvent, HookKind, Hooks
from bull.Modules.hooks.merge_guard import MergeGuard, merge_targets
from bull.Modules.hooks.protection import Protection, agent_name
from bull.Modules.hooks.session import SessionStart
from bull.Modules.hooks.usage_guard import UsageGuard

_ALLOW = HookDecision(True, "")

# Kinds that block when their safeguard cannot run; the others allow with the message.
_FAIL_CLOSED = frozenset(
    {
        HookKind.BEFORE_AGENT,
        HookKind.BEFORE_SHELL,
        HookKind.BEFORE_EDIT,
        HookKind.BEFORE_READ,
    }
)


def _failure_message(error: Exception) -> str:
    """The text for a safeguard that raised: its reason, plus a BullError's fix."""
    if isinstance(error, BullError):
        reason = error.message
        if error.fix:
            reason = f"{reason} ({error.fix})"
    else:
        reason = str(error) or type(error).__name__
    return f"bull safeguard could not run: {reason}"


class LiveHooks(Hooks):
    """Finds the app from the event's cwd and routes the event to its safeguard.

    Outside a bull app, and in a stack repo (status file `kind` is "stack"), every hook
    allows with an empty message. AGENT_END appends an `agent_end` event and allows;
    BEFORE_SHELL without a command allows. If a safeguard raises, guarded kinds block with
    "bull safeguard could not run: <reason>"; SESSION_START and AGENT_END allow with it.
    """

    def __init__(
        self,
        layouts: Layouts,
        session: SessionStart,
        usage_guard: UsageGuard,
        merge_guard: MergeGuard,
        protection: Protection,
        events: EventLog,
        files: Files,
    ) -> None:
        self._layouts = layouts
        self._session = session
        self._usage_guard = usage_guard
        self._merge_guard = merge_guard
        self._protection = protection
        self._events = events
        self._files = files

    def handle(self, event: HookEvent) -> HookDecision:
        app = self._layouts.find(event.cwd)
        if app is None:
            return _ALLOW
        try:
            if self._is_stack_repo(app):
                return _ALLOW
            return self._route(app, event)
        except Exception as error:  # noqa: BLE001 - fail closed: any safeguard failure is reported
            return HookDecision(event.kind not in _FAIL_CLOSED, _failure_message(error))

    def _is_stack_repo(self, app: AppLayout) -> bool:
        data = self._files.read_json(app.status_file)
        return isinstance(data, dict) and data.get("kind") == "stack"

    def _route(self, app: AppLayout, event: HookEvent) -> HookDecision:
        kind = event.kind
        if kind is HookKind.SESSION_START:
            return self._session.check(app, event)
        if kind is HookKind.BEFORE_AGENT:
            return self._usage_guard.check(app, event)
        if kind is HookKind.BEFORE_SHELL:
            if event.command is None:
                return _ALLOW
            return self._merge_guard.check(app, event.command)
        if kind is HookKind.BEFORE_EDIT or kind is HookKind.BEFORE_READ:
            return self._protection.check(app, event)
        # AGENT_END
        self._events.append(EventKind.AGENT_END, agent=agent_name(event.agent))
        return _ALLOW

    def merge_targets(self, command: str) -> list[str]:
        return merge_targets(command)
