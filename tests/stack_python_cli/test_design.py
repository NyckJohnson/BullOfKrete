"""Tests for the python_cli stack's `DESIGN.md`: template headings in order and the key facts."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import bull.Modules.stack_python_cli as pkg
import bull.Modules.stackflow as stackflow_pkg

_DESIGN = Path(pkg.__file__).parent / "python_cli" / "DESIGN.md"
_TEMPLATE = Path(stackflow_pkg.__file__).parent / "template" / "DESIGN.md"


def _headings(text: str) -> list[str]:
    return re.findall(r"^## (.+?)\s*$", text, flags=re.MULTILINE)


@pytest.fixture(scope="module")
def text() -> str:
    return _DESIGN.read_text()


def _section(text: str, heading: str) -> str:
    parts = re.split(r"^## .+$", text, flags=re.MULTILINE)
    names = _headings(text)
    return parts[names.index(heading) + 1]


def test_design_has_the_stack_title(text: str) -> None:
    assert text.splitlines()[0] == "# Python CLI stack: design"


def test_design_keeps_the_template_headings_in_order(text: str) -> None:
    assert _headings(text) == _headings(_TEMPLATE.read_text())
    assert _headings(text) == [
        "Language and tools",
        "Contracts",
        "Modules",
        "Kind",
        "Human setup",
        "Adoption support",
        "Interfaces and running",
        "Decisions log",
    ]


def test_design_is_not_the_placeholder(text: str) -> None:
    assert "placeholder" not in text.lower()


@pytest.mark.parametrize(
    "tool", ["uv", "pytest", "coverage", "ruff", "mypy --strict", "hatchling"]
)
def test_language_section_names_the_tool(text: str, tool: str) -> None:
    assert tool in _section(text, "Language and tools")


def test_language_section_states_python_floor(text: str) -> None:
    assert "3.11" in _section(text, "Language and tools")


def test_language_section_puts_mypy_in_the_build_step(text: str) -> None:
    body = _section(text, "Language and tools")
    assert re.search(
        r"mypy --strict.{0,60}build", body, flags=re.DOTALL | re.IGNORECASE
    )


def test_contracts_section_says_ast_and_contracts_folder(text: str) -> None:
    body = _section(text, "Contracts")
    assert "ast" in body
    assert "Contracts/__init__.py" in body


def test_modules_section_names_capitalized_folders_and_globs(text: str) -> None:
    body = _section(text, "Modules")
    assert "Modules" in body
    assert "Contracts" in body
    assert "mocks" in body
    assert "*.py" in body
    assert "test_*.py" in body


def test_kind_section_says_tool(text: str) -> None:
    assert "tool" in _section(text, "Kind")


def test_human_setup_section_mentions_uv_and_pyproject(text: str) -> None:
    body = _section(text, "Human setup")
    assert "uv" in body
    assert "pyproject.toml" in body


def test_adoption_section_says_none(text: str) -> None:
    assert "none" in _section(text, "Adoption support").lower()


def test_interfaces_section_names_json_schema_and_no_run(text: str) -> None:
    body = _section(text, "Interfaces and running")
    assert "json-schema" in body
    assert "[run]" in body


def test_decisions_log_has_dated_entries(text: str) -> None:
    entries = re.findall(
        r"^- (\d{4}-\d{2}-\d{2}):", _section(text, "Decisions log"), re.MULTILINE
    )
    assert len(entries) >= 4
    assert "2026-11-17" in entries


def test_decisions_log_records_the_core_decisions(text: str) -> None:
    body = _section(text, "Decisions log")
    for fact in ("hatchling", "ast", "mypy", "capitalized", "pytest-cov"):
        assert fact in body, fact
