"""An app's parts, the implicit one-part case and part checks."""

from __future__ import annotations

import json
import os
import posixpath
import re
import tempfile
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from bull.Modules.foundation.Contracts import AppLayout, BullError
from bull.Modules.parts.Contracts import Part, Parts
from bull.Modules.settings.Contracts import SettingsLoader, StackLayer
from bull.Modules.stacks.Contracts import Stack, StackError, StackRegistry

_IMPLICIT = "app"
_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")
_FORMAT = 1


@dataclass(frozen=True)
class _Entry:
    """A part as written on disk: name, stack and folder, before settings resolve."""

    name: str
    stack: str
    dir: str
    implicit: bool


class LiveParts(Parts):
    """Parts read from `.bull/parts/*.toml`, or the implicit part `app` in `config.toml`.

    Folders inside each part come from settings (`source_dir`, `test_dir` for that part);
    stacks come from the registry.
    """

    def __init__(self, registry: StackRegistry, loader: SettingsLoader) -> None:
        self._registry = registry
        self._loader = loader

    # ----------------------------------------------------------------- reading

    def all(self, app: AppLayout) -> list[Part]:
        entries = self._entries(app)
        if not entries:
            return []
        settings = self._loader.load(app, self._stack_layer)
        parts: list[Part] = []
        for entry in entries:
            key = None if entry.implicit else entry.name
            parts.append(
                Part(
                    name=entry.name,
                    stack=entry.stack,
                    dir=entry.dir,
                    root=_root(app, entry.dir),
                    source_dir=Path(str(settings.get("source_dir", key))),
                    test_dir=Path(str(settings.get("test_dir", key))),
                )
            )
        return parts

    def get(self, app: AppLayout, name: str | None = None) -> Part:
        parts = self.all(app)
        if name is None:
            if not parts:
                raise BullError(
                    "this app has no parts", "select a stack or run `bull part add`"
                )
            if len(parts) > 1:
                names = ", ".join(p.name for p in parts)
                raise BullError(f"say which part: {names}", "pass --part <name>")
            return parts[0]
        for part in parts:
            if part.name == name:
                return part
        known = ", ".join(p.name for p in parts) or "none"
        raise BullError(f"no part named `{name}`; parts: {known}")

    # ------------------------------------------------------------------ adding

    def add(
        self, app: AppLayout, name: str, stack: str, dir: str | None = None
    ) -> Part:
        # Every check runs before the first write, so a refusal leaves the app untouched.
        if not _NAME.match(name):
            raise BullError(
                f"bad part name `{name}`",
                "use lowercase letters, digits and `_`, starting with a letter",
            )
        found = self._registry.get(stack)  # raises StackError for an unknown stack
        folder = _clean_dir(dir if dir is not None else name)
        existing = self.all(app)
        if any(p.name == name for p in existing):
            raise BullError(f"a part named `{name}` already exists")
        values = found.manifest.settings.values
        new_folders = (
            _rel(str(values.get("source_dir", "."))),
            _rel(str(values.get("test_dir", "."))),
        )
        for other in existing:
            if _overlap(
                PurePosixPath(folder),
                new_folders,
                PurePosixPath(_clean_dir(other.dir)),
                (_rel(str(other.source_dir)), _rel(str(other.test_dir))),
            ):
                raise BullError(
                    f"folder `{folder}` overlaps part `{other.name}` (`{other.dir}`)",
                    "choose a folder outside the other parts with --dir",
                )

        writes: list[tuple[Path, str]] = []
        implicit = self._implicit_entry(app)
        if implicit is not None and not _part_files(app):
            writes.extend(self._move_implicit(app, implicit.stack))
        writes.append(
            (
                app.parts_dir / f"{name}.toml",
                _part_toml(stack, folder, _own_values(found.manifest.settings)),
            )
        )
        gitignore = _gitignore_write(app, folder, found.manifest.gitignore)
        if gitignore is not None:
            writes.append(gitignore)

        for path, text in writes:
            _write_atomic(path, text)
        root = _root(app, folder)
        root.mkdir(parents=True, exist_ok=True)
        for sub in found.manifest.scaffold:
            (root / sub).mkdir(parents=True, exist_ok=True)
        return self.get(app, name)

    # ---------------------------------------------------------------- checking

    def check(self, app: AppLayout) -> list[str]:
        entries = self._entries(app)
        problems: list[str] = []
        known: dict[str, Stack] = {}
        for entry in entries:
            found = self._stack_or_none(entry.stack)
            if found is None:
                problems.append(f"part `{entry.name}`: unknown stack `{entry.stack}`")
            else:
                known[entry.name] = found
        folders = self._inner_folders(app, entries, known)
        for i, first in enumerate(entries):
            for second in entries[i + 1 :]:
                if _overlap(
                    PurePosixPath(_clean_dir(first.dir)),
                    folders.get(first.name, ()),
                    PurePosixPath(_clean_dir(second.dir)),
                    folders.get(second.name, ()),
                ):
                    problems.append(
                        f"parts `{first.name}` (`{first.dir}`) and "
                        f"`{second.name}` (`{second.dir}`) overlap"
                    )
        for entry in entries:
            if not _root(app, entry.dir).is_dir():
                problems.append(f"part `{entry.name}`: folder `{entry.dir}` is missing")
        return problems

    # ------------------------------------------------------------------- paths

    def module_src(self, part: Part, module: str) -> Path:
        return part.root / part.source_dir / "Modules" / module

    def module_tests(self, part: Part, module: str) -> Path:
        return part.root / part.test_dir / module

    def is_test_path(self, app: AppLayout, path: Path) -> bool:
        target = path if path.is_absolute() else app.root / path
        for part in self.all(app):
            if target.is_relative_to(part.root / part.test_dir):
                return True
            found = self._stack_or_none(part.stack)
            if found is not None and any(
                target.match(glob) for glob in found.manifest.test_glob
            ):
                return True
        return False

    # --------------------------------------------------------------- internals

    def _stack_or_none(self, name: str) -> Stack | None:
        """The stack, or None when unknown: `check` reports unknown stacks itself."""
        try:
            return self._registry.get(name)
        except StackError:
            return None

    def _stack_layer(self, name: str) -> StackLayer:
        """Settings layer for a stack; an unknown stack contributes nothing."""
        found = self._stack_or_none(name)
        if found is None:
            return StackLayer(schema=(), values={})
        return found.manifest.settings

    def _entries(self, app: AppLayout) -> list[_Entry]:
        files = _part_files(app)
        if files:
            return [_read_part_file(path) for path in files]
        implicit = self._implicit_entry(app)
        return [implicit] if implicit is not None else []

    def _implicit_entry(self, app: AppLayout) -> _Entry | None:
        config = _read_toml(app.config_file)
        stack = config.get("stack") if config is not None else None
        if stack is None:
            return None
        if not isinstance(stack, str):
            raise BullError(f"{app.config_file}: `stack` must be a string")
        return _Entry(_IMPLICIT, stack, ".", implicit=True)

    def _inner_folders(
        self, app: AppLayout, entries: Sequence[_Entry], known: Mapping[str, Stack]
    ) -> dict[str, tuple[PurePosixPath, ...]]:
        """Source and test folders of root parts with a known stack (all overlap needs)."""
        roots = [e for e in entries if _clean_dir(e.dir) == "." and e.name in known]
        if not roots:
            return {}
        settings = self._loader.load(app, self._stack_layer)
        folders: dict[str, tuple[PurePosixPath, ...]] = {}
        for entry in roots:
            key = None if entry.implicit else entry.name
            folders[entry.name] = (
                _rel(str(settings.get("source_dir", key))),
                _rel(str(settings.get("test_dir", key))),
            )
        return folders

    def _move_implicit(self, app: AppLayout, stack: str) -> list[tuple[Path, str]]:
        """Writes that move `stack` and the stack's keys from config.toml to parts/app.toml."""
        text = app.config_file.read_text(encoding="utf-8")
        flat = _flatten(tomllib.loads(text))
        found = self._stack_or_none(stack)
        own = {s.key for s in found.manifest.settings.schema} if found else set()
        moved = {k: v for k, v in flat.items() if k in own}
        remaining = _remove_top_level_keys(text, {"stack", *moved})
        expected = {k: v for k, v in flat.items() if k != "stack" and k not in moved}
        if _flatten(tomllib.loads(remaining)) != expected:
            raise BullError(
                f"can't move the app's stack settings out of {app.config_file}",
                "write `stack` and the stack's keys as plain top-level lines, then retry",
            )
        return [
            (app.parts_dir / f"{_IMPLICIT}.toml", _part_toml(stack, ".", moved)),
            (app.config_file, remaining),
        ]


