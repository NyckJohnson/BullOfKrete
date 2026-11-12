"""stacktest contract: a stack's self-test cases and report."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from bull.Modules.stacks.Contracts import Stack


class CaseVerdict(Enum):
    PASS = "pass"
    FAIL = "fail"
    NOT_RUN = "not run"


@dataclass(frozen=True)
class Case:
    id: str
    change: Mapping[str, object]
    run: tuple[str, ...]
    expect: Mapping[str, object]
    then: "Case | None"


@dataclass(frozen=True)
class CaseResult:
    id: str
    verdict: CaseVerdict
    expected: str
    got: str


@dataclass(frozen=True)
class StackTestReport:
    stack: str
    static: bool
    problems: tuple[str, ...]
    cases: tuple[CaseResult, ...]

    @property
    def ok(self) -> bool:
        """True when there are no problems and every case PASSed (NOT_RUN fails)."""
        return not self.problems and all(
            result.verdict is CaseVerdict.PASS for result in self.cases
        )


class StackTester(Protocol):
    def load_cases(self, stack: Stack) -> list[Case]: ...
    def static(self, stack: Stack) -> StackTestReport: ...
    def run(self, stack: Stack, case: str | None = None) -> StackTestReport: ...
    def render(self, report: StackTestReport) -> str: ...
