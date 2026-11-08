"""Loads and validates the user, app and part settings files."""

from __future__ import annotations

import os
import re
import tomllib
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

from bull.Modules.foundation.Contracts import AppLayout, BullError
from bull.Modules.settings.Contracts import (
    ConfigError,
    ConfigProblem,
    Layer,
    Setting,
    SettingsLoader,
    SettingType,
    SettingValue,
    StackLayer,
)
from bull.Modules.settings.schema import find_setting, parse_value
from bull.Modules.settings.settings import (
    LayerFile,
    LiveSettings,
    allowed_files,
    stack_schema,
)
from bull.Modules.settings.toml_edit import find_line

_FORMAT = "format"
_STACK = "stack"
_DECODE_LINE = re.compile(r"line (\d+)")


@dataclass(frozen=True)
class _RawFile:
    layer: Layer
    path: Path
    text: str
    data: dict[str, object]


class LiveSettingsLoader(SettingsLoader):
    """Reads the settings files and checks them against bull's and the stacks' schemas.

    `user_file` is the user layer's file; None means `$XDG_CONFIG_HOME/bull/config.toml`
    (when that variable holds an absolute path), else `~/.config/bull/config.toml`.
    """

    def __init__(self, user_file: Path | None = None) -> None:
        self._user_file = user_file

    def load(
        self, app: AppLayout | None, stack_layer: Callable[[str], StackLayer]
    ) -> LiveSettings:
        """The layered settings of `app` (None: user file and bull defaults only).

        A stack layer is requested (once per name) for the stack named in the app file and in
        each part file.

        Raises:
            ConfigError: any problem in any file; `problems` lists every one of them.
        """
        problems: list[ConfigProblem] = []
        user_path = self._user_file or _default_user_file()
        user = _read(Layer.USER, user_path, problems)
        app_raw = _read(Layer.APP, app.config_file, problems) if app else None
        part_paths: list[Path] = []
        if app is not None and app.parts_dir.is_dir():
            part_paths = sorted(app.parts_dir.glob("*.toml"))
        parts_raw = {p.stem: (p, _read(Layer.PART, p, problems)) for p in part_paths}

        stacks = _StackRequests(stack_layer, problems)
        app_stack = stacks.named_in(app_raw)
        part_stacks: dict[str, StackLayer] = {}
        for name, (_, raw) in parts_raw.items():
            stack = stacks.named_in(raw)
            if stack is not None:
                part_stacks[name] = stack
        extra = stack_schema([app_stack, *part_stacks.values()])

        def lookup(key: str) -> Setting | None:
            return find_setting(key) or extra.get(key)

        user_file = _validate(user, user_path, Layer.USER, lookup, problems)
        app_file = (
            _validate(app_raw, app.config_file, Layer.APP, lookup, problems)
            if app is not None
            else None
        )
        part_files = {
            name: _validate(raw, path, Layer.PART, lookup, problems)
            for name, (path, raw) in parts_raw.items()
        }
        if problems:
            raise _config_error(problems)
        return LiveSettings(
            user=user_file,
            app=app_file,
            parts=part_files,
            parts_dir=app.parts_dir if app is not None else None,
            app_stack=_known_values(app_stack, lookup),
            part_stacks={
                name: known
                for name, stack in part_stacks.items()
                if (known := _known_values(stack, lookup)) is not None
            },
        )


def _default_user_file() -> Path:
    value = os.environ.get("XDG_CONFIG_HOME", "")
    base = (
        Path(value) if value and Path(value).is_absolute() else Path.home() / ".config"
    )
    return base / "bull" / "config.toml"


