"""gates contract: gate requests, runs, step results and pass records."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol

from bull.Modules.coverage.Contracts import CoverageReport
from bull.Modules.foundation.Contracts import AppLayout


class Gate(Enum):
    PREFLIGHT = "preflight"
    SETUP = "setup"
    BUILD = "build"
    TESTS = "tests"
    LINT = "lint"
    API = "api"
    COVERAGE = "coverage"
    INTERFACE = "interface"
    JOURNEYS = "journeys"


class Verdict(Enum):
    PASS = "pass"
    FAIL = "fail"
    ABORTED = "aborted"


class GateMode(Enum):
    MODULE = "module"
    FAST = "fast"
    FAILED = "failed"
    COVERAGE_REPORT = "coverage-report"
    ALL = "all"
    AFTER_MERGE = "after-merge"
    JOURNEYS = "journeys"


@dataclass(frozen=True)
class GateRequest:
    mode: GateMode
    module: str | None = None
    branch: str | None = None
    skip_coverage: bool = False


@dataclass(frozen=True)
class StepResult:
    gate: Gate
    part: str
    module: str | None
    verdict: Verdict
    labels: tuple[str, ...]
    seconds: float
    output_tail: str


@dataclass(frozen=True)
class GateRun:
    request: GateRequest
    verdict: Verdict
    steps: tuple[StepResult, ...]
    tests_run: int
    failed_ids: Mapping[str, tuple[str, ...]]
    coverage: tuple[CoverageReport, ...]
    recorded: bool
    note: str


@dataclass(frozen=True)
class PassRecord:
    sha: str
    branch: str | None
    command: str
    time: datetime
    parts: tuple[str, ...]


class Gates(Protocol):
    def run(self, app: AppLayout, request: GateRequest) -> GateRun: ...
    def coverage(self, app: AppLayout, module: str) -> CoverageReport: ...
    def render(self, run: GateRun) -> str: ...


class PassRecords(Protocol):
    def record(
        self,
        app: AppLayout,
        sha: str,
        branch: str | None,
        command: str,
        parts: Sequence[str],
    ) -> None: ...
    def get(self, app: AppLayout, sha: str) -> PassRecord | None: ...
