"""adoption contract: detection, start / finish / abandon and the legacy check."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from bull.Modules.foundation.Contracts import AppLayout
from bull.Modules.stacks.Contracts import Detection, Issue, IssueLevel


@dataclass(frozen=True)
class DetectionReport:
    """What detection found: the chosen stack (if any), its detection, and every issue."""

    stack: str | None
    detection: Detection | None
    issues: tuple[Issue, ...]

    @property
    def blocked(self) -> bool:
        """True exactly when any issue has level `IssueLevel.BLOCK`."""
        return any(issue.level is IssueLevel.BLOCK for issue in self.issues)


@dataclass(frozen=True)
class LegacyLeft:
    """Legacy code still present: files, declarations, tests and memo `Legacy files:` entries."""

    files: tuple[str, ...]
    declarations: tuple[str, ...]
    tests: tuple[str, ...]
    memo_files: tuple[str, ...]

    @property
    def empty(self) -> bool:
        """True exactly when no legacy files, declarations, tests or memo files are left."""
        return not (self.files or self.declarations or self.tests or self.memo_files)


class Adoption(Protocol):
    def detect(self, root: Path) -> DetectionReport: ...
    def apply(
        self, app: AppLayout, report: DetectionReport, stack: str | None = None
    ) -> None: ...
    def start(self, app: AppLayout) -> None: ...
    def legacy(self, app: AppLayout) -> LegacyLeft: ...
    def finish(self, app: AppLayout) -> None: ...
    def abandon(self, app: AppLayout) -> None: ...
