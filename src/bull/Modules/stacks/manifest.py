"""Parses and validates a stack folder's `stack.toml`.

`parse_manifest` collects every problem it finds and raises one `StackError` listing them all,
so a stack author sees the whole list at once. The `detect` → `surveyor` agent rule needs the
stack's readers and is checked when the stack is loaded (see `registry.py`).
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import TypeVar

from bull.Modules.settings.Contracts import (
    Layer,
    Setting,
    SettingType,
    SettingValue,
    StackLayer,
)
from bull.Modules.stacks.Contracts import (
    GateCommands,
    Maturity,
    Requirement,
    RunCommands,
    StackError,
    StackKind,
    StackManifest,
)

MANIFEST_FILE = "stack.toml"
FORMAT_VERSION = 1

# Agents every stack must list, and the ones a feature of the stack makes required.
BASE_AGENTS = (
    "skeleton-builder",
    "test-writer",
    "code-writer",
    "reviewer",
    "coverage-analyst",
)
JOURNEY_AGENT = "journey-test-writer"
SURVEYOR_AGENT = "surveyor"

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_TEMPLATE_NAME = "_template"
_PLACEHOLDER = "TODO"
# The placeholder counts only as a whole, case-sensitive word ("TODOLIST" is fine).
_PLACEHOLDER_RE = re.compile(r"\bTODO\b")
_REQUIRED_SETTINGS = ("source_dir", "test_dir")
_GATE_KEYS = (
    "preflight",
    "setup",
    "build_test",
    "build_test_fast",
    "lint",
    "rerun_failed",
)
_RUN_KEYS = ("start", "ready", "stop")
_DEFAULT_READY_TIMEOUT = 30.0
_STACK_SETTING_LAYERS = frozenset({Layer.STACK, Layer.APP, Layer.PART})
_E = TypeVar("_E", StackKind, Maturity)
_FIX = "Edit the stack's stack.toml (see the stack-author guide) and try again."


def parse_manifest(folder: Path) -> StackManifest:
    """Read and validate `folder/stack.toml`.

    Raises `StackError` if the file is missing or unreadable, or listing every problem found.
    """
    path = folder / MANIFEST_FILE
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError:
        raise StackError(f"{folder} has no {MANIFEST_FILE}.", _FIX) from None
    except OSError as error:
        raise StackError(f"Cannot read {path}: {error}", _FIX) from error
    except tomllib.TOMLDecodeError as error:
        raise StackError(f"{path} is not valid TOML: {error}", _FIX) from error
    except UnicodeDecodeError as error:
        raise StackError(f"{path} is not valid UTF-8: {error}", _FIX) from error

    parser = _Parser(folder)
    manifest = parser.parse(data)
    if parser.problems or manifest is None:
        lines = "\n".join(f"- {p}" for p in parser.problems)
        raise StackError(f"{path} has problems:\n{lines}", _FIX)
    return manifest


class _Parser:
    """Turns the decoded TOML into a `StackManifest`, recording problems instead of stopping."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.problems: list[str] = []

    def problem(self, text: str) -> None:
        self.problems.append(text)

    # -- entry -------------------------------------------------------------------------------

    def parse(self, data: Mapping[str, object]) -> StackManifest | None:
        self._check_placeholders(data, "")
        fmt = data.get("format")
        if fmt is None:
            self.problem("format: missing (expected format = 1)")
        elif fmt != FORMAT_VERSION or isinstance(fmt, bool):
            self.problem(
                f"format: unsupported version {fmt!r} (expected {FORMAT_VERSION})"
            )

        stack = self._table(data, "stack", required=True)
        name = self._name(stack)
        title = self._str(stack, "stack.", "title")
        description = self._str(stack, "stack.", "description")
        language = self._str(stack, "stack.", "language")
        kind = self._enum(stack, "kind", StackKind)
        maturity = self._enum(stack, "maturity", Maturity)
        source_glob = self._str(stack, "stack.", "source_glob")
        test_glob = self._argv(stack, "stack.", "test_glob", required=True)
        comment = self._str(stack, "stack.", "comment")
        scaffold = self._argv(stack, "stack.", "scaffold", required=False) or ()
        gitignore = self._argv(stack, "stack.", "gitignore", required=False) or ()
        agents = self._argv(stack, "stack.", "agents", required=True)
        requires = self._requires(stack)
        settings = self._settings(data)
        gates = self._gates(data)
        run = self._run(data)
        interface_formats = self._interfaces(data)
        commands = self._commands(data)

        if agents is not None:
            needed = list(BASE_AGENTS)
            if gates is not None and gates.journeys is not None:
                needed.append(JOURNEY_AGENT)
            for agent in needed:
                if agent not in agents:
                    reason = (
                        " (needed because [gates] sets journeys)"
                        if agent == JOURNEY_AGENT
                        else ""
                    )
                    self.problem(
                        f"stack.agents: missing required agent {agent!r}{reason}"
                    )

        if (
            name is None
            or title is None
            or description is None
            or language is None
            or kind is None
            or maturity is None
            or source_glob is None
            or test_glob is None
            or comment is None
            or agents is None
            or requires is None
            or settings is None
            or gates is None
            or self.problems
        ):
            return None
        return StackManifest(
            name=name,
            title=title,
            description=description,
            language=language,
            kind=kind,
            maturity=maturity,
            source_glob=source_glob,
            test_glob=test_glob,
            comment=comment,
            scaffold=scaffold,
            gitignore=gitignore,
            agents=agents,
            requires=requires,
            settings=settings,
            gates=gates,
            run=run,
            interface_formats=interface_formats,
            commands=commands,
        )

    # -- generic readers ---------------------------------------------------------------------

    def _check_placeholders(self, value: object, where: str) -> None:
        """Report every string value that still holds the template's `TODO` placeholder."""
        if isinstance(value, str):
            if _PLACEHOLDER_RE.search(value):
                self.problem(
                    f"{where or 'value'}: placeholder {_PLACEHOLDER!r} left in {value!r}"
                )
        elif isinstance(value, Mapping):
            for key, item in value.items():
                self._check_placeholders(item, f"{where}.{key}" if where else str(key))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                self._check_placeholders(item, f"{where}[{index}]")

    def _table(
        self, data: Mapping[str, object], key: str, *, required: bool
    ) -> Mapping[str, object] | None:
        value = data.get(key)
        if value is None:
            if required:
                self.problem(f"[{key}]: missing section")
            return None
        if not isinstance(value, Mapping):
            self.problem(f"[{key}]: must be a table")
            return None
        return value

    def _str(
        self, table: Mapping[str, object] | None, prefix: str, key: str
    ) -> str | None:
        if table is None:
            return None
        value = table.get(key)
        if value is None:
            self.problem(f"{prefix}{key}: missing required key")
            return None
        if not isinstance(value, str):
            self.problem(f"{prefix}{key}: must be a string")
            return None
        return value

    def _argv(
        self,
        table: Mapping[str, object] | None,
        prefix: str,
        key: str,
        *,
        required: bool,
    ) -> tuple[str, ...] | None:
        if table is None:
            return None
        value = table.get(key)
        if value is None:
            if required:
                self.problem(f"{prefix}{key}: missing required key")
            return None
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            self.problem(f"{prefix}{key}: must be a list of strings")
            return None
        return tuple(str(v) for v in value)

    def _enum(
        self, table: Mapping[str, object] | None, key: str, enum: type[_E]
    ) -> _E | None:
        raw = self._str(table, "stack.", key)
        if raw is None:
            return None
        try:
            return enum(raw)
        except ValueError:
            allowed = " | ".join(member.value for member in enum)
            self.problem(f"stack.{key}: {raw!r} is not one of {allowed}")
            return None

    # -- sections ----------------------------------------------------------------------------

    def _name(self, stack: Mapping[str, object] | None) -> str | None:
        name = self._str(stack, "stack.", "name")
        if name is None:
            return None
        bad = False
        if name == _TEMPLATE_NAME:
            self.problem(
                f"stack.name: {_TEMPLATE_NAME!r} is the template, not a stack; rename it"
            )
            bad = True
        elif not _NAME_RE.match(name):
            self.problem(
                f"stack.name: {name!r} is not a valid name "
                "(lowercase letter, then lowercase letters, digits or _)"
            )
            bad = True
        if name != self.folder.name:
            self.problem(
                f"stack.name: {name!r} does not match the folder name {self.folder.name!r}"
            )
            bad = True
        return None if bad else name

    def _requires(
        self, stack: Mapping[str, object] | None
    ) -> tuple[Requirement, ...] | None:
        if stack is None:
            return None
        raw = stack.get("requires", [])
        if not isinstance(raw, list):
            self.problem(
                "stack.requires: must be an array of tables ([[stack.requires]])"
            )
            return None
        result: list[Requirement] = []
        ok = True
        for index, entry in enumerate(raw):
            where = f"stack.requires[{index}]."
            if not isinstance(entry, Mapping):
                self.problem(
                    f"stack.requires[{index}]: must be a table with tool and hint"
                )
                ok = False
                continue
            tool = self._str(entry, where, "tool")
            hint = self._str(entry, where, "hint")
            if tool is None or hint is None:
                ok = False
                continue
            result.append(Requirement(tool=tool, hint=hint))
        return tuple(result) if ok else None

    def _settings(self, data: Mapping[str, object]) -> StackLayer | None:
        table = self._table(data, "settings", required=False) or {}
        schema: list[Setting] = []
        values: dict[str, SettingValue] = {}
        ok = True
        for key, entry in table.items():
            if not isinstance(entry, Mapping):
                self.problem(f"settings.{key}: must be a table ([settings.{key}])")
                ok = False
                continue
            valid, setting = self._setting(key, entry)
            if not valid:
                ok = False
                continue
            if setting is not None:
                schema.append(setting)
            if "default" in entry:
                default = _setting_value(entry["default"])
                if default is None:
                    self.problem(f"settings.{key}.default: unsupported value type")
                    ok = False
                    continue
                values[key] = default
        declared = {s.key for s in schema}
        for key in _REQUIRED_SETTINGS:
            if key not in declared:
                self.problem(
                    f"settings.{key}: missing required setting [settings.{key}]"
                )
                ok = False
        if not ok:
            return None
        return StackLayer(schema=tuple(schema), values=values)

    def _setting(
        self, key: str, entry: Mapping[str, object]
    ) -> tuple[bool, Setting | None]:
        """(valid, setting): the stack's own setting, or None for a bare default of a bull key."""
        raw_type = entry.get("type")
        if raw_type is None:
            if "default" not in entry:
                self.problem(f"settings.{key}: needs a type (own setting) or a default")
                return False, None
            return True, None
        if not isinstance(raw_type, str):
            self.problem(f"settings.{key}.type: must be a string")
            return False, None
        try:
            setting_type = SettingType(raw_type)
        except ValueError:
            allowed = " | ".join(t.value for t in SettingType)
            self.problem(f"settings.{key}.type: {raw_type!r} is not one of {allowed}")
            return False, None
        description = entry.get("description", "")
        if not isinstance(description, str):
            self.problem(f"settings.{key}.description: must be a string")
            return False, None
        choices_raw = entry.get("choices", [])
        if not isinstance(choices_raw, list) or not all(
            isinstance(c, str) for c in choices_raw
        ):
            self.problem(f"settings.{key}.choices: must be a list of strings")
            return False, None
        choices = tuple(str(c) for c in choices_raw)
        if setting_type is SettingType.CHOICE and not choices:
            self.problem(f"settings.{key}.choices: a choice setting needs choices")
            return False, None
        bounds: list[int | None] = []
        for bound in ("minimum", "maximum"):
            value = entry.get(bound)
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool)
            ):
                self.problem(f"settings.{key}.{bound}: must be an integer")
                return False, None
            bounds.append(value if isinstance(value, int) else None)
        default = _setting_value(entry["default"]) if "default" in entry else None
        if "default" in entry and not _fits(setting_type, default, choices):
            self.problem(f"settings.{key}.default: does not match type {raw_type!r}")
            return False, None
        return True, Setting(
            key=key,
            type=setting_type,
            default=default,
            description=description,
            choices=choices,
            minimum=bounds[0],
            maximum=bounds[1],
            layers=_STACK_SETTING_LAYERS,
        )

    def _gates(self, data: Mapping[str, object]) -> GateCommands | None:
        table = self._table(data, "gates", required=True)
        if table is None:
            return None
        found = {
            key: self._argv(table, "gates.", key, required=True) for key in _GATE_KEYS
        }
        journeys = self._argv(table, "gates.", "journeys", required=False)
        if "journeys" in table and journeys is None:
            return None
        preflight = found["preflight"]
        setup = found["setup"]
        build_test = found["build_test"]
        build_test_fast = found["build_test_fast"]
        lint = found["lint"]
        rerun_failed = found["rerun_failed"]
        if (
            preflight is None
            or setup is None
            or build_test is None
            or build_test_fast is None
            or lint is None
            or rerun_failed is None
        ):
            return None
        return GateCommands(
            preflight=preflight,
            setup=setup,
            build_test=build_test,
            build_test_fast=build_test_fast,
            lint=lint,
            rerun_failed=rerun_failed,
            journeys=journeys,
        )

    def _run(self, data: Mapping[str, object]) -> RunCommands | None:
        table = self._table(data, "run", required=False)
        if table is None:
            return None
        start, ready, stop = (
            self._argv(table, "run.", key, required=True) for key in _RUN_KEYS
        )
        timeout_raw = table.get("ready_timeout", _DEFAULT_READY_TIMEOUT)
        timeout: float | None = None
        if (
            isinstance(timeout_raw, (int, float))
            and not isinstance(timeout_raw, bool)
            and timeout_raw > 0
        ):
            timeout = float(timeout_raw)
        else:
            self.problem("run.ready_timeout: must be a positive number of seconds")
        if start is None or ready is None or stop is None or timeout is None:
            return None
        return RunCommands(start=start, ready=ready, stop=stop, ready_timeout=timeout)

    def _interfaces(self, data: Mapping[str, object]) -> tuple[str, ...]:
        table = self._table(data, "interfaces", required=False)
        return self._argv(table, "interfaces.", "formats", required=False) or ()

    def _commands(self, data: Mapping[str, object]) -> Mapping[str, tuple[str, ...]]:
        table = self._table(data, "commands", required=False)
        if table is None:
            return {}
        commands: dict[str, tuple[str, ...]] = {}
        for key in table:
            argv = self._argv(table, "commands.", key, required=True)
            if argv is not None:
                commands[key] = argv
        return commands


def _setting_value(raw: object) -> SettingValue | None:
    """A TOML value as a `SettingValue` (lists become tuples); None if the type is unsupported."""
    if isinstance(raw, (bool, int, str)):
        return raw
    if isinstance(raw, list) and all(isinstance(v, str) for v in raw):
        return tuple(str(v) for v in raw)
    return None


def _fits(
    setting_type: SettingType, value: SettingValue | None, choices: tuple[str, ...]
) -> bool:
    if setting_type is SettingType.BOOL:
        return isinstance(value, bool)
    if setting_type is SettingType.INT:
        return isinstance(value, int) and not isinstance(value, bool)
    if setting_type is SettingType.STR:
        return isinstance(value, str)
    if setting_type is SettingType.CHOICE:
        return isinstance(value, str) and value in choices
    return isinstance(value, tuple)
