"""The gate run report and its JSON form."""

from __future__ import annotations

from collections.abc import Mapping

from bull.Modules.coverage.Contracts import CoverageTriage
from bull.Modules.gates.Contracts import GateRun


def render(run: GateRun, triage: CoverageTriage, comments: Mapping[str, str]) -> str:
    raise NotImplementedError("report.render")
