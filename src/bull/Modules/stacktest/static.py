"""The static shape check of a stack folder.

Needs no toolchain: files are read and parsed (TOML, JSON, Python `ast`), never
executed. Each miss is one problem string in the returned report.
"""

from __future__ import annotations

import ast
import re
import tomllib
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import cast

from bull.Modules.stacks.Contracts import Stack, StackError
from bull.Modules.stacktest.cases import load_cases
from bull.Modules.stacktest.Contracts import StackTestReport

_FILES = ("stack.toml", "readers.py", "rules.md", "setup.md", "cases.json")
_READER_FUNCTIONS = ("contract_declarations", "test_results", "uncovered", "check")
_STACK_KEYS = (
    "name",
    "title",
    "description",
    "language",
    "kind",
    "maturity",
    "source_glob",
    "test_glob",
    "comment",
    "scaffold",
    "gitignore",
    "agents",
)
_GATE_KEYS = (
    "preflight",
    "setup",
    "build_test",
    "build_test_fast",
    "lint",
    "rerun_failed",
)
_SETTING_KEYS = ("source_dir", "test_dir")
_BASE_IDS = (
    "clean",
    "fast",
    "no-tests",
    "failing-test",
    "build-warning",
    "lint",
    "contract-change",
    "uncovered",
    "exemption",
    "setup-broken",
)
_HEADING = re.compile(r"^##\s+(.+?)\s*$")


def static(stack: Stack) -> StackTestReport:
    """Check the shape of `stack.home` without running anything.

    Checks the required files and a non-empty `fixture/` folder, that `stack.toml` parses with
    the required tables and keys and no `TODO` placeholder, that `readers.py`
    defines the required functions (via `ast`, never imported), that `rules.md`
    has `## common`, `## outline` and one section per manifest agent, that
    `setup.md` has `## For a feature`, and that `cases.json` holds every
    required case id. Returns a report with `static=True` and no cases.
    """
    home = stack.home
    problems: list[str] = []
    present = set()
    for name in _FILES:
        if (home / name).is_file():
            present.add(name)
        else:
            problems.append(f"missing {name}")
    fixture = home / "fixture"
    if not fixture.is_dir():
        problems.append("missing fixture/ folder")
    elif not any(fixture.iterdir()):
        problems.append("fixture/ folder is empty")

    if "stack.toml" in present:
        problems.extend(_manifest_problems(home / "stack.toml"))

    defined: set[str] | None = None
    if "readers.py" in present:
        defined, reader_problems = _readers(home / "readers.py")
        problems.extend(reader_problems)

    if "rules.md" in present:
        heads = _headings(home / "rules.md")
        for section in ("common", "outline", *stack.manifest.agents):
            if section.lower() not in heads:
                problems.append(f"rules.md has no `## {section}` section")

    if "setup.md" in present and "for a feature" not in _headings(home / "setup.md"):
        problems.append("setup.md has no `## For a feature` section")

    if "cases.json" in present:
        problems.extend(_case_problems(stack, defined))

    return StackTestReport(
        stack=stack.manifest.name, static=True, problems=tuple(problems), cases=()
    )


def _manifest_problems(path: Path) -> list[str]:
    """Self-contained check of `stack.toml` (decision 2026-11-12, option C)."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        return [f"stack.toml does not load: {error}"]
    problems: list[str] = []
    if data.get("format") != 1 or isinstance(data.get("format"), bool):
        problems.append(f"stack.toml: `format` must be 1, got {data.get('format')!r}")
    for table, keys in (("stack", _STACK_KEYS), ("gates", _GATE_KEYS)):
        section = data.get(table)
        if not isinstance(section, dict):
            problems.append(f"stack.toml: missing `[{table}]` table")
            continue
        problems.extend(
            f"stack.toml: missing `{table}.{key}`" for key in keys if key not in section
        )
    settings = data.get("settings")
    settings_map = (
        cast("dict[str, object]", settings) if isinstance(settings, dict) else {}
    )
    problems.extend(
        f"stack.toml: missing `[settings.{key}]`"
        for key in _SETTING_KEYS
        if not isinstance(settings_map.get(key), dict)
    )
    problems.extend(
        f"stack.toml: `{where}` is a TODO placeholder"
        for where in _todo_values(data, "")
    )
    return problems


def _todo_values(value: object, where: str) -> Iterator[str]:
    """Yield the dotted path of every string value that contains `TODO`."""
    if isinstance(value, str):
        if "TODO" in value:
            yield where
    elif isinstance(value, Mapping):
        for key, item in cast("Mapping[str, object]", value).items():
            yield from _todo_values(item, f"{where}.{key}" if where else key)
    elif isinstance(value, list):
        for index, item in enumerate(cast("list[object]", value)):
            yield from _todo_values(item, f"{where}[{index}]")


def _readers(path: Path) -> tuple[set[str] | None, list[str]]:
    """Top-level names `readers.py` binds, and its problems; never imports it."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeDecodeError, SyntaxError, ValueError) as error:
        return None, [f"readers.py does not parse: {error}"]
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            names.add(node.name)
        elif isinstance(node, ast.ImportFrom | ast.Import):
            names.update(alias.asname or alias.name for alias in node.names)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    problems = [
        f"readers.py does not define `{func}`"
        for func in _READER_FUNCTIONS
        if func not in names
    ]
    return names, problems


def _headings(path: Path) -> set[str]:
    """Lower-cased `## ` headings of a Markdown file."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return set()
    return {
        match.group(1).lower()
        for line in text.splitlines()
        if (match := _HEADING.match(line))
    }


def _case_problems(stack: Stack, readers_names: set[str] | None) -> list[str]:
    try:
        cases = load_cases(stack)
    except StackError as error:
        return [f"cases.json does not load: {error}"]
    have = {case.id for case in cases}
    manifest = stack.manifest
    has_detect = (
        "detect" in readers_names
        if readers_names is not None
        else stack.optional.detect is not None
    )
    required = list(_BASE_IDS)
    if manifest.gates.journeys is not None:
        required += ["journey", "journey-failing"]
    if manifest.interface_formats:
        required.append("interface-drift")
    if manifest.run is not None:
        required.append("run-lifecycle")
    if has_detect:
        required.append("adopt-mode")
    return [
        f"cases.json has no case `{case_id}`"
        for case_id in required
        if case_id not in have
    ]
