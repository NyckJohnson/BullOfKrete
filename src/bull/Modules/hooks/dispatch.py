"""Dispatches a hook event to its safeguard."""

from __future__ import annotations

from bull.Modules.events.Contracts import EventKind, EventLog
from bull.Modules.foundation.Contracts import Layouts
from bull.Modules.hooks.Contracts import HookDecision, HookEvent, HookKind, Hooks
from bull.Modules.hooks.merge_guard import MergeGuard, merge_targets
from bull.Modules.hooks.protection import Protection, agent_name
from bull.Modules.hooks.session import SessionStart
from bull.Modules.hooks.usage_guard import UsageGuard

_ALLOW = HookDecision(True, "")


class LiveHooks(Hooks):
    """Finds the app from the event's cwd and routes the event to its safeguard.

    Outside a bull app every hook allows with an empty message. AGENT_END appends an
    `agent_end` event and allows; BEFORE_SHELL without a command allows.
    """

    def __init__(
        self,
        layouts: Layouts,
        session: SessionStart,
        usage_guard: UsageGuard,
        merge_guard: MergeGuard,
        protection: Protection,
        events: EventLog,
    ) -> None:
        self._layouts = layouts
        self._session = session
        self._usage_guard = usage_guard
        self._merge_guard = merge_guard
        self._protection = protection
        self._events = events

    def handle(self, event: HookEvent) -> HookDecision:
        app = self._layouts.find(event.cwd)
        if app is None:
            return _ALLOW
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
