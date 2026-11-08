"""Mocks of the hooks contract, for tests and previews."""

from __future__ import annotations

from bull.Modules.hooks.Contracts import HookDecision, HookEvent, HookKind, Hooks


class MockHooks(Hooks):
    """Allows everything; session start gives a short context; `decision` overrides."""

    def __init__(self) -> None:
        self.decision: HookDecision | None = None
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def handle(self, event: HookEvent) -> HookDecision:
        self.calls.append(("handle", (event,)))
        if self.decision is not None:
            return self.decision
        if event.kind is HookKind.SESSION_START:
            return HookDecision(
                True, "bull · stage 5 (app)\nnext: Counter unit 1: code-writer"
            )
        return HookDecision(True, "")

    def merge_targets(self, command: str) -> list[str]:
        self.calls.append(("merge_targets", (command,)))
        words = command.split()
        if "merge" in words:
            rest = [
                w for w in words[words.index("merge") + 1 :] if not w.startswith("-")
            ]
            return rest[-1:]
        return []
