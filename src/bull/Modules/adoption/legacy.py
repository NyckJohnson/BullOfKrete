"""The legacy check: what an adoption has left to replace."""

from __future__ import annotations

import os
from collections.abc import Iterable, Iterator
from pathlib import Path

from bull.Modules.adoption.Contracts import LegacyLeft
from bull.Modules.foundation.Contracts import AppLayout, Files
from bull.Modules.memo.Contracts import Memo, MemoReader
from bull.Modules.parts.Contracts import Part, Parts
from bull.Modules.stacks.Contracts import StackRegistry

_PYCACHE = "__pycache__"


def legacy_left(
    app: AppLayout,
    files: Files,
    parts: Parts,
    memo_reader: MemoReader,
    stacks: StackRegistry,
) -> LegacyLeft:
    """Legacy code still in the app's one part; reads only, changes nothing.

    Paths are POSIX, relative to `app.root`, sorted and without duplicates.
    """
    part = parts.get(app, None)
    memo = _memo(app, files, memo_reader)
    shell: tuple[str, ...] = ()
    shell_tests: tuple[str, ...] = ()
    if memo is not None and memo.legacy is not None:
        shell = memo.legacy.app_shell
        shell_tests = memo.legacy.app_shell_tests

    source = part.root / part.source_dir
    modules_dir = source / "Modules"
    left_files = _paths(
        app,
        (p for p in _walk(source) if not p.is_relative_to(modules_dir)),
        exclude=shell,
    )

    module_tests: list[Path] = []
    if memo is not None:
        module_tests = [parts.module_tests(part, m.name) for m in memo.modules]
    left_tests = _paths(
        app,
        (
            p
            for p in _walk(part.root / part.test_dir)
            if not any(p.is_relative_to(folder) for folder in module_tests)
        ),
        exclude=shell_tests,
    )

    memo_files: tuple[str, ...] = ()
    if memo is not None:
        named = {
            _posix(entry)
            for module in memo.modules
            for entry in (*module.legacy_files, *module.legacy_tests)
        }
        memo_files = tuple(sorted(e for e in named if (app.root / e).exists()))

    return LegacyLeft(
        files=left_files,
        declarations=_declarations(part, stacks),
        tests=left_tests,
        memo_files=memo_files,
    )


def _memo(app: AppLayout, files: Files, reader: MemoReader) -> Memo | None:
    text = files.read_text(app.memo_file)
    return None if text is None else reader.parse(text)


def _declarations(part: Part, stacks: StackRegistry) -> tuple[str, ...]:
    reader = stacks.get(part.stack).optional.legacy_declarations
    if reader is None:
        return ()
    return tuple(sorted({n for n in reader(part.root) if n.startswith("Legacy")}))


def _walk(base: Path) -> Iterator[Path]:
    """Every file under `base`, skipping `__pycache__` folders and dotfiles (and dot folders)."""
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d != _PYCACHE and not d.startswith(".")]
        folder = Path(dirpath)
        for name in filenames:
            if not name.startswith("."):
                yield folder / name


def _paths(
    app: AppLayout, found: Iterable[Path], exclude: tuple[str, ...]
) -> tuple[str, ...]:
    """`found` relative to `app.root`, less `exclude`.

    An `exclude` entry ending in `/` names a folder and covers everything under it; any other
    entry names one file.
    """
    exact = {_posix(e) for e in exclude if not e.endswith("/")}
    folders = tuple(_posix(e) + "/" for e in exclude if e.endswith("/"))
    relative = {p.relative_to(app.root).as_posix() for p in found}
    return tuple(sorted(r for r in relative - exact if not r.startswith(folders)))


def _posix(entry: str) -> str:
    return Path(entry).as_posix()


def left_lines(left: LegacyLeft) -> list[str]:
    """One `<field>: <entry>` line per entry, grouped by field in declaration order."""
    fields = (
        ("files", left.files),
        ("declarations", left.declarations),
        ("tests", left.tests),
        ("memo_files", left.memo_files),
    )
    return [f"{name}: {entry}" for name, entries in fields for entry in entries]
