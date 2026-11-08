"""The stack's readers: the functions bull imports from this folder."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from bull.Modules.stacks.Contracts import CheckItem, CoverageData, Detection, TestRun


def contract_declarations(path: Path) -> list[str]:
    raise NotImplementedError("readers.contract_declarations")


def test_results(results: Path) -> TestRun | None:
    raise NotImplementedError("readers.test_results")


def uncovered(part_root: Path, sources: Sequence[Path], results: Path) -> CoverageData:
    raise NotImplementedError("readers.uncovered")


def check(
    part_root: Path, settings: Mapping[str, object], adopting: bool
) -> list[CheckItem]:
    raise NotImplementedError("readers.check")


def detect(root: Path) -> Detection:
    raise NotImplementedError("readers.detect")


def inventory(root: Path, settings: Mapping[str, object]) -> str:
    raise NotImplementedError("readers.inventory")


def legacy_declarations(path: Path) -> list[str]:
    raise NotImplementedError("readers.legacy_declarations")