def _read(layer: Layer, path: Path, problems: list[ConfigProblem]) -> _RawFile | None:
    """The parsed file, or None when it doesn't exist or can't be parsed (a problem)."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as error:
        problems.append(ConfigProblem(path, 0, "", f"cannot read the file: {error}"))
        return None
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        match = _DECODE_LINE.search(str(error))
        line = int(match.group(1)) if match else 0
        problems.append(ConfigProblem(path, line, "", f"not valid TOML: {error}"))
        return None
    return _RawFile(layer, path, text, data)


class _StackRequests:
    """Asks `stack_layer` for each named stack once; its errors become problems."""

    def __init__(
        self, stack_layer: Callable[[str], StackLayer], problems: list[ConfigProblem]
    ) -> None:
        self._stack_layer = stack_layer
        self._problems = problems
        self._cache: dict[str, StackLayer | None] = {}

    def named_in(self, raw: _RawFile | None) -> StackLayer | None:
        if raw is None:
            return None
        name = raw.data.get(_STACK)
        if not isinstance(name, str):
            return None  # absent, or a wrong type the validation reports
        if name not in self._cache:
            try:
                self._cache[name] = self._stack_layer(name)
            except BullError as error:
                self._cache[name] = None
                line = find_line(raw.text, _STACK)
                self._problems.append(
                    ConfigProblem(raw.path, line, _STACK, error.message)
                )
        return self._cache[name]


def _flatten(
    table: Mapping[str, object], prefix: str, lookup: Callable[[str], Setting | None]
) -> Iterator[tuple[str, object]]:
    """Dotted keys and values; a table is descended into unless its key is a setting."""
    for name, value in table.items():
        key = prefix + name
        if isinstance(value, dict) and lookup(key) is None:
            yield from _flatten(value, key + ".", lookup)
        else:
            yield key, value


def _validate(
    raw: _RawFile | None,
    path: Path,
    layer: Layer,
    lookup: Callable[[str], Setting | None],
    problems: list[ConfigProblem],
) -> LayerFile:
    """The file's valid values; each invalid key adds a problem."""
    result = LayerFile(layer, path)
    if raw is None:
        return result
    if layer is not Layer.USER and _FORMAT not in raw.data:
        problems.append(
            ConfigProblem(path, 0, _FORMAT, "missing `format` (add `format = 1`)")
        )
    for key, value in _flatten(raw.data, "", lookup):
        if key == _FORMAT:
            continue  # checked by the formats module, not a setting
        setting = lookup(key)
        line = find_line(raw.text, key)
        if setting is None:
            problems.append(ConfigProblem(path, line, key, f"unknown setting `{key}`"))
            continue
        if layer not in setting.layers:
            message = (
                f"{key} can't be set in the {layer.value} file "
                f"(allowed in: {allowed_files(setting)})"
            )
            problems.append(ConfigProblem(path, line, key, message))
            continue
        try:
            result.values[key] = _checked(setting, value)
        except BullError as error:
            problems.append(ConfigProblem(path, line, key, error.message))
    return result


def _checked(setting: Setting, value: object) -> SettingValue:
    """`value` (as read from TOML) when it fits `setting`.

    Raises:
        BullError: the value has the wrong type or is out of range; the message says what
            the setting expects.
    """
    key = setting.key
    if setting.type is SettingType.INT:
        # parse_value owns the integer range message; "" never parses as an integer.
        text = (
            str(value) if isinstance(value, int) and not isinstance(value, bool) else ""
        )
        return parse_value(setting, text)
    if setting.type is SettingType.BOOL:
        if isinstance(value, bool):
            return value
        raise BullError(f"{key} must be true or false")
    if setting.type is SettingType.CHOICE:
        if isinstance(value, str) and value in setting.choices:
            return value
        raise BullError(f"{key} must be one of: {', '.join(setting.choices)}")
    if setting.type is SettingType.STR_LIST:
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return tuple(value)
        raise BullError(f"{key} must be a list of strings")
    if isinstance(value, str):
        return value
    raise BullError(f"{key} must be a string")


def _known_values(
    stack: StackLayer | None, lookup: Callable[[str], Setting | None]
) -> StackLayer | None:
    """`stack` keeping only the values of keys a schema knows."""
    if stack is None:
        return None
    values = {key: value for key, value in stack.values.items() if lookup(key)}
    return StackLayer(schema=stack.schema, values=values)


def _config_error(problems: list[ConfigProblem]) -> ConfigError:
    lines = [f"{p.file}:{p.line}: {p.key or '(file)'}: {p.message}" for p in problems]
    count = len(problems)
    noun = "problem" if count == 1 else "problems"
    error = ConfigError(
        f"{count} {noun} in the settings files:\n" + "\n".join(lines),
        fix="fix the settings files listed, then try again",
    )
    error.problems = list(problems)
    return error
