"""The coverage triage report."""

from __future__ import annotations

from collections.abc import Sequence
from fnmatch import fnmatchcase
from pathlib import Path

from bull.Modules.coverage.Contracts import (
    CoverageReport,
    CoverageTriage,
    Exemption,
    MarkerScan,
)
from bull.Modules.coverage.markers import scan_markers, scan_markers_with_file_lines
from bull.Modules.stacks.Contracts import CoverageData


class LiveCoverageTriage(CoverageTriage):
    """The real `CoverageTriage`: reads source files from disk."""

    def markers(self, path: Path, comment: str) -> MarkerScan:
        return scan_markers(path, comment)

    def sources(
        self,
        module_dir: Path,
        part_root: Path,
        source_glob: str,
        exclude: Sequence[str],
    ) -> list[Path]:
        found: list[Path] = []
        for path in module_dir.rglob(source_glob):
            if not path.is_file():
                continue
            if exclude and _excluded(path, part_root, exclude):
                continue
            found.append(path)
        return sorted(found)

    def report(
        self, module: str, sources: Sequence[Path], data: CoverageData, comment: str
    ) -> CoverageReport:
        uncovered: dict[Path, tuple[int, ...]] = {}
        no_data: list[Path] = []
        exempted: list[Exemption] = []
        invalid: list[str] = []
        missing = set(data.no_data)

        for source in sources:
            scan, file_marker_lines = scan_markers_with_file_lines(source, comment)
            invalid.extend(scan.invalid)
            line_exemptions = [ex for ex in scan.exemptions if ex.lines is not None]
            file_exemptions = [ex for ex in scan.exemptions if ex.lines is None]
            exempted.extend(line_exemptions)

            if source in missing:
                # A file marker exempts a file only from "no data".
                if file_exemptions:
                    exempted.extend(file_exemptions)
                else:
                    no_data.append(source)
                continue

            # A file with data needs no file marker: report it so it gets removed.
            invalid.extend(
                f"{source}:{number}: unnecessary file marker"
                for number in file_marker_lines
            )
            exempt_lines = {n for ex in line_exemptions for n in ex.lines or ()}
            remaining = tuple(
                n
                for n in sorted(data.uncovered.get(source, ()))
                if n not in exempt_lines
            )
            if remaining:
                uncovered[source] = remaining

        return CoverageReport(
            module=module,
            uncovered=uncovered,
            no_data=tuple(no_data),
            exempted=tuple(exempted),
            invalid_markers=tuple(invalid),
        )

    def render(self, report: CoverageReport) -> str:
        if report.clean:
            return f"coverage clean for {report.module}\n"
        lines: list[str] = []
        for path in sorted(report.uncovered, key=str):
            numbers = report.uncovered[path]
            if numbers:
                lines.append(f"{path}: lines {_collapse(numbers)}")
        if report.no_data:
            lines.append("without coverage data:")
            lines.extend(f"  {path}" for path in report.no_data)
        if report.invalid_markers:
            lines.append("invalid coverage-exempt markers:")
            lines.extend(f"  {message}" for message in report.invalid_markers)
        return "\n".join(lines) + "\n"


def _excluded(path: Path, part_root: Path, exclude: Sequence[str]) -> bool:
    # Globs match the POSIX path relative to the part root; `*` may cross `/` (fnmatch rules).
    try:
        relative = path.relative_to(part_root).as_posix()
    except ValueError:
        relative = path.as_posix()
    return any(fnmatchcase(relative, pattern) for pattern in exclude)


def _collapse(numbers: Sequence[int]) -> str:
    """`(3, 7, 8, 9)` → `"3, 7-9"`: consecutive runs collapse into ranges."""
    parts: list[str] = []
    ordered = sorted(set(numbers))
    start = prev = ordered[0]
    for n in ordered[1:]:
        if n == prev + 1:
            prev = n
            continue
        parts.append(f"{start}-{prev}" if prev != start else str(start))
        start = prev = n
    parts.append(f"{start}-{prev}" if prev != start else str(start))
    return ", ".join(parts)
