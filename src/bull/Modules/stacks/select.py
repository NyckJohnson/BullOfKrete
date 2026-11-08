"""The per-app stack operations: select, rules, setup guide, check and run."""

from __future__ import annotations

import json
import os
import re
import stat
import sys
import tempfile
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from bull.Modules.foundation.Contracts import AppLayout, FileFormatError, Runner
from bull.Modules.settings.Contracts import Settings, SettingValue
from bull.Modules.stacks import docs
from bull.Modules.stacks.Contracts import (
    CheckItem,
    Stack,
    StackError,
    StackOps,
    StackRegistry,
)

_ONE_PART = "app"
_FOLDER_KEYS = ("source_dir", "test_dir")


@dataclass(frozen=True)
class _Part:
    """Where one part of the app lives and what it is built with."""

    name: str
    settings_part: str | None
    root: Path
    results: Path
    stack: Stack


class LiveStackOps(StackOps):
    """Stack operations on a real app folder.

    `settings` is the app's loaded settings (used by `check` and `run_command`); `runner` runs
    commands and looks up tools; `python` is what `{python}` expands to.
    """

    def __init__(
        self,
        registry: StackRegistry,
        settings: Settings,
        runner: Runner,
        python: str = sys.executable,
    ) -> None:
        self._registry = registry
        self._settings = settings
        self._runner = runner
        self._python = python

    # ------------------------------------------------------------- select

    def select(self, app: AppLayout, name: str) -> None:
        """Set the one-part app's stack: config keys, `.gitignore` lines, scaffold folders.

        Raises StackError for an app with parts or an unknown stack, before writing anything.
        """
        if part_names(app):
            raise StackError(
                "this app has parts; its stacks are set per part",
                "use `bull part add <name> <stack>` to add a part with a stack",
            )
        stack = self._registry.get(name)
        values: dict[str, str] = {"stack": stack.manifest.name}
        for key in _FOLDER_KEYS:
            values[key] = _stack_default(stack, key)

        config = _config_with(app.config_file, values)
        gitignore_path = app.root / ".gitignore"
        gitignore = _gitignore_with(gitignore_path, stack.manifest.gitignore)

        # Config last: if a folder or `.gitignore` cannot be written, the stack stays unset.
        for folder in stack.manifest.scaffold:
            (app.root / folder).mkdir(parents=True, exist_ok=True)
        if gitignore is not None:
            _write_atomic(gitignore_path, gitignore)
        if config is not None:
            _write_atomic(app.config_file, config)

    # ------------------------------------------------------ rules, setup

    def rules(self, stack: Stack, agent: str) -> str:
        return docs.rules(stack, agent)

    def setup_guide(self, stack: Stack, section: str | None = None) -> str:
        return docs.setup_guide(stack, section)

    # -------------------------------------------------------------- check

    def check(self, app: AppLayout, part: str | None = None) -> list[CheckItem]:
        """The stack's own check items for the part, then bull's: required tools and folders."""
        where = self._part(app, part)
        values = self._values(where)
        items = list(where.stack.readers.check(where.root, values, _adopting(app)))
        for need in where.stack.manifest.requires:
            found = self._runner.which(need.tool) is not None
            items.append(
                CheckItem(
                    found,
                    f"{need.tool} on PATH",
                    "" if found else f"install {need.tool}: {need.hint}",
                )
            )
        for key, label in (("source_dir", "source"), ("test_dir", "test")):
            folder = values.get(key)
            if not isinstance(folder, str):
                items.append(
                    CheckItem(
                        False, f"{label} folder set", f"set `{key}` in the config"
                    )
                )
                continue
            exists = (where.root / folder).is_dir()
            items.append(
                CheckItem(
                    exists,
                    f"{label} folder {folder} exists",
                    "" if exists else f"create {where.root / folder}",
                )
            )
        return items

    # -------------------------------------------------------- run_command

    def run_command(self, app: AppLayout, command: str, part: str | None = None) -> int:
        """Run the stack's `[commands]` entry `command` like a gate step; its exit code.

        The command's captured stdout and stderr are written to this process's stdout and stderr.
        """
        where = self._part(app, part)
        commands = where.stack.manifest.commands
        if command not in commands:
            known = ", ".join(sorted(commands))
            raise StackError(
                f"stack `{where.stack.manifest.name}` has no command `{command}`",
                f"commands: {known}" if known else "this stack defines no commands",
            )
        values = self._values(where)
        adopting = _adopting(app)
        fills = {
            "{python}": self._python,
            "{stack_dir}": str(where.stack.home),
            "{app_root}": str(app.root),
            "{part_root}": str(where.root),
            "{results}": str(where.results),
            "{module}": "",
            "{module_src}": "",
            "{module_tests}": "",
            "{port}": "",
        }
        argv = tuple(
            _fill(arg, fills) for arg in commands[command] if arg != "{failed_ids}"
        )
        env = {
            "BULL_PART": where.name,
            "BULL_PART_ROOT": str(where.root),
            "BULL_APP_ROOT": str(app.root),
            "BULL_RESULTS": str(where.results),
            "BULL_STACK_DIR": str(where.stack.home),
            "BULL_ADOPT_MODE": "1" if adopting else "0",
            "BULL_SCOPE_MODULE": "",
            "BULL_SETTINGS": json.dumps(_jsonable(values), sort_keys=True),
        }
        result = self._runner.run(argv, where.root, env, None)
        if result.stdout:
            sys.stdout.write(result.stdout)
            sys.stdout.flush()
        if result.stderr:
            sys.stderr.write(result.stderr)
            sys.stderr.flush()
        return result.returncode

    # ------------------------------------------------------------ helpers

    def _part(self, app: AppLayout, part: str | None) -> _Part:
        """The part's folder, results folder and stack.

        With no part files, the app is the implicit part `app` (`None` or `"app"`): the app root
        and the app-layer settings. With part files, `part` must name one of them.
        """
        names = part_names(app)
        if not names:
            if part is not None and part != _ONE_PART:
                raise StackError(
                    f"unknown part `{part}`",
                    "this app has no parts; leave out the part, or add one with `bull part add`",
                )
            root = app.root
            name, settings_part = _ONE_PART, None
        else:
            if part is None:
                raise StackError(
                    "this app has parts; say which part: " + ", ".join(names),
                    "pass `--part <name>`",
                )
            if part not in names:
                raise StackError(
                    f"unknown part `{part}`",
                    "parts: " + ", ".join(names),
                )
            folder = self._settings.get("dir", part)
            if not isinstance(folder, str):
                raise StackError(f"part `{part}` has no folder (`dir`)")
            root = app.root / folder
            name, settings_part = part, part
        stack_name = self._settings.get("stack", settings_part)
        if not isinstance(stack_name, str) or not stack_name:
            raise StackError(
                f"no stack set for part `{name}`", "run `bull stack select <name>`"
            )
        return _Part(
            name=name,
            settings_part=settings_part,
            root=root,
            results=app.results_dir / name,
            stack=self._registry.get(stack_name),
        )

    def _values(self, where: _Part) -> dict[str, SettingValue]:
        return {r.key: r.value for r in self._settings.show(where.settings_part)}


