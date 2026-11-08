"""Tests for `bull.Modules.memo.parser` (LiveMemoReader.parse and section_items)."""

from __future__ import annotations

import pytest

from bull.Modules.memo.parser import LiveMemoReader

FENCE = "```"


def _line_of(text: str, needle: str) -> int:
    for number, line in enumerate(text.splitlines(), start=1):
        if needle in line:
            return number
    raise AssertionError(f"{needle!r} not in text")


def test_build_order_parses_none_and_dependency_lists_with_lines() -> None:
    text = (
        "# Memo\n"
        "\n"
        "## Build order\n"
        "1. foundation (depends on: none)\n"
        "2. gitrepo (depends on: foundation)\n"
        "3. formats (depends on: foundation, gitrepo)\n"
    )
    memo = LiveMemoReader().parse(text)
    assert [(b.name, b.depends, b.line) for b in memo.build_order] == [
        ("foundation", (), 4),
        ("gitrepo", ("foundation",), 5),
        ("formats", ("foundation", "gitrepo"), 6),
    ]


def test_build_order_stops_at_next_section() -> None:
    text = (
        "## Build order\n"
        "1. a (depends on: none)\n"
        "\n"
        "## Modules\n"
        "2. not-a-build-line (depends on: none)\n"
    )
    memo = LiveMemoReader().parse(text)
    assert [b.name for b in memo.build_order] == ["a"]


def test_module_block_parses_every_key() -> None:
    text = (
        "## Modules\n"
        "\n"
        "### Export\n"
        "- Purpose: something\n"
        "- Part: cli\n"
        "- Depends on: Store, Config\n"
        "- Files: Contracts/__init__.py, mocks/__init__.py | a.py, b.py | c.py\n"
        "- Legacy files: Old.py, Older.py\n"
        "- Legacy tests: test_old.py\n"
        "- Callers to repoint: main.py, app.py\n"
        "- Reference tests: v1/test_a.py::test_x, v1/test_b.py::test_y\n"
        "- Changes (dark-mode): a.py, c.py\n"
        "- Contract changes (dark-mode): adds `theme()` to the protocol\n"
    )
    memo = LiveMemoReader().parse(text)
    assert len(memo.modules) == 1
    m = memo.modules[0]
    assert m.name == "Export"
    assert m.line == 3
    assert m.part == "cli"
    assert m.depends == ("Store", "Config")
    assert m.units == (
        ("Contracts/__init__.py", "mocks/__init__.py"),
        ("a.py", "b.py"),
        ("c.py",),
    )
    assert m.legacy_files == ("Old.py", "Older.py")
    assert m.legacy_tests == ("test_old.py",)
    assert m.callers == ("main.py", "app.py")
    assert m.reference_tests == ("v1/test_a.py::test_x", "v1/test_b.py::test_y")
    assert dict(m.changes) == {"dark-mode": ("a.py", "c.py")}
    assert dict(m.contract_changes) == {"dark-mode": "adds `theme()` to the protocol"}


def test_module_block_defaults_when_keys_absent() -> None:
    text = "## Modules\n### Solo\n- Files: a.py\n"
    m = LiveMemoReader().parse(text).modules[0]
    assert m.part is None
    assert m.depends == ()
    assert m.units == (("a.py",),)
    assert m.legacy_files == ()
    assert m.legacy_tests == ()
    assert m.callers == ()
    assert m.reference_tests == ()
    assert dict(m.changes) == {}
    assert dict(m.contract_changes) == {}


def test_module_without_files_line_has_no_units() -> None:
    text = "## Modules\n### Bare\n- Purpose: nothing\n"
    assert LiveMemoReader().parse(text).modules[0].units == ()


def test_depends_on_none_is_empty() -> None:
    text = "## Modules\n### A\n- Depends on: none\n- Files: a.py\n"
    assert LiveMemoReader().parse(text).modules[0].depends == ()


def test_reference_tests_none_is_empty() -> None:
    text = "## Modules\n### A\n- Files: a.py\n- Reference tests: none\n"
    assert LiveMemoReader().parse(text).modules[0].reference_tests == ()


def test_files_trims_whitespace_and_drops_empty_entries() -> None:
    text = "## Modules\n### A\n- Files:  a.py ,, b.py  |  | c.py ,\n"
    assert LiveMemoReader().parse(text).modules[0].units == (
        ("a.py", "b.py"),
        ("c.py",),
    )


def test_multiple_changes_slugs_are_kept_separately() -> None:
    text = (
        "## Modules\n### A\n- Files: a.py, b.py\n"
        "- Changes (one): a.py\n"
        "- Changes (two): b.py\n"
        "- Contract changes (one): first\n"
        "- Contract changes (two): second\n"
    )
    m = LiveMemoReader().parse(text).modules[0]
    assert dict(m.changes) == {"one": ("a.py",), "two": ("b.py",)}
    assert dict(m.contract_changes) == {"one": "first", "two": "second"}


def test_several_module_blocks_have_their_own_lines_and_values() -> None:
    text = "## Modules\n### One\n- Files: one.py\n\n### Two\n- Files: two.py\n"
    first, second = LiveMemoReader().parse(text).modules
    assert (first.name, first.line, first.units) == ("One", 2, (("one.py",),))
    assert (second.name, second.line, second.units) == ("Two", 5, (("two.py",),))


