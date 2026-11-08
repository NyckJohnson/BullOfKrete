"""Shared fakes for the stacks tests: a settings object and a ready-made registry."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from bull.Modules.foundation.Contracts import BullError
from bull.Modules.settings.Contracts import (
    Layer,
    Resolved,
    Setting,
    Settings,
    SettingType,
    SettingValue,
)
from bull.Modules.stacks.Contracts import Stack, StackManifest
from bull.Modules.stacks.mocks import MockStackRegistry, sample_stack


class FakeSettings(Settings):
    """Resolved settings per part. `None` and `"app"` both mean the one-part app."""

    def __init__(
        self,
        app: dict[str, SettingValue],
        parts: dict[str, dict[str, SettingValue]] | None = None,
    ) -> None:
        self.app = dict(app)
        self.parts = dict(parts or {})

    def _values(self, part: str | None) -> dict[str, SettingValue]:
        if part is None or part == "app":
            return self.app
        if part not in self.parts:
            raise BullError(f"unknown part {part}")
        return self.parts[part]

    def values(self, part: str | None = None) -> dict[str, SettingValue]:
        return dict(self._values(part))

    def schema(self) -> list[Setting]:
        return [Setting(k, SettingType.STR, None, k) for k in sorted(self.app)]

    def get(self, key: str, part: str | None = None) -> SettingValue:
        values = self._values(part)
        if key not in values:
            raise BullError(f"unknown setting {key}")
        return values[key]

    def show(self, part: str | None = None) -> list[Resolved]:
        layer = Layer.APP if part in (None, "app") else Layer.PART
        return [
            Resolved(k, v, layer, None) for k, v in sorted(self._values(part).items())
        ]

    def set(
        self, key: str, raw: str, layer: Layer = Layer.APP, part: str | None = None
    ) -> Resolved:
        raise NotImplementedError


def registry_with(
    root: Path | None = None, name: str = "fixture", **changes: object
) -> MockStackRegistry:
    """A mock registry whose `name` stack has manifest fields replaced and `root` as home."""
    registry = MockStackRegistry()
    stack = sample_stack(name)
    manifest: StackManifest = replace(stack.manifest, **changes)  # type: ignore[arg-type]
    registry.stacks[name] = replace(
        stack, manifest=manifest, home=root if root is not None else stack.home
    )
    return registry


def stack_of(registry: MockStackRegistry, name: str = "fixture") -> Stack:
    return registry.stacks[name]
