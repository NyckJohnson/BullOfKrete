"""Mocks of the stacktest contract, for tests and previews."""

from __future__ import annotations

from bull.Modules.stacks.Contracts import Stack
from bull.Modules.stacktest.Contracts import (
    Case,
    CaseResult,
    CaseVerdict,
    StackTester,
    StackTestReport,
)

SAMPLE_CASES = (
    Case(
        id="clean",
        change={},
        run=("gates", "counter"),
        expect={"verdict": "pass", "recorded": True},
        then=None,
    ),
    Case(
        id="failing-test",
        change={"replace": {"tests/counter/a.test": "fail one\n"}},
        run=("gates", "counter"),
        expect={"verdict": "fail", "gate": "tests", "output": "one"},
        then=Case(
            id="failing-test/then",
            change={},
            run=("gates", "--failed"),
            expect={"verdict": "fail", "ran": 1},
            then=None,
        ),
    ),
)


class MockStackTester(StackTester):
    """Every case passes; `report` can be replaced to test failures."""

    def __init__(self) -> None:
        self.cases: list[Case] = list(SAMPLE_CASES)
        self.report: StackTestReport | None = None
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def _passing(
        self, stack: Stack, static: bool, case: str | None = None
    ) -> StackTestReport:
        results = (
            ()
            if static
            else tuple(
                CaseResult(c.id, CaseVerdict.PASS, verdict, verdict)
                for c in self.cases
                if case is None or c.id == case
                for verdict in (str(c.expect.get("verdict")),)
            )
        )
        return StackTestReport(stack.manifest.name, static, (), results)

    def load_cases(self, stack: Stack) -> list[Case]:
        self.calls.append(("load_cases", (stack,)))
        return list(self.cases)

    def static(self, stack: Stack) -> StackTestReport:
        self.calls.append(("static", (stack,)))
        return self.report or self._passing(stack, static=True)

    def run(self, stack: Stack, case: str | None = None) -> StackTestReport:
        self.calls.append(("run", (stack, case)))
        return self.report or self._passing(stack, static=False, case=case)

    def render(self, report: StackTestReport) -> str:
        self.calls.append(("render", (report,)))
        lines = [f"stack test {report.stack}"]
        lines += [f"  {r.verdict.value:8} {r.id}" for r in report.cases]
        lines += [f"  problem: {p}" for p in report.problems]
        return "\n".join(lines) + "\n"
