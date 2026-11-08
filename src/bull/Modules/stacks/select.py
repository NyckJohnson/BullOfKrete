"""The per-app stack operations: select, rules, setup guide, check and run."""

from __future__ import annotations

from bull.Modules.foundation.Contracts import AppLayout
from bull.Modules.stacks.Contracts import CheckItem, Stack, StackOps


class LiveStackOps(StackOps):
    def select(self, app: AppLayout, name: str) -> None:
        raise NotImplementedError(f"{type(self).__name__}.select")

    def rules(self, stack: Stack, agent: str) -> str:
        raise NotImplementedError(f"{type(self).__name__}.rules")

    def setup_guide(self, stack: Stack, section: str | None = None) -> str:
        raise NotImplementedError(f"{type(self).__name__}.setup_guide")

    def check(self, app: AppLayout, part: str | None = None) -> list[CheckItem]:
        raise NotImplementedError(f"{type(self).__name__}.check")

    def run_command(self, app: AppLayout, command: str, part: str | None = None) -> int:
        raise NotImplementedError(f"{type(self).__name__}.run_command")
