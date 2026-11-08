"""Contract snapshots of modules and interfaces."""

from __future__ import annotations

from pathlib import Path

from bull.Modules.api.Contracts import ApiCheck, ApiSnapshots, Snapshot
from bull.Modules.foundation.Contracts import AppLayout


class LiveApiSnapshots(ApiSnapshots):
    def current(self, app: AppLayout, module: str) -> Snapshot:
        raise NotImplementedError(f"{type(self).__name__}.current")

    def check(self, app: AppLayout, module: str) -> ApiCheck:
        raise NotImplementedError(f"{type(self).__name__}.check")

    def write(
        self, app: AppLayout, module: str, approved: str | None = None
    ) -> Path | None:
        raise NotImplementedError(f"{type(self).__name__}.write")

    def check_interface(self, app: AppLayout, name: str) -> ApiCheck:
        raise NotImplementedError(f"{type(self).__name__}.check_interface")

    def write_interface(
        self, app: AppLayout, name: str, approved: str | None = None
    ) -> Path | None:
        raise NotImplementedError(f"{type(self).__name__}.write_interface")

    def render(self, snapshot: Snapshot) -> str:
        raise NotImplementedError(f"{type(self).__name__}.render")

    def parse(self, text: str) -> Snapshot:
        raise NotImplementedError(f"{type(self).__name__}.parse")
