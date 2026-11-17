"""Tests for the stack repo templates: DESIGN.md, stack.toml and cases.json."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

import pytest

import bull.Modules.stackflow as stackflow_package

TEMPLATE = Path(stackflow_package.__file__).parent / "template"

DESIGN_SECTIONS = [
    "Language and tools",
    "Contracts",
    "Modules",
    "Kind",
    "Human setup",
    "Adoption support",
    "Interfaces and running",
    "Decisions log",
]

REQUIRED_CASE_IDS = [
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
    "journey",
    "journey-failing",
    "interface-drift",
    "run-lifecycle",
    "adopt-mode",
]


def manifest() -> dict[str, Any]:
    return tomllib.loads((TEMPLATE / "stack.toml").read_text())


def cases_file() -> dict[str, Any]:
    data = json.loads((TEMPLATE / "cases.json").read_text())
    assert isinstance(data, dict)
    return data


# --- DESIGN.md


@pytest.mark.parametrize("section", DESIGN_SECTIONS)
def test_design_has_the_section(section: str) -> None:
    headings = re.findall(
        r"^#{1,6}\s+(.*?)\s*$", (TEMPLATE / "DESIGN.md").read_text(), re.MULTILINE
    )
    assert section in headings


def test_design_sections_come_in_the_spec_order() -> None:
    text = (TEMPLATE / "DESIGN.md").read_text()
    positions = [text.index(section) for section in DESIGN_SECTIONS]
    assert positions == sorted(positions)


def test_design_has_no_build_checklist() -> None:
    text = (TEMPLATE / "DESIGN.md").read_text()
    assert not re.search(r"^\s*[-*]\s+\[[ xX]\]", text, re.MULTILINE)
    assert "checklist" not in text.lower()


# --- stack.toml


def test_stack_toml_is_valid_toml_with_format_one() -> None:
    assert manifest()["format"] == 1


@pytest.mark.parametrize(
    "key",
    [
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
        "requires",
    ],
)
def test_stack_toml_has_every_stack_key(key: str) -> None:
    assert key in manifest()["stack"]


@pytest.mark.parametrize(
    "key",
    [
        "preflight",
        "setup",
        "build_test",
        "build_test_fast",
        "lint",
        "rerun_failed",
        "journeys",
    ],
)
def test_stack_toml_has_every_gates_key(key: str) -> None:
    assert key in manifest()["gates"]


@pytest.mark.parametrize("key", ["start", "ready", "stop", "ready_timeout"])
def test_stack_toml_has_every_run_key(key: str) -> None:
    assert key in manifest()["run"]


def test_stack_toml_has_the_interfaces_formats_key() -> None:
    assert "formats" in manifest()["interfaces"]


def test_stack_toml_has_a_commands_table() -> None:
    assert isinstance(manifest()["commands"], dict)


def test_stack_toml_has_a_requires_entry_with_tool_and_hint() -> None:
    requires = manifest()["stack"]["requires"]
    assert requires
    assert "tool" in requires[0]
    assert "hint" in requires[0]


def test_stack_toml_has_a_setting_with_type_default_and_description() -> None:
    settings = manifest()["settings"]
    assert any(
        isinstance(entry, dict) and {"type", "default", "description"} <= set(entry)
        for entry in settings.values()
    )


def test_stack_toml_maturity_is_experimental() -> None:
    assert manifest()["stack"]["maturity"] == "experimental"


@pytest.mark.parametrize("key", ["title", "description", "language", "source_glob"])
def test_stack_toml_text_values_are_todo_placeholders(key: str) -> None:
    assert "TODO" in manifest()["stack"][key]


# --- cases.json


def test_cases_json_has_format_layout_and_settings() -> None:
    data = cases_file()
    assert data["format"] == 1
    assert "layout" in data
    assert "settings" in data


def test_cases_json_has_every_required_case_id() -> None:
    ids = [case["id"] for case in cases_file()["cases"]]
    assert sorted(ids) == sorted(REQUIRED_CASE_IDS)


@pytest.mark.parametrize("case_id", REQUIRED_CASE_IDS)
def test_cases_json_case_has_an_empty_change(case_id: str) -> None:
    case = next(c for c in cases_file()["cases"] if c["id"] == case_id)
    assert case["change"] == {}


@pytest.mark.parametrize("case_id", REQUIRED_CASE_IDS)
def test_cases_json_case_has_a_run_and_an_expect(case_id: str) -> None:
    case = next(c for c in cases_file()["cases"] if c["id"] == case_id)
    assert isinstance(case["run"], list)
    assert isinstance(case["expect"], dict)


def test_cases_json_failing_test_case_has_a_then_step() -> None:
    case = next(c for c in cases_file()["cases"] if c["id"] == "failing-test")
    assert "run" in case["then"]
    assert "expect" in case["then"]