# ------------------------------------------------------------------ helpers


def _part_files(app: AppLayout) -> list[Path]:
    if not app.parts_dir.is_dir():
        return []
    return sorted(p for p in app.parts_dir.glob("*.toml") if p.is_file())


def _read_toml(path: Path) -> dict[str, object] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise BullError(f"{path}: {error}", "fix the TOML syntax") from error


def _read_part_file(path: Path) -> _Entry:
    data = _read_toml(path) or {}
    stack = data.get("stack")
    folder = data.get("dir", ".")
    if not isinstance(stack, str) or not isinstance(folder, str):
        raise BullError(
            f"{path}: `stack` and `dir` must be strings", "fix the part file"
        )
    return _Entry(path.stem, stack, folder, implicit=False)


def _root(app: AppLayout, folder: str) -> Path:
    clean = _clean_dir(folder)
    return app.root if clean == "." else app.root / clean


def _clean_dir(folder: str) -> str:
    """A part folder normalized; refuses absolute folders and ones outside the app."""
    if folder.startswith("/") or PurePosixPath(folder).is_absolute():
        raise BullError(f"part folder `{folder}` must be relative to the app")
    clean = posixpath.normpath(folder) if folder else "."
    if clean == ".." or clean.startswith("../"):
        raise BullError(f"part folder `{folder}` is outside the app")
    return clean