def part_names(app: AppLayout) -> list[str]:
    """The sorted names of the app's parts (`.bull/parts/*.toml`); empty for a one-part app."""
    if not app.parts_dir.is_dir():
        return []
    return sorted(p.stem for p in app.parts_dir.glob("*.toml") if p.is_file())


def _stack_default(stack: Stack, key: str) -> str:
    layer = stack.manifest.settings
    value: object = layer.values.get(key)
    if value is None:
        value = next((s.default for s in layer.schema if s.key == key), None)
    if not isinstance(value, str):
        raise StackError(
            f"stack `{stack.manifest.name}` has no default for `{key}`",
            f"give `[settings.{key}]` a default in {stack.home / 'stack.toml'}",
        )
    return value


def _adopting(app: AppLayout) -> bool:
    """True while `status.json` records an active adoption."""
    try:
        text = app.status_file.read_text(encoding="utf-8")
    except FileNotFoundError:
        return False
    except (OSError, UnicodeDecodeError) as e:
        raise FileFormatError(f"{app.status_file}: cannot read: {e}") from e
    try:
        data: object = json.loads(text)
    except json.JSONDecodeError as e:
        raise FileFormatError(
            f"{app.status_file}: invalid JSON at line {e.lineno}: {e.msg}"
        ) from e
    return isinstance(data, dict) and data.get("adoption") is not None


