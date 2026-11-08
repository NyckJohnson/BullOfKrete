"""adoption contract: detection, start / finish / abandon and the legacy check."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from bull.Modules.foundation.Contracts import AppLayout
from bull.Modules.stacks.Contracts import Detection, Issue


@dataclass(frozen=True)
class DetectionReport:
    stack: str | None
    detection: Detection | None
    issues: tuple[Issue, ...]

    @property
    def blocked(self) -> bool:
        raise NotImplementedError(f"{type(self).__name__}.blocked")


@dataclass(frozen=True)
class LegacyLeft:
    files: tuple[str, ...]
    declarations: tuple[str, ...]
    tests: tuple[str, ...]
    memo_files: tuple[str, ...]

    @property
    def empty(self) -> bool:
        raise NotImplementedError(f"{type(self).__name__}.empty")


class Adoption(Protocol):
    def detect(self, root: Path) -> DetectionReport: ...
    def apply(
        self, app: AppLayout, report: DetectionReport, stack: str | None = None
    ) -> None: ...
    def start(self, app: AppLayout) -> None: ...
    def legacy(self, app: AppLayout) -> LegacyLeft: ...
    def finish(self, app: AppLayout) -> None: ...
    def abandon(self, app: AppLayout) -> None: ...
