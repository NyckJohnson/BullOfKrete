"""Tests for `bull.Modules.memo.templates` and the two shipped template files.

Shapes chosen here (for the code-writer):
  - `names()` returns ["backlog", "outline"] (sorted).
  - `text(name)` returns the content of `templates/<name>.md` next to the module
    (packaged with it); read as UTF-8, returned unchanged.
  - the outline template is meant to parse cleanly: the example lines are real (not in a
    fenced block, which the reader skips), so `LiveMemoReader` yields every line format.
  - the backlog template follows the idea-file format (`## <Title>` sections).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import bull.Modules.memo.templates as templates_module
from bull.Modules.foundation.Contracts import BullError
from bull.Modules.memo.Contracts import Memo
from bull.Modules.memo.parser import LiveMemoReader
from bull.Modules.memo.templates import LiveTemplates

BANNED = [
    "Xcode",
    "Swift",
    "SwiftUI",
    "UIKit",
    "iOS",
    "iPhone",
    "simulator",
    "XCUITest",
    "pytest",
    "mypy",
    "ruff",
    "xcodebuild",
]


def shipped(name: str) -> str:
    folder = Path(templates_module.__file__).parent / "templates"
    return (folder / f"{name}.md").read_text(encoding="utf-8")


def test_names_lists_backlog_and_outline() -> None:
    assert LiveTemplates().names() == ["backlog", "outline"]


@pytest.mark.parametrize("name", ["backlog", "outline"])
def test_text_returns_the_shipped_file_exactly(name: str) -> None:
    assert LiveTemplates().text(name) == shipped(name)


@pytest.mark.parametrize("name", ["backlog", "outline"])
def test_text_is_not_empty(name: str) -> None:
    assert LiveTemplates().text(name).strip() != ""


@pytest.mark.parametrize("name", ["nope", "", "Outline", "design"])
def test_unknown_name_raises_bull_error_listing_the_names(name: str) -> None:
    with pytest.raises(BullError) as caught:
        LiveTemplates().text(name)
    shown = f"{caught.value.message} {caught.value.fix}"
    assert "backlog" in shown
    assert "outline" in shown


@pytest.mark.parametrize("name", ["backlog", "outline"])
@pytest.mark.parametrize("word", BANNED)
def test_templates_contain_no_stack_specific_words(name: str, word: str) -> None:
    pattern = re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE)
    assert pattern.search(shipped(name)) is None


# --- the outline template parses into every line format ----------------------


def parsed() -> Memo:
    return LiveMemoReader().parse(shipped("outline"))


def test_outline_has_a_build_order_entry_with_no_dependencies() -> None:
    assert any(entry.depends == () for entry in parsed().build_order)


def test_outline_has_a_build_order_entry_with_a_dependency_list() -> None:
    assert any(len(entry.depends) >= 1 for entry in parsed().build_order)


def test_outline_has_a_module_block_with_every_key() -> None:
    modules = parsed().modules
    assert modules
    assert any(m.part for m in modules)
    assert any(m.depends for m in modules)
    assert any(m.legacy_files for m in modules)
    assert any(m.legacy_tests for m in modules)
    assert any(m.callers for m in modules)
    assert any(m.reference_tests for m in modules)
    assert any(m.changes for m in modules)
    assert any(m.contract_changes for m in modules)


def test_outline_files_line_shows_units_split_on_a_bar() -> None:
    assert any(len(m.units) >= 2 and all(u for u in m.units) for m in parsed().modules)


def test_outline_has_a_module_with_no_dependencies() -> None:
    assert any(m.depends == () for m in parsed().modules)


def test_outline_has_a_journey_with_a_part() -> None:
    journeys = parsed().journeys
    assert journeys
    assert any(j.part for j in journeys)


def test_outline_has_an_interface_block_with_every_key() -> None:
    interfaces = parsed().interfaces
    assert interfaces
    assert any(
        i.file
        and i.format
        and i.provider.module
        and i.provider.part
        and i.consumers
        and i.contract_changes
        for i in interfaces
    )


def test_outline_constraints_list_parts() -> None:
    assert len(parsed().parts) >= 1


def test_outline_has_unmapped_reference_tests() -> None:
    assert len(parsed().unmapped_reference_tests) >= 1


def test_outline_has_a_legacy_code_section_with_every_key() -> None:
    legacy = parsed().legacy
    assert legacy is not None
    assert legacy.app_shell
    assert legacy.app_shell_tests
    assert legacy.legacy_folders
    assert legacy.renames


# --- the backlog template follows the idea-file format -----------------------


def test_backlog_template_has_at_least_one_example_idea() -> None:
    text = shipped("backlog")
    sections = re.findall(r"^## \S.*$", text, flags=re.MULTILINE)
    items = re.findall(r"^- [^:\n]+: \S.*$", text, flags=re.MULTILINE)
    assert sections or items


def test_backlog_template_idea_sections_have_a_title_and_body() -> None:
    text = shipped("backlog")
    body = re.search(r"^## \S.*\n+\s*\S", text, flags=re.MULTILINE)
    items = re.search(r"^- [^:\n]+: \S", text, flags=re.MULTILINE)
    assert body or items
