"""The `python_cli` stack's readers: the functions bull imports from this folder.

Contracts are read with `ast`, so formatting, comments and docstrings never change the result.
Test results come from pytest's `<results>/junit.xml` and coverage from coverage.py's
`<results>/coverage.json`, both written by `gates.py`.
"""

from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from bull.Modules.stacks.Contracts import CheckItem, CoverageData, Role, TestRun

from . import schema_check
from .gates import (
    DEFAULT_PACKAGE,
    IMPORT_BY_ARGUMENT,
    UV_HINT,
    junit_run,
    valid_package,
)

_MIN_PYTHON = (3, 11)
_PYVENV_VERSION = re.compile(r"^\s*version(?:_info)?\s*=\s*(\d+)\.(\d+)", re.MULTILINE)
_SHOWN_METHOD_DECORATORS = frozenset(
    {"property", "classmethod", "staticmethod", "abstractmethod"}
)
"""Method decorators that change how a method is called, so they are part of its contract."""


# --- contract_declarations -----------------------------------------------------------------


def _public(name: str) -> bool:
    return not name.startswith("_")


def _decorator_name(node: ast.expr) -> str:
    """`abstractmethod` for both `@abstractmethod` and `@abc.abstractmethod`; '' otherwise."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _signature(fn: ast.FunctionDef | ast.AsyncFunctionDef, method: bool) -> str:
    """`def name(args) -> ret`, without the `self`/`cls` of a method.

    A method's `@property`, `@classmethod`, `@staticmethod` and `@abstractmethod` decorators
    come first, in source order: `@property @abstractmethod def name() -> ret`.
    """
    args = fn.args
    shown = (
        [d for d in fn.decorator_list if _decorator_name(d) in _SHOWN_METHOD_DECORATORS]
        if method
        else []
    )
    is_static = any(_decorator_name(d) == "staticmethod" for d in shown)
    if method and not is_static:
        positional = [*args.posonlyargs, *args.args]
        if positional:
            first = positional[0]
            args = ast.arguments(
                posonlyargs=[a for a in args.posonlyargs if a is not first],
                args=[a for a in args.args if a is not first],
                vararg=args.vararg,
                kwonlyargs=args.kwonlyargs,
                kw_defaults=args.kw_defaults,
                kwarg=args.kwarg,
                defaults=args.defaults,
            )
    prefix = "async def" if isinstance(fn, ast.AsyncFunctionDef) else "def"
    returns = f" -> {ast.unparse(fn.returns)}" if fn.returns else ""
    decorators = "".join(f"@{ast.unparse(d)} " for d in shown)
    return f"{decorators}{prefix} {fn.name}({ast.unparse(args)}){returns}"


def _class_lines(cls: ast.ClassDef) -> list[str]:
    decorators = "".join(f"@{ast.unparse(d)} " for d in cls.decorator_list)
    bases = [ast.unparse(b) for b in (*cls.bases, *cls.keywords)]
    head = f"{decorators}class {cls.name}" + (f"({', '.join(bases)})" if bases else "")
    lines = [head]
    for node in cls.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if _public(node.name):
                lines.append(f"{cls.name}.{_signature(node, method=True)}")
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if _public(node.target.id):
                lines.append(
                    f"{cls.name}.{node.target.id}: {ast.unparse(node.annotation)}"
                )
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and _public(target.id):
                    lines.append(f"{cls.name}.{target.id}")
    return lines


def _type_alias_line(node: ast.stmt) -> str | None:
    """`type X = …` (Python 3.12+ syntax), when the running Python parses it."""
    alias = getattr(ast, "TypeAlias", None)
    if alias is None or not isinstance(node, alias):
        return None
    name: object = getattr(node, "name", None)
    value: object = getattr(node, "value", None)
    if not isinstance(name, ast.Name) or not isinstance(value, ast.expr):
        return None
    return f"type {name.id} = {ast.unparse(value)}" if _public(name.id) else None


def contract_declarations(path: Path) -> list[str]:
    """The public declarations of one Python file, one line each, in file order.

    Lists top-level public classes (`@decorators class Name(bases)`), their public methods
    (`Class.def name(args) -> ret`, or `Class.@property def name() -> ret` when decorated with
    `@property`, `@classmethod`, `@staticmethod` or `@abstractmethod`), annotated fields (`Class.name: type`) and plain class
    attributes such as enum members (`Class.NAME`); public functions (`def name(args) -> ret`);
    and public module-level aliases (`Name = value`, `Name: type = value`, `type Name = value`).
    Names starting with `_` are skipped. Raises `SyntaxError` for a file that doesn't parse.
    """
    tree = ast.parse(path.read_text(), filename=str(path))
    out: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            if _public(node.name):
                out.extend(_class_lines(node))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if _public(node.name):
                out.append(_signature(node, method=False))
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and _public(target.id):
                    out.append(f"{target.id} = {ast.unparse(node.value)}")
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if _public(node.target.id):
                value = f" = {ast.unparse(node.value)}" if node.value else ""
                out.append(f"{node.target.id}: {ast.unparse(node.annotation)}{value}")
        else:
            line = _type_alias_line(node)
            if line:
                out.append(line)
    return out


# --- test_results / uncovered --------------------------------------------------------------


def test_results(results: Path) -> TestRun | None:
    """The last run from `<results>/junit.xml`: test count and failed or errored node ids.

    None when the file is missing or not valid XML.
    """
    found = junit_run(results / "junit.xml")
    if found is None:
        return None
    count, failed = found
    return TestRun(count=count, failed=tuple(failed))


def _missing_lines(
    part_root: Path, results: Path
) -> dict[Path, tuple[int, ...]] | None:
    """coverage.py's JSON as resolved path → missing lines; None when absent or unreadable."""
    path = results / "coverage.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    files = data.get("files") if isinstance(data, dict) else None
    if not isinstance(files, dict):
        return None
    out: dict[Path, tuple[int, ...]] = {}
    for name, entry in files.items():
        missing = entry.get("missing_lines") if isinstance(entry, dict) else None
        if not isinstance(missing, list):
            continue
        key = Path(str(name))
        if not key.is_absolute():
            key = part_root / key
        out[key.resolve()] = tuple(n for n in missing if isinstance(n, int))
    return out


