"""Runs a stack's self-test: the static check and the cases against its fixture."""

from __future__ import annotations

from bull.Modules.stacks.Contracts import Stack
from bull.Modules.stacktest.Contracts import Case, StackTester, StackTestReport


class LiveStackTester(StackTester):
    def load_cases(self, stack: Stack) -> list[Case]:
        raise NotImplementedError(f"{type(self).__name__}.load_cases")

    def static(self, stack: Stack) -> StackTestReport:
        raise NotImplementedError(f"{type(self).__name__}.static")

    def run(self, stack: Stack, case: str | None = None) -> StackTestReport:
        raise NotImplementedError(f"{type(self).__name__}.run")

    def render(self, report: StackTestReport) -> str:
        raise NotImplementedError(f"{type(self).__name__}.render")
