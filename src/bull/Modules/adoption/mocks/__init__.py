"""Mocks of the adoption contract, for tests and previews."""

from __future__ import annotations

from pathlib import Path

from bull.Modules.adoption.Contracts import Adoption, DetectionReport, LegacyLeft
from bull.Modules.foundation.Contracts import AppLayout
from bull.Modules.stacks.Contracts import Detection, Issue, IssueLevel

SAMPLE_DETECTION = Detection(
    confidence=0.9,
    summary="fixture app: fixture.toml and 6 .fx files",
    settings={"source_dir": "src/fx", "test_dir": "tests"},
    issues=(),
)


class MockAdoption(Adoption):
    """Detects the `fixture` stack with one note; legacy code left: one file."""

    def __init__(self) -> None:
        self.report = DetectionReport(
            stack="fixture",
            detection=SAMPLE_DETECTION,
            issues=(Issue(IssueLevel.NOTE, "active git hook pre-commit", ""),),
        )
        self.left = LegacyLeft(
            files=("src/fx/counter.fx",),
            declarations=(),
            tests=("tests/counter.test",),
            memo_files=(),
        )
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def detect(self, root: Path) -> DetectionReport:
        self.calls.append(("detect", (root,)))
        return self.report

    def apply(
        self, app: AppLayout, report: DetectionReport, stack: str | None = None
    ) -> None:
        self.calls.append(("apply", (app, report, stack)))

    def start(self, app: AppLayout) -> None:
        self.calls.append(("start", (app,)))

    def legacy(self, app: AppLayout) -> LegacyLeft:
        self.calls.append(("legacy", (app,)))
        return self.left

    def finish(self, app: AppLayout) -> None:
        self.calls.append(("finish", (app,)))

    def abandon(self, app: AppLayout) -> None:
        self.calls.append(("abandon", (app,)))
