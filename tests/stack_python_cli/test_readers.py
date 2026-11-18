"""Tests for `bull.Modules.stack_python_cli.python_cli.readers` (all but `interface_check`).

Choices where the spec is open: `test_results` derives node ids as
`<classname with dots as slashes>.py::<name>` (pytest's junit output for plain test functions);
`uncovered` reads coverage.py's JSON (`files.<path>.missing_lines`), path keys relative to the
part root or absolute; `check` returns one item per probe, found by words in the item text.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from bull.Modules.stack_python_cli.python_cli import readers
from bull.Modules.stacks.Contracts import CheckItem


def _decls(tmp_path: Path, text: str, name: str = "c.py") -> list[str]:
    f = tmp_path / name
    f.write_text(text)
    return readers.contract_declarations(f)


def _has(lines: list[str], pattern: str) -> bool:
    import re

    return any(re.search(pattern, line) for line in lines)


# --- contract_declarations ---------------------------------------------------------------


def test_contract_declarations_empty_module_gives_nothing(tmp_path: Path) -> None:
    assert _decls(tmp_path, "") == []


def test_contract_declarations_lists_protocol_with_base_and_method(
    tmp_path: Path,
) -> None:
    out = _decls(
        tmp_path,
        "from typing import Protocol\n\n"
        "class CounterStore(Protocol):\n"
        "    def value(self) -> int: ...\n"
        "    def increment(self, by: int) -> int: ...\n",
    )
    assert _has(out, r"CounterStore.*Protocol")
    assert _has(out, r"def value\(.*\) -> int")
    assert _has(out, r"def increment\(.*by: int.*\) -> int")


def test_contract_declarations_lists_dataclass_with_decorator_and_fields(
    tmp_path: Path,
) -> None:
    out = _decls(
        tmp_path,
        "from dataclasses import dataclass\n\n"
        "@dataclass(frozen=True)\n"
        "class Point:\n"
        "    x: int\n"
        "    label: str | None = None\n",
    )
    assert _has(out, r"dataclass.*Point|Point.*dataclass")
    assert _has(out, r"x: int")
    assert _has(out, r"label: str \| None")


def test_contract_declarations_lists_enum_members(tmp_path: Path) -> None:
    out = _decls(
        tmp_path,
        "from enum import Enum\n\n"
        "class Colour(Enum):\n"
        "    RED = 'r'\n"
        "    GREEN = 'g'\n",
    )
    assert _has(out, r"Colour.*Enum")
    assert _has(out, r"RED")
    assert _has(out, r"GREEN")


def test_contract_declarations_lists_public_functions(tmp_path: Path) -> None:
    out = _decls(
        tmp_path, "def make_thing(a: int, b: str = 'x') -> str:\n    return b\n"
    )
    assert _has(out, r"def make_thing\(.*a: int.*\) -> str")


def test_contract_declarations_lists_type_aliases(tmp_path: Path) -> None:
    out = _decls(
        tmp_path,
        "from typing import TypeAlias\n\n"
        "Pair = tuple[int, int]\n"
        "Maybe: TypeAlias = int | None\n"
        "type Modern = list[str]\n",
    )
    assert _has(out, r"\bPair\b")
    assert _has(out, r"\bMaybe\b")
    assert _has(out, r"\bModern\b")


def test_contract_declarations_skips_private_names(tmp_path: Path) -> None:
    out = _decls(
        tmp_path,
        "from dataclasses import dataclass\n\n"
        "class _HiddenClass:\n    def shown(self) -> int: ...\n\n"
        "def _hidden_func() -> int:\n    return 1\n\n"
        "_HIDDEN_ALIAS = int\n\n"
        "class Public:\n"
        "    def _hidden_method(self) -> int: ...\n"
        "    def visible_method(self) -> int: ...\n\n"
        "@dataclass\nclass Fields:\n    _secret: int\n    open_field: int\n",
    )
    joined = "\n".join(out)
    for hidden in (
        "_HiddenClass",
        "_hidden_func",
        "_HIDDEN_ALIAS",
        "_hidden_method",
        "_secret",
    ):
        assert hidden not in joined
    assert "visible_method" in joined
    assert "open_field" in joined


def test_contract_declarations_ignore_formatting_comments_and_docstrings(
    tmp_path: Path,
) -> None:
    compact = (
        "from dataclasses import dataclass\n"
        "@dataclass\nclass A:\n    x: int\n    def go(self, a: int, b: str) -> bool: ...\n"
    )
    spread = (
        "from dataclasses import dataclass\n\n\n"
        "# a comment\n"
        "@dataclass\n"
        "class A:\n"
        '    """Docstring."""\n\n'
        "    x: int  # trailing\n\n"
        "    def go(\n"
        "        self,\n"
        "        a: int,\n"
        "        b: str,\n"
        "    ) -> bool:\n"
        '        """More docs."""\n'
        "        ...\n"
    )
    assert _decls(tmp_path, compact, "one.py") == _decls(tmp_path, spread, "two.py")


def test_contract_declarations_change_when_a_signature_changes(tmp_path: Path) -> None:
    before = _decls(tmp_path, "def f(a: int) -> int: ...\n", "a.py")
    after = _decls(tmp_path, "def f(a: str) -> int: ...\n", "b.py")
    assert before != after


def test_contract_declarations_change_when_a_field_is_added(tmp_path: Path) -> None:
    head = "from dataclasses import dataclass\n@dataclass\nclass A:\n    x: int\n"
    assert _decls(tmp_path, head, "a.py") != _decls(
        tmp_path, head + "    y: int\n", "b.py"
    )


# --- test_results ------------------------------------------------------------------------

_JUNIT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites name="pytest tests"><testsuite name="pytest" errors="{e}" failures="{f}" skipped="0" tests="{n}">
{cases}
</testsuite></testsuites>
"""