def uncovered(part_root: Path, sources: Sequence[Path], results: Path) -> CoverageData:
    """Missing lines per source from `<results>/coverage.json`.

    Keys are the given source paths; fully covered sources are omitted. A source the data
    doesn't mention (or every source, when the file is missing) is listed under `no_data`.
    """
    data = _missing_lines(part_root, results) or {}
    missing: dict[Path, tuple[int, ...]] = {}
    no_data: list[Path] = []
    for source in sources:
        lines = data.get(source.resolve())
        if lines is None:
            no_data.append(source)
        elif lines:
            missing[source] = lines
    return CoverageData(uncovered=missing, no_data=tuple(no_data))


# --- check ---------------------------------------------------------------------------------


def _setting(settings: Mapping[str, object], key: str) -> str:
    value = settings.get(key)
    return value if isinstance(value, str) else ""


def _venv_python(part_root: Path) -> Path | None:
    for rel in (".venv/bin/python", ".venv/Scripts/python.exe"):
        candidate = part_root / rel
        if candidate.is_file():
            return candidate
    return None


def _python_version_item(part_root: Path) -> CheckItem:
    """Python ≥ 3.11: the app venv's version (from `.venv/pyvenv.cfg`), else this interpreter's.

    An unreadable `pyvenv.cfg` fails the item (the venv is broken) rather than raising.
    """
    cfg = part_root / ".venv" / "pyvenv.cfg"
    version = (sys.version_info.major, sys.version_info.minor)
    where = "bull's interpreter"
    if cfg.is_file():
        try:
            text = cfg.read_text()
        except (OSError, UnicodeDecodeError) as exc:
            return CheckItem(
                ok=False,
                item="Python 3.11 or newer (the app's .venv/pyvenv.cfg is unreadable)",
                fix=f"{exc}; re-run `uv sync` in the part folder",
            )
        match = _PYVENV_VERSION.search(text)
        if match:
            version = (int(match[1]), int(match[2]))
            where = "the app's .venv"
    return CheckItem(
        ok=version >= _MIN_PYTHON,
        item=f"Python 3.11 or newer ({version[0]}.{version[1]} in {where})",
        fix="pin a newer Python: `uv python pin 3.11` (or newer), then `uv sync`",
    )


