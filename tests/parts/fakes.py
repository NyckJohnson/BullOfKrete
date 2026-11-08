"""Shared fakes for the parts tests: settings, a registry and app-folder helpers."""

from __future__ import annotations

from pathlib import Path

from bull.Modules.foundation.Contracts import AppLayout, BullError
from bull.Modules.foundation.mocks import sample_layout
from bull.Modules.settings.Contracts import (
    Layer,
    Resolved,
    Setting,
    Settings,
    SettingType,
    SettingValue,
)
from bull.Modules.settings.mocks import MockSettingsLoader
from bull.Modules.stacks.mocks import MockStackRegistry

DEFAULTS: dict[str, SettingValue] = {"source_dir": "src/fx", "test_dir": "tests"}


class FakeSettings(Settings):
    """Resolved settings per part; parts without overrides get the fixture defaults.

    `None` and `"app"` both mean the implicit one-part app.
    """

    def __init__(self, overrides: dict[str, dict[str, SettingValue]] | None = None):
        self.overrides = dict(overrides or {})

    def schema(self) -> list[Setting]:
        return [Setting(k, SettingType.STR, None, k) for k in sorted(DEFAULTS)]

    def get(self, key: str, part: str | None = None) -> SettingValue:
        values = {**DEFAULTS, **self.overrides.get(part or "app", {})}
        if key not in values:
            raise BullError(f"unknown setting {key}")
        return values[key]

    def show(self, part: str | None = None) -> list[Resolved]:
        return []

    def set(
        self, key: str, raw: str, layer: Layer = Layer.APP, part: str | None = None
    ) -> Resolved:
        raise NotImplementedError


def loader_with(
    overrides: dict[str, dict[str, SettingValue]] | None = None,
) -> MockSettingsLoader:
    return MockSettingsLoader(FakeSettings(overrides))


def new_app(
    tmp_path: Path,
    config: str | None = 'format = 1\nstack = "fixture"\n',
    gitignore: str | None = None,
) -> AppLayout:
    """A real app folder under `tmp_path`; `config=None` writes no config.toml."""
    root = tmp_path / "app"
    root.mkdir()
    app = sample_layout(root)
    app.bull_dir.mkdir()
    if config is not None:
        app.config_file.write_text(config, encoding="utf-8")
    if gitignore is not None:
        (root / ".gitignore").write_text(gitignore, encoding="utf-8")
    return app


def write_part(
    app: AppLayout, name: str, stack: str = "fixture", dir: str | None = None
) -> None:
    """Write `.bull/parts/<name>.toml` and the part's folders."""
    folder = dir if dir is not None else name
    app.parts_dir.mkdir(parents=True, exist_ok=True)
    (app.parts_dir / f"{name}.toml").write_text(
        f'format = 1\nstack = "{stack}"\ndir = "{folder}"\n', encoding="utf-8"
    )
    for sub in ("src/fx", "tests"):
        (app.root / folder / sub).mkdir(parents=True, exist_ok=True)


def registry() -> MockStackRegistry:
    return MockStackRegistry()