def _junit(results: Path, cases: str, n: int, f: int = 0, e: int = 0) -> None:
    results.mkdir(parents=True, exist_ok=True)
    (results / "junit.xml").write_text(_JUNIT.format(cases=cases, n=n, f=f, e=e))


def _case(cls: str, name: str, inner: str = "") -> str:
    return f'<testcase classname="{cls}" name="{name}" time="0.001">{inner}</testcase>'


def test_test_results_counts_passing_tests_with_none_failed(tmp_path: Path) -> None:
    _junit(
        tmp_path,
        _case("tests.counter.test_a", "test_one")
        + _case("tests.counter.test_a", "test_two"),
        n=2,
    )
    run = readers.test_results(tmp_path)
    assert run is not None
    assert run.count == 2
    assert tuple(run.failed) == ()


def test_test_results_lists_failed_and_errored_node_ids(tmp_path: Path) -> None:
    cases = (
        _case("tests.counter.test_a", "test_ok")
        + _case(
            "tests.counter.test_a", "test_bad", '<failure message="boom">x</failure>'
        )
        + _case("tests.other.test_b", "test_err", '<error message="oops">y</error>')
    )
    _junit(tmp_path, cases, n=3, f=1, e=1)
    run = readers.test_results(tmp_path)
    assert run is not None
    assert run.count == 3
    assert set(run.failed) == {
        "tests/counter/test_a.py::test_bad",
        "tests/other/test_b.py::test_err",
    }


def test_test_results_none_when_junit_missing(tmp_path: Path) -> None:
    assert readers.test_results(tmp_path) is None


def test_test_results_none_when_results_folder_missing(tmp_path: Path) -> None:
    assert readers.test_results(tmp_path / "nope") is None


# --- uncovered ---------------------------------------------------------------------------


def _coverage(results: Path, files: dict[str, list[int]]) -> None:
    results.mkdir(parents=True, exist_ok=True)
    data = {
        "files": {
            name: {"executed_lines": [], "missing_lines": missing}
            for name, missing in files.items()
        }
    }
    (results / "coverage.json").write_text(json.dumps(data))


