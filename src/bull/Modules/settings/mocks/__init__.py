"""Mocks of the settings contract, for tests and previews."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from bull.Modules.foundation.Contracts import AppLayout, BullError
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

_USER_AND_APP = frozenset({Layer.USER, Layer.APP})

SAMPLE_SCHEMA: tuple[Setting, ...] = (
    Setting(
        "base_branch",
        SettingType.STR,
        "main",
        "The trunk branch.",
        layers=_USER_AND_APP,
    ),
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
        layers=_USER_AND_APP,
    ),
    Setting(
        "usage.pause_weekly",
        SettingType.INT,
        95,
        "Pause at this weekly usage.",
        minimum=1,
        maximum=100,
        layers=_USER_AND_APP,
    ),
    Setting(
        "models.reviewer",
        SettingType.STR,
        "sonnet",
        "Model for the reviewer.",
        layers=_USER_AND_APP,
    ),
)

# Fake file locations the mock reports as each layer's source, named like the
# real ones: user file outside any `.bull`, app file `.bull/config.toml`, part
# files `.bull/parts/<part>.toml`.
_USER_FILE = Path("/tmp/home/.config/bull/config.toml")
_APP_ROOT = Path("/tmp/apps/tally")


def _source(layer: Layer, part: str | None) -> Path | None:
    if layer is Layer.USER:
        return _USER_FILE
    if layer is Layer.APP:
        return _APP_ROOT / ".bull" / "config.toml"
    if layer is Layer.PART and part is not None:
        return _APP_ROOT / ".bull" / "parts" / f"{part}.toml"
    return None


def _expected(setting: Setting) -> str:
    """The "must be …" phrase for a setting, e.g. "an integer ≥ 1"."""
    if setting.type is SettingType.INT:
        if setting.minimum is not None and setting.maximum is not None:
            return f"an integer {setting.minimum}–{setting.maximum}"
        if setting.minimum is not None:
            return f"an integer ≥ {setting.minimum}"
        if setting.maximum is not None:
            return f"an integer ≤ {setting.maximum}"
        return "an integer"
    if setting.type is SettingType.BOOL:
        return "true or false"
    if setting.type is SettingType.CHOICE:
        return "one of " + ", ".join(setting.choices)
    if setting.type is SettingType.STR_LIST:
        return "a comma-separated list"
    return "text"


def _parse(setting: Setting, raw: str) -> SettingValue:
    """Parse and validate `raw` for `setting`; raise BullError when invalid."""
    error = BullError(
        f"{setting.key} must be {_expected(setting)}",
        f"run `bull config show` to see {setting.key}'s current value",
    )
    text = raw.strip()
    if setting.type is SettingType.INT:
        try:
            number = int(text)
        except ValueError:
            raise error from None
        if setting.minimum is not None and number < setting.minimum:
            raise error
        if setting.maximum is not None and number > setting.maximum:
            raise error
        return number
    if setting.type is SettingType.BOOL:
        if text.lower() == "true":
            return True
        if text.lower() == "false":
            return False
        raise error
    if setting.type is SettingType.CHOICE:
        if text not in setting.choices:
            raise error
        return text
    if setting.type is SettingType.STR_LIST:
        return tuple(item.strip() for item in text.split(",") if item.strip())
    return raw


class MockSettings(Settings):
    """In-memory layered settings over SAMPLE_SCHEMA.

    `values` holds the bull-default layer (tests may override entries); `set`
    validates like the real implementation and stores into the user, app or
    per-part layer. The part layer is consulted only when `part` is given.
    """

    def __init__(self) -> None:
        self._schema = {s.key: s for s in SAMPLE_SCHEMA}
        self.values: dict[str, SettingValue] = {
            s.key: s.default for s in SAMPLE_SCHEMA if s.default is not None
        }
        self.user: dict[str, SettingValue] = {}
        self.app: dict[str, SettingValue] = {}
        self.parts: dict[str, dict[str, SettingValue]] = {}
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def schema(self) -> list[Setting]:
        self.calls.append(("schema", ()))
        return list(SAMPLE_SCHEMA)

    def get(self, key: str, part: str | None = None) -> SettingValue:
        self.calls.append(("get", (key, part)))
        return self._resolve(key, part).value

    def show(self, part: str | None = None) -> list[Resolved]:
        self.calls.append(("show", (part,)))
        return [self._resolve(key, part) for key in sorted(self._schema)]

    def set(
        self, key: str, raw: str, layer: Layer = Layer.APP, part: str | None = None
    ) -> Resolved:
        self.calls.append(("set", (key, raw, layer, part)))
        setting = self._setting(key)
        if layer not in setting.layers or layer in (Layer.BULL, Layer.STACK):
            raise BullError(
                f"{key} can't be set in the {layer.value} layer",
                "allowed: "
                + ", ".join(
                    sorted(
                        lay.value
                        for lay in setting.layers
                        if lay not in (Layer.BULL, Layer.STACK)
                    )
                ),
            )
        if layer is Layer.PART and part is None:
            raise BullError(f"{key}: the part layer needs a part", "pass --part <part>")
        value = _parse(setting, raw)
        if layer is Layer.USER:
            self.user[key] = value
        elif layer is Layer.APP:
            self.app[key] = value
        else:
            assert part is not None  # checked above
            self.parts.setdefault(part, {})[key] = value
        return Resolved(key, value, layer, _source(layer, part))

    def _setting(self, key: str) -> Setting:
        setting = self._schema.get(key)
        if setting is None:
            raise BullError(
                f"unknown setting `{key}`", "run `bull config show` to list settings"
            )
        return setting

    def _resolve(self, key: str, part: str | None) -> Resolved:
        self._setting(key)
        if part is not None and key in self.parts.get(part, {}):
            return Resolved(
                key, self.parts[part][key], Layer.PART, _source(Layer.PART, part)
            )
        if key in self.app:
            return Resolved(key, self.app[key], Layer.APP, _source(Layer.APP, None))
        if key in self.user:
            return Resolved(key, self.user[key], Layer.USER, _source(Layer.USER, None))
        if key in self.values:
            return Resolved(key, self.values[key], Layer.BULL, None)
        raise BullError(
            f"{key} has no value", f"set it with `bull config set {key} <value>`"
        )


class MockSettingsLoader(SettingsLoader):
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings if settings is not None else MockSettings()
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def load(
        self, app: AppLayout | None, stack_layer: Callable[[str], StackLayer]
    ) -> Settings:
        self.calls.append(("load", (app, stack_layer)))
        return self.settings
