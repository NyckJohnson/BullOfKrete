"""coverage contract: exemption markers and the triage report."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from bull.Modules.stacks.Contracts import CoverageData


@dataclass(frozen=True)
class Exemption:
    path: Path
    lines: tuple[int, ...] | None
    reason: str  # None: whole file (no-data only)


@dataclass(frozen=True)
class MarkerScan:
    exemptions: tuple[Exemption, ...]
    invalid: tuple[str, ...]


@dataclass(frozen=True)
class CoverageReport:
    module: str
    uncovered: Mapping[Path, tuple[int, ...]]
    no_data: tuple[Path, ...]
    exempted: tuple[Exemption, ...]
    invalid_markers: tuple[str, ...]

    @property
    def clean(self) -> bool:
        raise NotImplementedError(f"{type(self).__name__}.clean")


class CoverageTriage(Protocol):
    def markers(self, path: Path, comment: str) -> MarkerScan: ...
    def sources(
        self,
        module_dir: Path,
        part_root: Path,
        source_glob: str,
        exclude: Sequence[str],
    ) -> list[Path]: ...
    def report(
        self, module: str, sources: Sequence[Path], data: CoverageData, comment: str
    ) -> CoverageReport: ...
    def render(self, report: CoverageReport) -> str: ...