def _source(root: Path, rel: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x = 1\n")
    return path


def test_uncovered_lists_missing_lines_per_source(tmp_path: Path) -> None:
    src = _source(tmp_path, "src/pkg/a.py")
    _coverage(tmp_path / "results", {"src/pkg/a.py": [3, 5, 9]})
    data = readers.uncovered(tmp_path, [src], tmp_path / "results")
    assert data.uncovered == {src: (3, 5, 9)}
    assert data.no_data == ()


def test_uncovered_accepts_absolute_paths_in_the_data(tmp_path: Path) -> None:
    src = _source(tmp_path, "src/pkg/a.py")
    _coverage(tmp_path / "results", {str(src): [2]})
    data = readers.uncovered(tmp_path, [src], tmp_path / "results")
    assert data.uncovered == {src: (2,)}


def test_uncovered_omits_a_fully_covered_source(tmp_path: Path) -> None:
    src = _source(tmp_path, "src/pkg/a.py")
    _coverage(tmp_path / "results", {"src/pkg/a.py": []})
    data = readers.uncovered(tmp_path, [src], tmp_path / "results")
    assert src not in data.uncovered
    assert data.no_data == ()


def test_uncovered_source_absent_from_the_data_is_no_data(tmp_path: Path) -> None:
    covered = _source(tmp_path, "src/pkg/a.py")
    absent = _source(tmp_path, "src/pkg/b.py")
    _coverage(tmp_path / "results", {"src/pkg/a.py": [1]})
    data = readers.uncovered(tmp_path, [covered, absent], tmp_path / "results")
    assert data.no_data == (absent,)
    assert absent not in data.uncovered


def test_uncovered_without_any_coverage_file_reports_every_source_as_no_data(
    tmp_path: Path,
) -> None:
    src = _source(tmp_path, "src/pkg/a.py")
    data = readers.uncovered(tmp_path, [src], tmp_path / "results")
    assert data.no_data == (src,)
    assert data.uncovered == {}


def test_uncovered_with_no_sources_is_empty(tmp_path: Path) -> None:
    _coverage(tmp_path / "results", {"src/pkg/a.py": [1]})
    data = readers.uncovered(tmp_path, [], tmp_path / "results")
    assert data.uncovered == {}
    assert data.no_data == ()


# --- check -------------------------------------------------------------------------------


def _item(items: list[CheckItem], word: str) -> CheckItem:
    matches = [i for i in items if word in i.item.lower()]
    assert matches, [i.item for i in items]
    return matches[0]


def _part(root: Path, package: str = "demo_pkg") -> None:
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "{package}"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n'
    )
    pkg = root / "src" / package
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")


def _fake_uv(bin_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    exe = bin_dir / "uv"
    exe.write_text("#!/bin/sh\nexit 0\n")
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))


def test_check_reports_uv_missing_with_a_fix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    items = readers.check(tmp_path, {"package": "demo_pkg"}, False)
    uv = _item(items, "uv")
    assert uv.ok is False
    assert uv.fix


def test_check_reports_uv_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_uv(tmp_path / "bin", monkeypatch)
    items = readers.check(tmp_path, {"package": "demo_pkg"}, False)
    assert _item(items, "uv").ok is True


def test_check_reports_missing_pyproject_with_a_fix(tmp_path: Path) -> None:
    items = readers.check(tmp_path, {"package": "demo_pkg"}, False)
    item = _item(items, "pyproject")
    assert item.ok is False
    assert item.fix


def test_check_reports_present_pyproject(tmp_path: Path) -> None:
    _part(tmp_path)
    items = readers.check(tmp_path, {"package": "demo_pkg"}, False)
    assert _item(items, "pyproject").ok is True


def test_check_reports_unimportable_package_with_a_fix(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "0"\n')
    items = readers.check(tmp_path, {"package": "no_such_pkg_zz"}, False)
    item = _item(items, "package")
    assert item.ok is False
    assert item.fix


def test_check_accepts_python_311_or_newer(tmp_path: Path) -> None:
    assert sys.version_info >= (3, 11)
    items = readers.check(tmp_path, {"package": "demo_pkg"}, False)
    assert _item(items, "python").ok is True


def test_check_items_are_all_check_items(tmp_path: Path) -> None:
    items = readers.check(tmp_path, {"package": "demo_pkg"}, False)
    assert items
    assert all(isinstance(i, CheckItem) for i in items)