def test_fenced_code_block_inside_module_is_skipped() -> None:
    text = (
        "## Modules\n"
        "### A\n"
        "- Files: real.py\n"
        f"{FENCE}python\n"
        "- Files: fake.py\n"
        "- Part: ghost\n"
        "### NotAModule\n"
        f"{FENCE}\n"
        "- Depends on: Store\n"
    )
    memo = LiveMemoReader().parse(text)
    assert [m.name for m in memo.modules] == ["A"]
    m = memo.modules[0]
    assert m.units == (("real.py",),)
    assert m.part is None
    assert m.depends == ("Store",)


def test_line_numbers_are_one_based_for_module_blocks() -> None:
    text = "intro\n\n## Modules\n\n### Late\n- Files: a.py\n"
    assert LiveMemoReader().parse(text).modules[0].line == _line_of(text, "### Late")


def test_journeys_parse_number_title_and_optional_part() -> None:
    text = (
        "## User journeys\n"
        "1. **Create a thing** — the user makes one.\n"
        "   - Part: cli\n"
        "2. **Delete a thing** — the user removes one.\n"
    )
    memo = LiveMemoReader().parse(text)
    assert [(j.number, j.title, j.part) for j in memo.journeys] == [
        (1, "Create a thing", "cli"),
        (2, "Delete a thing", None),
    ]


def test_interfaces_parse_all_fields() -> None:
    text = (
        "## Interfaces\n"
        "\n"
        "### events-feed\n"
        "- File: docs/feed.json (json)\n"
        "- Provider: cli / Export\n"
        "- Consumers: web / Import, web / Viewer\n"
        "- Contract changes (v2): adds a field\n"
    )
    memo = LiveMemoReader().parse(text)
    assert len(memo.interfaces) == 1
    i = memo.interfaces[0]
    assert i.name == "events-feed"
    assert i.file == "docs/feed.json"
    assert i.format == "json"
    assert i.provider.part == "cli"
    assert i.provider.module == "Export"
    assert [(c.part, c.module) for c in i.consumers] == [
        ("web", "Import"),
        ("web", "Viewer"),
    ]
    assert dict(i.contract_changes) == {"v2": "adds a field"}


def test_parts_constraint_lists_part_names() -> None:
    text = "## Constraints\n- Stack: x\n- Parts: cli (python_cli), web (ios)\n"
    assert LiveMemoReader().parse(text).parts == ("cli", "web")


def test_parts_absent_is_empty() -> None:
    text = "## Constraints\n- Stack: python_cli (one part)\n"
    assert LiveMemoReader().parse(text).parts == ()


def test_unmapped_reference_tests_are_listed() -> None:
    text = (
        "## Unmapped reference tests\n- v1/test_a.py::test_x\n- v1/test_b.py::test_y\n"
    )
    assert LiveMemoReader().parse(text).unmapped_reference_tests == (
        "v1/test_a.py::test_x",
        "v1/test_b.py::test_y",
    )


def test_legacy_code_section_parses_every_field() -> None:
    text = (
        "## Legacy code\n"
        "- App shell: App.swift, Root.swift\n"
        "- App shell tests: AppTests.swift\n"
        "- Legacy folders: Old/, Older/\n"
        "- Renames: Export → LegacyExport, Store → LegacyStore\n"
    )
    legacy = LiveMemoReader().parse(text).legacy
    assert legacy is not None
    assert legacy.app_shell == ("App.swift", "Root.swift")
    assert legacy.app_shell_tests == ("AppTests.swift",)
    assert legacy.legacy_folders == ("Old/", "Older/")
    assert dict(legacy.renames) == {
        "Export": "LegacyExport",
        "Store": "LegacyStore",
    }


def test_missing_sections_give_empty_memo() -> None:
    memo = LiveMemoReader().parse("# Just a title\n\nSome prose.\n")
    assert memo.build_order == ()
    assert memo.modules == ()
    assert memo.journeys == ()
    assert memo.interfaces == ()
    assert memo.parts == ()
    assert memo.unmapped_reference_tests == ()
    assert memo.legacy is None


def test_empty_text_gives_empty_memo() -> None:
    memo = LiveMemoReader().parse("")
    assert memo.modules == ()
    assert memo.legacy is None


def test_section_items_returns_top_level_items() -> None:
    text = "## Later features\n- First idea\n- Second idea\n\n## Other\n- nope\n"
    assert LiveMemoReader().section_items(text, "Later features") == [
        "First idea",
        "Second idea",
    ]


def test_section_items_joins_continuation_lines() -> None:
    text = "## Notes\n- First line\n  continues here\n  and here\n- Second\n"
    items = LiveMemoReader().section_items(text, "Notes")
    assert len(items) == 2
    assert items[0].split() == ["First", "line", "continues", "here", "and", "here"]
    assert items[1] == "Second"


def test_section_items_excludes_nested_items() -> None:
    text = "## Notes\n- Top\n  - nested\n    - deeper\n- Another\n"
    items = LiveMemoReader().section_items(text, "Notes")
    assert len(items) == 2
    assert items[0].startswith("Top")
    assert items[1] == "Another"


def test_section_items_missing_heading_is_empty_list() -> None:
    assert LiveMemoReader().section_items("## A\n- x\n", "B") == []


@pytest.mark.parametrize("text", ["", "no headings\n- not under any section\n"])
def test_section_items_on_text_without_headings_is_empty(text: str) -> None:
    assert LiveMemoReader().section_items(text, "Anything") == []


def test_section_items_empty_section_is_empty_list() -> None:
    assert LiveMemoReader().section_items("## A\n\n## B\n- x\n", "A") == []
