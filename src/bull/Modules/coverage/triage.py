"""The coverage triage report."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from bull.Modules.coverage.Contracts import CoverageReport, CoverageTriage, MarkerScan
from bull.Modules.stacks.Contracts import CoverageData


class LiveCoverageTriage(CoverageTriage):
    def markers(self, path: Path, comment: str) -> MarkerScan:
        raise NotImplementedError(f"{type(self).__name__}.markers")

    def sources(
        self,
        module_dir: Path,
        part_root: Path,
        source_glob: str,
        exclude: Sequence[str],
    ) -> list[Path]:
        raise NotImplementedError(f"{type(self).__name__}.sources")

    def report(
        self, module: str, sources: Sequence[Path], data: CoverageData, comment: str
    ) -> CoverageReport:
        raise NotImplementedError(f"{type(self).__name__}.report")

    def render(self, report: CoverageReport) -> str:
        raise NotImplementedError(f"{type(self).__name__}.render")