def _package_item(part_root: Path, settings: Mapping[str, object]) -> CheckItem:
    package = _setting(settings, "package") or DEFAULT_PACKAGE
    source_dir = _setting(settings, "source_dir") or f"src/{package}"
    item = f"package `{package}` importable"
    if not valid_package(package):
        return CheckItem(
            ok=False,
            item=item,
            fix="the package setting must be a dotted Python name: "
            "run `bull config set package <package>`",
        )
    if not (part_root / source_dir / "__init__.py").is_file():
        return CheckItem(
            ok=False,
            item=item,
            fix=f"create {source_dir}/__init__.py (see `bull stack setup`)",
        )
    python = _venv_python(part_root)
    if python is not None:
        try:
            with subprocess.Popen(
                [str(python), "-c", IMPORT_BY_ARGUMENT, package],
                cwd=part_root,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            ) as proc:
                _, err = proc.communicate()
        except OSError as exc:
            return CheckItem(
                ok=False,
                item=item,
                fix=f"can't run {python} ({exc.strerror or exc}); "
                "delete .venv and run `uv sync`",
            )
        if proc.returncode != 0:
            last = err.strip().splitlines()[-1] if err.strip() else "import failed"
            return CheckItem(
                ok=False,
                item=item,
                fix=f"{last}; check pyproject.toml's packages and run `uv sync`",
            )
    return CheckItem(ok=True, item=item, fix="")


def check(
    part_root: Path, settings: Mapping[str, object], adopting: bool
) -> list[CheckItem]:
    """The part's setup: `uv` on PATH, `pyproject.toml`, the package imports, Python ≥ 3.11.

    Settings fall back to the manifest defaults (`package` `myapp`, `source_dir` `src/<package>`).
    The import is tried with the app's `.venv` interpreter when it exists, the package name passed
    as an argument (a name that isn't a dotted identifier fails the item); without one, the
    package folder (`<source_dir>/__init__.py`) must exist. `adopting` changes nothing: the
    stack has no adoption support.
    """
    items = [
        CheckItem(
            ok=shutil.which("uv") is not None,
            item="`uv` on PATH",
            fix=f"install uv: {UV_HINT}",
        ),
        CheckItem(
            ok=(part_root / "pyproject.toml").is_file(),
            item="pyproject.toml present at the part root",
            fix="write pyproject.toml from the template in `bull stack setup`",
        ),
        _package_item(part_root, settings),
        _python_version_item(part_root),
    ]
    return [i if not i.ok else CheckItem(ok=True, item=i.item, fix="") for i in items]


def interface_check(
    part_root: Path,
    settings: Mapping[str, object],
    interface: Path,
    format: str,
    role: Role,
    module: str,
) -> list[CheckItem]:
    """One side's interface check (json-schema), done by `schema_check.py`.

    The contract read is `<part_root>/<source_dir>/Modules/<module>/Contracts/__init__.py`
    (`source_dir` falls back to `src/<package>`). Failing items name the role in lowercase
    (`provider`/`consumer`) and the field at fault; bad input gives failing items, never raises.
    """
    package = _setting(settings, "package") or DEFAULT_PACKAGE
    source_dir = _setting(settings, "source_dir") or f"src/{package}"
    contract = part_root / source_dir / "Modules" / module / "Contracts" / "__init__.py"
    findings = schema_check.check(contract, interface, format, role.name.lower())
    return [CheckItem(ok=f.ok, item=f.item, fix=f.fix) for f in findings]
