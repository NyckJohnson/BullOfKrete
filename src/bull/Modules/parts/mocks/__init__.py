"""Mocks of the parts contract, for tests and previews."""

from __future__ import annotations

from pathlib import Path

from bull.Modules.foundation.Contracts import AppLayout
from bull.Modules.parts.Contracts import Part, Parts


def sample_part(root: Path = Path("/tmp/apps/tally"), name: str = "app") -> Part:
    """The implicit part of a one-part `fixture` app."""
    return Part(
        name=name,
        stack="fixture",
        dir=".",
        root=root,
        source_dir=Path("src/fx"),
        test_dir=Path("tests"),
    )


class MockParts(Parts):
    """One implicit part `app`; `add` appends to `parts`."""

    def __init__(self) -> None:
        self.parts: list[Part] = [sample_part()]
        self.problems: list[str] = []
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def all(self, app: AppLayout) -> list[Part]:
        self.calls.append(("all", (app,)))
        return list(self.parts)

    def get(self, app: AppLayout, name: str | None = None) -> Part:
        self.calls.append(("get", (app, name)))
        if name is None:
            return self.parts[0]
        return next(p for p in self.parts if p.name == name)

    def add(
        self, app: AppLayout, name: str, stack: str, dir: str | None = None
    ) -> Part:
        self.calls.append(("add", (app, name, stack, dir)))
        folder = dir if dir is not None else name
        part = Part(
            name=name,
            stack=stack,
            dir=folder,
            root=app.root / folder,
            source_dir=Path("src"),
            test_dir=Path("tests"),
        )
        self.parts.append(part)
        return part

    def check(self, app: AppLayout) -> list[str]:
        self.calls.append(("check", (app,)))
        return list(self.problems)

    def module_src(self, part: Part, module: str) -> Path:
        self.calls.append(("module_src", (part, module)))
        return part.root / part.source_dir / "Modules" / module

    def module_tests(self, part: Part, module: str) -> Path:
        self.calls.append(("module_tests", (part, module)))
        return part.root / part.test_dir / module

    def is_test_path(self, app: AppLayout, path: Path) -> bool:
        self.calls.append(("is_test_path", (app, path)))
        return "tests" in path.parts or path.suffix == ".test"
