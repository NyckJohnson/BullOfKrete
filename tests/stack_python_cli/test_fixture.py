"""Tests for the python_cli stack's sample app (`fixture/app/`) and the end-to-end self-test."""

from __future__ import annotations

import ast
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import bull.Modules.stack_python_cli as pkg
from bull.Modules.memo.Contracts import SideRef
from bull.Modules.memo.parser import LiveMemoReader
from bull.Modules.stacks.Contracts import Stack
from bull.Modules.stacks.registry import LiveStackRegistry
from bull.Modules.stacktest.Contracts import CaseVerdict
from bull.Modules.stacktest.runner import LiveStackTester
from bull.Modules.stacktest.static import static

_FOLDER = Path(pkg.__file__).parent / "python_cli"
_APP = _FOLDER / "fixture" / "app"
_MODULE = _APP / "src" / "fixture_cli" / "Modules" / "counter"
_BULL = (sys.executable, "-m", "bull")

needs_uv = pytest.mark.skipif(shutil.which("uv") is None, reason="uv is not on PATH")


@pytest.fixture(scope="module")
def stack(tmp_path_factory: pytest.TempPathFactory) -> Stack:
    return LiveStackRegistry([], tmp_path_factory.mktemp("userdata")).load_path(_FOLDER)


@pytest.mark.parametrize(
    "relative",
    [
        "docs/outline.md",
        "pyproject.toml",
        "src/fixture_cli/__init__.py",
        "src/fixture_cli/cli.py",
        "src/fixture_cli/Modules/counter/Contracts/__init__.py",
        "src/fixture_cli/Modules/counter/counter.py",
        "tests/counter/test_counter.py",
        "tests/journey/test_count.py",
        "interfaces/count.json",
        "docs/api/counter.md",
        "docs/api/interfaces/Count.md",
    ],
)
def test_fixture_app_has_the_file(relative: str) -> None:
    assert (_APP / relative).is_file(), relative


def test_pyproject_names_the_fixture_package() -> None:
    text = (_APP / "pyproject.toml").read_text()
    assert "fixture_cli" in text


def test_outline_parses_without_problems() -> None:
    reader = LiveMemoReader()
    memo = reader.parse((_APP / "docs" / "outline.md").read_text())
    assert memo.parse_problems == ()
    assert reader.problems(memo, ["app"], 8) == []


def test_outline_has_the_counter_module_and_build_order() -> None:
    memo = LiveMemoReader().parse((_APP / "docs" / "outline.md").read_text())
    assert [m.name for m in memo.modules] == ["counter"]
    assert [b.name for b in memo.build_order] == ["counter"]


def test_outline_has_the_count_journey() -> None:
    memo = LiveMemoReader().parse((_APP / "docs" / "outline.md").read_text())
    assert [j.title for j in memo.journeys] == ["Count"]


def test_outline_declares_the_count_interface_provided_by_counter() -> None:
    memo = LiveMemoReader().parse((_APP / "docs" / "outline.md").read_text())
    (interface,) = memo.interfaces
    assert interface.name == "Count"
    assert interface.file == "interfaces/count.json"
    assert interface.format == "json-schema"
    assert interface.provider == SideRef("app", "counter")
    assert interface.consumers == ()


def test_outline_has_a_commands_section_with_the_count_command() -> None:
    items = LiveMemoReader().section_items(
        (_APP / "docs" / "outline.md").read_text(), "Commands"
    )
    assert any("fixture_cli count" in item for item in items)


def test_counter_contract_declares_store_protocol_and_count_dataclass() -> None:
    tree = ast.parse((_MODULE / "Contracts" / "__init__.py").read_text())
    classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}
    assert {"CounterStore", "Count"} <= set(classes)
    methods = {
        n.name for n in classes["CounterStore"].body if isinstance(n, ast.FunctionDef)
    }
    assert {"value", "increment"} <= methods
    fields = [
        n.target.id
        for n in classes["Count"].body
        if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)
    ]
    assert fields == ["value"]


def test_count_schema_has_title_and_required_integer_value() -> None:
    schema = json.loads((_APP / "interfaces" / "count.json").read_text())
    assert schema["title"] == "Count"
    assert schema["properties"]["value"]["type"] == "integer"
    assert schema["required"] == ["value"]


def test_static_check_passes_for_the_python_cli_stack(stack: Stack) -> None:
    report = static(stack)
    assert report.static is True
    assert report.problems == ()
    assert report.ok


def test_bull_stack_test_static_passes_without_uv() -> None:
    done = subprocess.run(
        [*_BULL, "stack", "test", str(_FOLDER), "--static", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    data = json.loads(done.stdout)
    assert data["stack"] == "python_cli"
    assert data["problems"] == []
    assert done.returncode == 0


@needs_uv
def test_every_case_passes_end_to_end(stack: Stack) -> None:
    report = LiveStackTester(_BULL).run(stack, None)
    assert report.problems == ()
    wrong = [
        f"{r.id}: expected {r.expected}, got {r.got}"
        for r in report.cases
        if r.verdict is not CaseVerdict.PASS
    ]
    assert wrong == []
    assert report.ok


@needs_uv
def test_bull_stack_test_command_passes_for_python_cli() -> None:
    done = subprocess.run(
        [*_BULL, "stack", "test", "python_cli", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    data = json.loads(done.stdout)
    assert data["stack"] == "python_cli"
    assert data["problems"] == []
    assert [c for c in data["cases"] if c["verdict"] != "pass"] == []
    assert done.returncode == 0
