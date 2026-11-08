"""Mocks of the gates contract, for tests and previews."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from bull.Modules.coverage.Contracts import CoverageReport
from bull.Modules.foundation.Contracts import AppLayout
from bull.Modules.gates.Contracts import (
    Gate,
    GateRequest,
    GateRun,
    Gates,
    PassRecord,
    PassRecords,
    StepResult,
    Verdict,
)

SAMPLE_TIME = datetime(2026, 11, 7, 12, 0, 0, tzinfo=UTC)


def sample_run(request: GateRequest) -> GateRun:
    """A passing `gates Counter` run on the implicit part, recorded."""
    module = request.module

    def step(gate: Gate, seconds: float) -> StepResult:
        return StepResult(gate, "app", module, Verdict.PASS, (), seconds, "")

    return GateRun(
        request=request,
        verdict=Verdict.PASS,
        steps=(
            step(Gate.PREFLIGHT, 0.1),
            step(Gate.SETUP, 0.2),
            step(Gate.BUILD, 1.4),
            step(Gate.TESTS, 2.3),
            step(Gate.LINT, 0.3),
            step(Gate.API, 0.1),
            step(Gate.COVERAGE, 0.2),
        ),
        tests_run=12,
        failed_ids={},
        coverage=(
            CoverageReport(
                module=module or "Counter",
                uncovered={},
                no_data=(),
                exempted=(),
                invalid_markers=(),
            ),
        ),
        recorded=True,
        note="",
    )


class MockGates(Gates):
    """Every run passes; set `result` to return a fixed run instead."""

    def __init__(self) -> None:
        self.result: GateRun | None = None
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def run(self, app: AppLayout, request: GateRequest) -> GateRun:
        self.calls.append(("run", (app, request)))
        return self.result or sample_run(request)

    def coverage(self, app: AppLayout, module: str) -> CoverageReport:
        self.calls.append(("coverage", (app, module)))
        return CoverageReport(module, {}, (), (), ())

    def render(self, run: GateRun) -> str:
        self.calls.append(("render", (run,)))
        lines = [
            f"{'✓' if s.verdict is Verdict.PASS else '✗'} {s.gate.value} {s.part}"
            + (f" {s.module}" if s.module else "")
            for s in run.steps
        ]
        lines.append("recorded" if run.recorded else run.note)
        return "\n".join(lines) + "\n"


class MockPassRecords(PassRecords):
    def __init__(self) -> None:
        self.records: dict[str, PassRecord] = {}
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def record(
        self,
        app: AppLayout,
        sha: str,
        branch: str | None,
        command: str,
        parts: Sequence[str],
    ) -> None:
        self.calls.append(("record", (app, sha, branch, command, tuple(parts))))
        self.records[sha] = PassRecord(sha, branch, command, SAMPLE_TIME, tuple(parts))

    def get(self, app: AppLayout, sha: str) -> PassRecord | None:
        self.calls.append(("get", (app, sha)))
        return self.records.get(sha)
