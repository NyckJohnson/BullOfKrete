"""Test counts, failed ids and coverage from result bundles."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from bull.Modules.stacks.Contracts import CoverageData, TestRun


def test_results(results: Path) -> TestRun | None:
    """Test count and failed ids from the result bundles in `results` (unit 3)."""
    raise NotImplementedError("xcresults.test_results")


def uncovered(part_root: Path, sources: Sequence[Path], results: Path) -> CoverageData:
    """Uncovered lines of `sources` from the result bundles in `results` (unit 3)."""
    raise NotImplementedError("xcresults.uncovered")