def _fill(arg: str, fills: Mapping[str, str]) -> str:
    for placeholder, value in fills.items():
        arg = arg.replace(placeholder, value)
    return arg


def _jsonable(values: Mapping[str, SettingValue]) -> dict[str, object]:
    return {k: list(v) if isinstance(v, tuple) else v for k, v in values.items()}


def _toml_line(key: str, value: str) -> str:
    # A JSON string is a valid TOML basic string.
    return f"{key} = {json.dumps(value)}\n"


def _config_with(path: Path, values: Mapping[str, str]) -> str | None:
    """The config text with top-level `values` set, or None when nothing changes.

    Existing lines and comments are kept; a key already set at top level is replaced in place,
    a new one goes at the end of the top-level block (before the first table).
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        text = "format = 1\n"
    except (OSError, UnicodeDecodeError) as e:
        raise FileFormatError(f"{path}: cannot read: {e}") from e
    try:
        tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise FileFormatError(f"{path}: invalid TOML: {e}", f"fix {path}") from e

    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    top = next(
        (i for i, ln in enumerate(lines) if ln.lstrip().startswith("[")), len(lines)
    )
    # New keys go after the last top-level entry: above any comment block directly over the
    # first table (it belongs to that table) and above the blank lines before it.
    insert = top
    while insert > 0 and lines[insert - 1].lstrip().startswith("#"):
        insert -= 1
    while insert > 0 and not lines[insert - 1].strip():
        insert -= 1
    for key, value in values.items():
        wanted = _toml_line(key, value)
        pattern = re.compile(rf"^\s*{re.escape(key)}\s*=")
        at = next((i for i in range(top) if pattern.match(lines[i])), None)
        if at is not None:
            lines[at] = wanted
        else:
            lines.insert(insert, wanted)
            insert += 1
            top += 1
    updated = "".join(lines)
    try:
        data = tomllib.loads(updated)
    except tomllib.TOMLDecodeError as e:
        raise StackError(
            f"cannot update {path}: {e}", f"set the keys by hand: {dict(values)}"
        ) from e
    if any(data.get(k) != v for k, v in values.items()):
        raise StackError(
            f"cannot update {path}: a key is set in a form bull cannot edit",
            f"set the keys by hand: {dict(values)}",
        )
    return None if updated == text else updated


def _gitignore_with(path: Path, wanted: tuple[str, ...]) -> str | None:
    """`.gitignore` text with the missing `wanted` lines appended, or None when none are missing."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        text = ""
    except (OSError, UnicodeDecodeError) as e:
        raise FileFormatError(f"{path}: cannot read: {e}") from e
    have = {ln.strip() for ln in text.splitlines()}
    missing: list[str] = []
    for line in wanted:
        if line.strip() not in have and line not in missing:
            missing.append(line)
    if not missing:
        return None
    if text and not text.endswith("\n"):
        text += "\n"
    return text + "".join(f"{line}\n" for line in missing)


def _write_atomic(path: Path, text: str) -> None:
    """Write `text` to `path` through a temporary file and a rename.

    The file keeps its permission mode; a new file gets `0o666` less the umask, as `open` would.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except FileNotFoundError:
        mode = 0o666 & ~_umask()
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            os.fchmod(handle.fileno(), mode)
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def _umask() -> int:
    """The process umask (read by setting it and putting it back)."""
    current = os.umask(0o022)
    os.umask(current)
    return current
