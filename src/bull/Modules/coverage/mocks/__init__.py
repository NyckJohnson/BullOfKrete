"""Mocks of the coverage contract, for tests and previews."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from bull.Modules.coverage.Contracts import (
    CoverageReport,
    CoverageTriage,
    Exemption,
    MarkerScan,
)
from bull.Modules.stacks.Contracts import CoverageData

SAMPLE_SOURCE = Path("/tmp/apps/tally/src/fx/Modules/Counter/counter.fx")


def sample_report(module: str = "Counter") -> CoverageReport:
    """Lines 3 and 7-9 of counter.fx uncovered; one exempted line."""
    return CoverageReport(
        module=module,
        uncovered={SAMPLE_SOURCE: (3, 7, 8, 9)},
        no_data=(),
        exempted=(Exemption(SAMPLE_SOURCE, (12,), "defensive branch"),),
        invalid_markers=(),
    )


class MockCoverageTriage(CoverageTriage):
    def __init__(self) -> None:
        self.result = sample_report()
        self.scan = MarkerScan(exemptions=(), invalid=())
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def markers(self, path: Path, comment: str) -> MarkerScan:
        self.calls.append(("markers", (path, comment)))
        return self.scan

    def sources(
        self,
        module_dir: Path,
        part_root: Path,
        source_glob: str,
        exclude: Sequence[str],
    ) -> list[Path]:
        self.calls.append(
            ("sources", (module_dir, part_root, source_glob, tuple(exclude)))
        )
        return [module_dir / "counter.fx"]

    def report(
        self, module: str, sources: Sequence[Path], data: CoverageData, comment: str
    ) -> CoverageReport:
        self.calls.append(("report", (module, tuple(sources), data, comment)))
        return self.result

    def render(self, report: CoverageReport) -> str:
        self.calls.append(("render", (report,)))
        return f"{SAMPLE_SOURCE}: lines 3, 7-9\n"
