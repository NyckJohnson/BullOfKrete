"""api contract: contract snapshots and their checks."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from bull.Modules.foundation.Contracts import AppLayout, BullError


class ApprovalNeeded(BullError): ...


@dataclass(frozen=True)
class Snapshot:
    name: str
    files: Mapping[str, tuple[str, ...]]  # relative path → declarations


@dataclass(frozen=True)
class ApiCheck:
    name: str
    ok: bool
    stored: bool
    diff: str


class ApiSnapshots(Protocol):
    def current(self, app: AppLayout, module: str) -> Snapshot: ...
    def check(self, app: AppLayout, module: str) -> ApiCheck: ...
    def write(
        self, app: AppLayout, module: str, approved: str | None = None
    ) -> Path | None: ...
    def check_interface(self, app: AppLayout, name: str) -> ApiCheck: ...
    def write_interface(
        self, app: AppLayout, name: str, approved: str | None = None
    ) -> Path | None: ...
    def render(self, snapshot: Snapshot) -> str: ...
    def parse(self, text: str) -> Snapshot: ...
