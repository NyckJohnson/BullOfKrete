"""Resolved settings: get, show and set across the layers."""

from __future__ import annotations

from bull.Modules.settings.Contracts import (
    Layer,
    Resolved,
    Setting,
    Settings,
    SettingValue,
)


class LiveSettings(Settings):
    def schema(self) -> list[Setting]:
        raise NotImplementedError(f"{type(self).__name__}.schema")

    def get(self, key: str, part: str | None = None) -> SettingValue:
        raise NotImplementedError(f"{type(self).__name__}.get")

    def show(self, part: str | None = None) -> list[Resolved]:
        raise NotImplementedError(f"{type(self).__name__}.show")

    def set(
        self, key: str, raw: str, layer: Layer = Layer.APP, part: str | None = None
    ) -> Resolved:
        raise NotImplementedError(f"{type(self).__name__}.set")
