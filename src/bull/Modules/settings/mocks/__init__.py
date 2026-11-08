"""Mocks of the settings contract, for tests and previews."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from bull.Modules.foundation.Contracts import AppLayout
from bull.Modules.settings.Contracts import (
    Layer,
    Resolved,
    Setting,
    Settings,
    SettingsLoader,
    SettingType,
    SettingValue,
    StackLayer,
)

SAMPLE_SCHEMA: tuple[Setting, ...] = (
    Setting("base_branch", SettingType.STR, "main", "The trunk branch."),
    Setting(
        "review_mode",
        SettingType.CHOICE,
        "combined",
        "One review pass or one per category.",
        choices=("combined", "split"),
    ),
    Setting("max_attempts", SettingType.INT, 3, "Attempts per work unit.", minimum=1),
    Setting(
        "max_files_per_unit", SettingType.INT, 4, "Files per work unit.", minimum=1
    ),
    Setting(
        "usage.pause_5h",
        SettingType.INT,
        85,
        "Pause at this 5-hour usage.",
        minimum=1,
        maximum=100,
    ),
    Setting(
        "usage.pause_weekly",
        SettingType.INT,
        95,
        "Pause at this weekly usage.",
        minimum=1,
        maximum=100,
    ),
    Setting("models.reviewer", SettingType.STR, "sonnet", "Model for the reviewer."),
)


class MockSettings(Settings):
    """Bull's defaults, overridable through `values`; `set` stores into `values`."""

    def __init__(self) -> None:
        self.values: dict[str, SettingValue] = {
            s.key: s.default for s in SAMPLE_SCHEMA if s.default is not None
        }
        self.layers: dict[str, Layer] = {}
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def schema(self) -> list[Setting]:
        self.calls.append(("schema", ()))
        return list(SAMPLE_SCHEMA)

    def get(self, key: str, part: str | None = None) -> SettingValue:
        self.calls.append(("get", (key, part)))
        return self.values[key]

    def show(self, part: str | None = None) -> list[Resolved]:
        self.calls.append(("show", (part,)))
        return [
            Resolved(key, value, self.layers.get(key, Layer.BULL), None)
            for key, value in sorted(self.values.items())
        ]

    def set(
        self, key: str, raw: str, layer: Layer = Layer.APP, part: str | None = None
    ) -> Resolved:
        self.calls.append(("set", (key, raw, layer, part)))
        value: SettingValue = int(raw) if raw.isdigit() else raw
        self.values[key] = value
        self.layers[key] = layer
        return Resolved(key, value, layer, Path("/tmp/apps/tally/.bull/config.toml"))


class MockSettingsLoader(SettingsLoader):
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings if settings is not None else MockSettings()
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def load(
        self, app: AppLayout | None, stack_layer: Callable[[str], StackLayer]
    ) -> Settings:
        self.calls.append(("load", (app, stack_layer)))
        return self.settings