def _rel(folder: str) -> PurePosixPath:
    return PurePosixPath(posixpath.normpath(folder) if folder else ".")


def _within(inner: PurePosixPath, outer: PurePosixPath) -> bool:
    return str(outer) == "." or inner == outer or inner.is_relative_to(outer)


def _overlap(
    a: PurePosixPath,
    a_inner: tuple[PurePosixPath, ...],
    b: PurePosixPath,
    b_inner: tuple[PurePosixPath, ...],
) -> bool:
    """Whether two part folders clash.

    Equal folders clash, and so do nested ones, except that a root part (`.`) may hold
    another part's folder as long as none of its own source or test folders contains it.
    """
    if a == b:
        return True
    if str(a) == ".":
        return any(_within(b, inner) for inner in a_inner)
    if str(b) == ".":
        return any(_within(a, inner) for inner in b_inner)
    return _within(a, b) or _within(b, a)


def _own_values(layer: StackLayer) -> dict[str, object]:
    """The stack's defaults for its own keys (not bull keys it also gives defaults for)."""
    keys = {s.key for s in layer.schema}
    return {k: v for k, v in layer.values.items() if k in keys}


def _flatten(data: Mapping[str, object], prefix: str = "") -> dict[str, object]:
    flat: dict[str, object] = {}
    for key, value in data.items():
        full = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(_flatten(value, f"{full}."))
        else:
            flat[full] = value
    return flat


def _toml_key(key: str) -> str:
    return ".".join(
        seg if _BARE_KEY.match(seg) else json.dumps(seg) for seg in key.split(".")
    )


def _toml_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    raise BullError(f"can't write a {type(value).__name__} value to a part file")


def _part_toml(stack: str, folder: str, values: Mapping[str, object]) -> str:
    lines = [
        f"format = {_FORMAT}",
        f"stack = {_toml_value(stack)}",
        f"dir = {_toml_value(folder)}",
    ]
    lines.extend(
        f"{_toml_key(k)} = {_toml_value(v)}"
        for k, v in values.items()
        if k not in {"format", "stack", "dir"}
    )
    return "\n".join(lines) + "\n"


_KEY_LINE = re.compile(r"^\s*([^=\[#][^=]*?)\s*=")


def _remove_top_level_keys(text: str, keys: set[str]) -> str:
    """Drop `key = value` lines for `keys` before the first table header.

    Comments and other lines stay as written. A multi-line array value is dropped up to
    its closing bracket. The caller verifies the result by parsing it.
    """
    out: list[str] = []
    lines = text.splitlines(keepends=True)
    i = 0
    in_tables = False
    while i < len(lines):
        line = lines[i]
        if line.lstrip().startswith("["):
            in_tables = True
        match = None if in_tables else _KEY_LINE.match(line)
        if match is not None and _key_name(match.group(1)) in keys:
            depth = _bracket_depth(line[match.end() :])
            i += 1
            while depth > 0 and i < len(lines):
                depth += _bracket_depth(lines[i])
                i += 1
            continue
        out.append(line)
        i += 1
    return "".join(out)


def _key_name(raw: str) -> str:
    return ".".join(seg.strip().strip("\"'") for seg in raw.split("."))


def _bracket_depth(fragment: str) -> int:
    """Net `[` minus `]` outside strings and comments in a line fragment."""
    depth = 0
    quote = ""
    for ch in fragment:
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch == "#":
            break
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
    return depth


def _gitignore_line(folder: str, line: str) -> str:
    """A stack gitignore line moved under the part's folder (unchanged for a root part)."""
    if folder == ".":
        return line
    negate = line.startswith("!")
    body = line[1:] if negate else line
    moved = f"/{folder}{body}" if body.startswith("/") else f"{folder}/{body}"
    return ("!" if negate else "") + moved


def _gitignore_write(
    app: AppLayout, folder: str, stack_lines: Sequence[str]
) -> tuple[Path, str] | None:
    """The new `.gitignore` with the stack's lines added, or None if none are new."""
    path = app.root / ".gitignore"
    try:
        current = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        current = ""
    present = set(current.splitlines())
    added: list[str] = []
    for raw in stack_lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        moved = _gitignore_line(folder, line)
        if moved not in present and moved not in added:
            added.append(moved)
    if not added:
        return None
    if current and not current.endswith("\n"):
        current += "\n"
    return path, current + "".join(f"{line}\n" for line in added)


def _write_atomic(path: Path, text: str) -> None:
    """Write `text` to a temp file beside `path`, then rename it into place."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise
