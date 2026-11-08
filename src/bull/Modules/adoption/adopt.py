"""Adoption: detection report, apply, start, legacy check, finish and abandon."""

from __future__ import annotations

from pathlib import Path

from bull.Modules.adoption.Contracts import Adoption, DetectionReport, LegacyLeft
from bull.Modules.foundation.Contracts import AppLayout


class LiveAdoption(Adoption):
    def detect(self, root: Path) -> DetectionReport:
        raise NotImplementedError(f"{type(self).__name__}.detect")

    def apply(
        self, app: AppLayout, report: DetectionReport, stack: str | None = None
    ) -> None:
        raise NotImplementedError(f"{type(self).__name__}.apply")

    def start(self, app: AppLayout) -> None:
        raise NotImplementedError(f"{type(self).__name__}.start")

    def legacy(self, app: AppLayout) -> LegacyLeft:
        raise NotImplementedError(f"{type(self).__name__}.legacy")

    def finish(self, app: AppLayout) -> None:
        raise NotImplementedError(f"{type(self).__name__}.finish")

    def abandon(self, app: AppLayout) -> None:
        raise NotImplementedError(f"{type(self).__name__}.abandon")
