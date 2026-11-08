"""coverage contract: exemption markers and the triage report."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from bull.Modules.stacks.Contracts import CoverageData


@dataclass(frozen=True)
class Exemption:
    """One valid `coverage-exempt` marker in a source file.

    `lines` are the 1-based lines it exempts (a line marker's own line, or a block's lines from
    begin to end inclusive); `None` means a file marker, which exempts the file from "no data"
    only. `reason` is the marker's non-empty reason text.
    """

    path: Path
    lines: tuple[int, ...] | None
    reason: str


@dataclass(frozen=True)
class MarkerScan:
    """The markers found in one file: the valid exemptions, and one `<path>:<line>: …` message
    per invalid marker (missing reason, unclosed begin, stray end)."""

    exemptions: tuple[Exemption, ...]
    invalid: tuple[str, ...]


@dataclass(frozen=True)
class CoverageReport:
    """The triage report for one module.

    `uncovered`: per source file, the uncovered lines left after exemptions (files with none are
    omitted). `no_data`: sources the coverage tool has no data for and no file marker exempts.
    `exempted`: the exemptions that applied. `invalid_markers`: messages for invalid markers.
    """

    module: str
    uncovered: Mapping[Path, tuple[int, ...]]
    no_data: tuple[Path, ...]
    exempted: tuple[Exemption, ...]
    invalid_markers: tuple[str, ...]

    @property
    def clean(self) -> bool:
        """True when no uncovered lines, no reported no-data files and no invalid markers remain."""
        return (
            not any(self.uncovered.values())
            and not self.no_data
            and not self.invalid_markers
        )


class CoverageTriage(Protocol):
    """Turns a stack's coverage data into the triage report, honoring `coverage-exempt` markers."""

    def markers(self, path: Path, comment: str) -> MarkerScan:
        """Scan `path` for markers written after the line-comment prefix `comment` (e.g. `#`).

        Raises `OSError` if the file cannot be read.
        """
        ...

    def sources(
        self,
        module_dir: Path,
        part_root: Path,
        source_glob: str,
        exclude: Sequence[str],
    ) -> list[Path]:
        """Files under `module_dir` (recursively) matching `source_glob`, minus those whose path
        relative to `part_root` matches any `exclude` glob; sorted."""
        ...

    def report(
        self, module: str, sources: Sequence[Path], data: CoverageData, comment: str
    ) -> CoverageReport:
        """Build the report for `module` from `data`, limited to `sources` and their markers.

        Raises `OSError` if a source cannot be read.
        """
        ...

    def render(self, report: CoverageReport) -> str:
        """Human-readable text of `report`: "coverage clean for <module>", or per file
        `path: lines 3, 7-9`, then files without coverage data and invalid markers."""
        ...
