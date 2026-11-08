"""An app's parts, the implicit one-part case and part checks."""

from __future__ import annotations

from pathlib import Path

from bull.Modules.foundation.Contracts import AppLayout
from bull.Modules.parts.Contracts import Part, Parts


class LiveParts(Parts):
    def all(self, app: AppLayout) -> list[Part]:
        raise NotImplementedError(f"{type(self).__name__}.all")

    def get(self, app: AppLayout, name: str | None = None) -> Part:
        raise NotImplementedError(f"{type(self).__name__}.get")

    def add(
        self, app: AppLayout, name: str, stack: str, dir: str | None = None
    ) -> Part:
        raise NotImplementedError(f"{type(self).__name__}.add")

    def check(self, app: AppLayout) -> list[str]:
        raise NotImplementedError(f"{type(self).__name__}.check")

    def module_src(self, part: Part, module: str) -> Path:
        raise NotImplementedError(f"{type(self).__name__}.module_src")

    def module_tests(self, part: Part, module: str) -> Path:
        raise NotImplementedError(f"{type(self).__name__}.module_tests")

    def is_test_path(self, app: AppLayout, path: Path) -> bool:
        raise NotImplementedError(f"{type(self).__name__}.is_test_path")
