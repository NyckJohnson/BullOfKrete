"""The gate driver: runs the steps of each mode and decides the verdict."""

from __future__ import annotations

from bull.Modules.coverage.Contracts import CoverageReport
from bull.Modules.foundation.Contracts import AppLayout
from bull.Modules.gates.Contracts import GateRequest, GateRun, Gates


class LiveGates(Gates):
    def run(self, app: AppLayout, request: GateRequest) -> GateRun:
        raise NotImplementedError(f"{type(self).__name__}.run")

    def coverage(self, app: AppLayout, module: str) -> CoverageReport:
        raise NotImplementedError(f"{type(self).__name__}.coverage")

    def render(self, run: GateRun) -> str:
        raise NotImplementedError(f"{type(self).__name__}.render")
