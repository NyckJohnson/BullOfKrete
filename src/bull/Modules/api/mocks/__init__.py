"""Mocks of the api contract, for tests and previews."""

from __future__ import annotations

from pathlib import Path

from bull.Modules.api.Contracts import ApiCheck, ApiSnapshots, Snapshot
from bull.Modules.foundation.Contracts import AppLayout


def sample_snapshot(name: str = "Counter") -> Snapshot:
    return Snapshot(
        name=name,
        files={"Contracts/counter.fx": ("pub counter.increment", "pub counter.value")},
    )


class MockApiSnapshots(ApiSnapshots):
    """Every check passes by default; set `result` to a failing `ApiCheck` to test the gate."""

    def __init__(self) -> None:
        self.result: ApiCheck | None = None
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def current(self, app: AppLayout, module: str) -> Snapshot:
        self.calls.append(("current", (app, module)))
        return sample_snapshot(module)

    def check(self, app: AppLayout, module: str) -> ApiCheck:
        self.calls.append(("check", (app, module)))
        return self.result or ApiCheck(name=module, ok=True, stored=True, diff="")

    def write(
        self, app: AppLayout, module: str, approved: str | None = None
    ) -> Path | None:
        self.calls.append(("write", (app, module, approved)))
        return app.api_dir / f"{module}.md"

    def check_interface(self, app: AppLayout, name: str) -> ApiCheck:
        self.calls.append(("check_interface", (app, name)))
        return self.result or ApiCheck(name=name, ok=True, stored=True, diff="")

    def write_interface(
        self, app: AppLayout, name: str, approved: str | None = None
    ) -> Path | None:
        self.calls.append(("write_interface", (app, name, approved)))
        return app.api_dir / "interfaces" / f"{name}.md"

    def render(self, snapshot: Snapshot) -> str:
        self.calls.append(("render", (snapshot,)))
        lines = [f"# {snapshot.name} contract", ""]
        for path, declarations in sorted(snapshot.files.items()):
            lines += [f"## {path}", "```", *declarations, "```", ""]
        return "\n".join(lines)

    def parse(self, text: str) -> Snapshot:
        self.calls.append(("parse", (text,)))
        return sample_snapshot()
