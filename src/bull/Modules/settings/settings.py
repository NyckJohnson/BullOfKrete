"""Resolved settings: get, show and set across the layers."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from bull.Modules.foundation.Contracts import BullError
from bull.Modules.settings.Contracts import (
    Layer,
    Resolved,
    Setting,
    Settings,
    SettingValue,
    StackLayer,
)
from bull.Modules.settings.schema import BULL_SCHEMA, find_setting, parse_value
from bull.Modules.settings.toml_edit import set_key

_NEW_FILE_TEXT = "format = 1\n"
_FILE_LAYERS = (Layer.USER, Layer.APP, Layer.PART)


@dataclass
class LayerFile:
    """One settings file's validated values (dotted keys), as read by the loader."""

    layer: Layer
    path: Path
    values: dict[str, SettingValue] = field(default_factory=dict)


def unknown_setting(key: str) -> BullError:
    """The error for a key no schema knows."""
    return BullError(
        f"unknown setting `{key}`", fix="run `bull config show` to list the settings"
    )


def allowed_files(setting: Setting) -> str:
    """The files `setting` may be set in, e.g. "user, app" (or "none")."""
    names = [layer.value for layer in _FILE_LAYERS if layer in setting.layers]
    return ", ".join(names) if names else "none"


class LiveSettings(Settings):
    """Settings over the bull defaults, the stack layers and the user, app and part files.

    Layer order (later wins): bull default → stack → user → app → part. The stack layer is the
    part's stack when the part file names one, else the app file's stack.
    """

    def __init__(
        self,
        *,
        user: LayerFile,
        app: LayerFile | None,
        parts: Mapping[str, LayerFile],
        parts_dir: Path | None,
        app_stack: StackLayer | None,
        part_stacks: Mapping[str, StackLayer],
    ) -> None:
        self._user = user
        self._app = app
        self._parts = dict(parts)
        self._parts_dir = parts_dir
        self._app_stack = app_stack
        self._part_stacks = dict(part_stacks)
        self._stack_schema = stack_schema([app_stack, *part_stacks.values()])

    # --- Settings -------------------------------------------------------------

    def schema(self) -> list[Setting]:
        return [*BULL_SCHEMA, *self._stack_schema.values()]

    def get(self, key: str, part: str | None = None) -> SettingValue:
        resolved = self._resolve(self._setting(key), part)
        if resolved is None:
            raise BullError(
                f"{key} has no value",
                fix=f"set it with `bull config set {key} <value>`",
            )
        return resolved.value

    def show(self, part: str | None = None) -> list[Resolved]:
        keys = {s.key for s in self.schema()}
        stack = self._stack_for(part)
        if stack is not None:
            keys.update(stack.values)
        for layer_file in self._files(part):
            keys.update(layer_file.values)
        found = (self._resolve(self._setting(key), part) for key in sorted(keys))
        return [resolved for resolved in found if resolved is not None]

    def set(
        self, key: str, raw: str, layer: Layer = Layer.APP, part: str | None = None
    ) -> Resolved:
        setting = self._setting(key)
        if layer not in _FILE_LAYERS:
            raise BullError(
                f"cannot set {key} in the {layer.value} layer",
                fix="set it in the user, app or part file",
            )
        if layer not in setting.layers:
            raise BullError(
                f"{key} can't be set in the {layer.value} file",
                fix=f"set it in one of: {allowed_files(setting)}",
            )
        value = parse_value(setting, raw)
        target = self._target(layer, part)
        text = _read_or_new(target.path)
        _write_atomic(target.path, set_key(text, key, value))
        target.values[key] = value
        return Resolved(key, value, layer, target.path)

    # --- helpers --------------------------------------------------------------

    def _setting(self, key: str) -> Setting:
        setting = find_setting(key) or self._stack_schema.get(key)
        if setting is None:
            raise unknown_setting(key)
        return setting

    def _stack_for(self, part: str | None) -> StackLayer | None:
        if part is not None and part in self._part_stacks:
            return self._part_stacks[part]
        return self._app_stack

    def _files(self, part: str | None) -> list[LayerFile]:
        files = [self._user]
        if self._app is not None:
            files.append(self._app)
        if part is not None and part in self._parts:
            files.append(self._parts[part])
        return files

    def _resolve(self, setting: Setting, part: str | None) -> Resolved | None:
        key = setting.key
        resolved: Resolved | None = None
        if setting.default is not None:
            # Bull's own keys have a bull default only when BULL is among their layers; a
            # stack-declared key's default is the stack's.
            if find_setting(key) is None:
                resolved = Resolved(key, setting.default, Layer.STACK, None)
            elif Layer.BULL in setting.layers:
                resolved = Resolved(key, setting.default, Layer.BULL, None)
        stack = self._stack_for(part)
        if stack is not None and key in stack.values:
            resolved = Resolved(key, stack.values[key], Layer.STACK, None)
        for layer_file in self._files(part):
            if key in layer_file.values:
                resolved = Resolved(
                    key, layer_file.values[key], layer_file.layer, layer_file.path
                )
        return resolved

    def _target(self, layer: Layer, part: str | None) -> LayerFile:
        if layer is Layer.USER:
            return self._user
        if layer is Layer.APP:
            if self._app is None:
                raise BullError(
                    "not in an app folder", fix="run this inside an app, or use --user"
                )
            return self._app
        if part is None:
            raise BullError(
                "setting a part's value needs a part", fix="pass --part <name>"
            )
        if self._parts_dir is None:
            raise BullError("not in an app folder", fix="run this inside an app")
        if part not in self._parts:
            self._parts[part] = LayerFile(Layer.PART, self._parts_dir / f"{part}.toml")
        return self._parts[part]


def stack_schema(stacks: list[StackLayer | None]) -> dict[str, Setting]:
    """The stacks' own settings by key (the first stack declaring a key wins); bull's keys
    are never overridden."""
    found: dict[str, Setting] = {}
    for stack in stacks:
        if stack is None:
            continue
        for setting in stack.schema:
            if find_setting(setting.key) is None and setting.key not in found:
                found[setting.key] = setting
    return found


def _read_or_new(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return _NEW_FILE_TEXT
    except (OSError, UnicodeDecodeError) as error:
        raise BullError(f"cannot read {path}: {error}") from error


def _write_atomic(path: Path, text: str) -> None:
    """Write `text` to `path` through a temp file in the same folder and a rename."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
            os.replace(temp_name, path)
        except BaseException:
            Path(temp_name).unlink(missing_ok=True)
            raise
    except OSError as error:
        raise BullError(f"cannot write {path}: {error.strerror or error}") from error
