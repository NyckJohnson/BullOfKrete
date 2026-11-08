"""Dispatches a hook event to its safeguard."""

from __future__ import annotations

from bull.Modules.hooks.Contracts import HookDecision, HookEvent, Hooks


class LiveHooks(Hooks):
    def handle(self, event: HookEvent) -> HookDecision:
        raise NotImplementedError(f"{type(self).__name__}.handle")

    def merge_targets(self, command: str) -> list[str]:
        raise NotImplementedError(f"{type(self).__name__}.merge_targets")
