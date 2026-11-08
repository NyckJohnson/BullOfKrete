"""Tests for the memo mocks other modules' tests rely on."""

from __future__ import annotations

import pytest

from bull.Modules.foundation.Contracts import BullError
from bull.Modules.memo.Contracts import (
    Memo,
    MemoProblem,
    MemoReader,
    Templates,
)
from bull.Modules.memo.mocks import MockMemoReader, MockTemplates, sample_memo


def test_sample_memo_is_a_memo() -> None:
    assert isinstance(sample_memo(), Memo)


def test_sample_memo_lists_store_then_counter_in_build_order() -> None:
    memo = sample_memo()
    assert [b.name for b in memo.build_order] == ["Store", "Counter"]
    assert [b.depends for b in memo.build_order] == [(), ("Store",)]


def test_sample_memo_modules_match_build_order_and_dependencies() -> None:
    memo = sample_memo()
    assert [m.name for m in memo.modules] == ["Store", "Counter"]
    assert memo.modules[0].depends == ()
    assert memo.modules[1].depends == ("Store",)


def test_sample_memo_modules_have_files_and_positive_lines() -> None:
    for module in sample_memo().modules:
        assert module.units
        assert all(unit for unit in module.units)
        assert module.line > 0


def test_sample_memo_is_single_part_without_legacy_or_interfaces() -> None:
    memo = sample_memo()
    assert memo.parts == ()
    assert memo.interfaces == ()
    assert memo.legacy is None
    assert all(m.part is None for m in memo.modules)


def test_mock_reader_satisfies_the_protocol() -> None:
    reader: MemoReader = MockMemoReader()
    assert isinstance(reader.parse("x"), Memo)


def test_mock_reader_parse_returns_its_memo_for_any_text() -> None:
    reader = MockMemoReader()
    assert reader.parse("anything") is reader.memo
    assert reader.parse("") is reader.memo


def test_mock_reader_parse_returns_replaced_memo() -> None:
    reader = MockMemoReader()
    other = Memo((), (), (), (), (), (), None)
    reader.memo = other
    assert reader.parse("x") is other


def test_mock_reader_section_items_missing_heading_is_empty() -> None:
    assert MockMemoReader().section_items("text", "No such heading") == []


def test_mock_reader_section_items_returns_configured_items() -> None:
    reader = MockMemoReader()
    reader.items["Ideas"] = ["One", "Two"]
    assert reader.section_items("t", "Ideas") == ["One", "Two"]


def test_mock_reader_section_items_returns_a_copy() -> None:
    reader = MockMemoReader()
    reader.items["Ideas"] = ["One"]
    reader.section_items("t", "Ideas").append("junk")
    assert reader.section_items("t", "Ideas") == ["One"]


def test_mock_reader_problems_default_is_empty() -> None:
    reader = MockMemoReader()
    assert reader.problems(reader.memo, [], 5) == []


def test_mock_reader_problems_returns_configured_problems() -> None:
    reader = MockMemoReader()
    reader.found_problems = [MemoProblem(3, "bad")]
    assert reader.problems(reader.memo, ["cli"], 5) == [MemoProblem(3, "bad")]


def test_mock_reader_problems_returns_a_copy() -> None:
    reader = MockMemoReader()
    reader.found_problems = [MemoProblem(3, "bad")]
    reader.problems(reader.memo, [], 5).clear()
    assert reader.found_problems == [MemoProblem(3, "bad")]


def test_mock_reader_records_calls_in_order() -> None:
    reader = MockMemoReader()
    reader.parse("t")
    reader.section_items("t", "H")
    reader.problems(reader.memo, ["a", "b"], 4)
    assert [c[0] for c in reader.calls] == ["parse", "section_items", "problems"]
    assert reader.calls[0][1] == ("t",)
    assert reader.calls[1][1] == ("t", "H")
    assert reader.calls[2][1] == (reader.memo, ("a", "b"), 4)


def test_mock_templates_satisfies_the_protocol() -> None:
    templates: Templates = MockTemplates()
    assert templates.names()


def test_mock_templates_names_are_outline_and_backlog() -> None:
    assert MockTemplates().names() == ["backlog", "outline"]


def test_mock_templates_text_returns_nonempty_text_per_name() -> None:
    templates = MockTemplates()
    for name in templates.names():
        assert templates.text(name).strip()


def test_mock_templates_outline_and_backlog_differ() -> None:
    templates = MockTemplates()
    assert templates.text("outline") != templates.text("backlog")


def test_mock_templates_text_returns_configured_text() -> None:
    templates = MockTemplates()
    templates.texts["outline"] = "custom"
    assert templates.text("outline") == "custom"


def test_mock_templates_unknown_name_raises_bull_error_listing_names() -> None:
    with pytest.raises(BullError) as excinfo:
        MockTemplates().text("nope")
    text = excinfo.value.message + excinfo.value.fix
    assert "backlog" in text
    assert "outline" in text


def test_mock_templates_records_calls() -> None:
    templates = MockTemplates()
    templates.names()
    templates.text("outline")
    assert templates.calls == [("names", ()), ("text", ("outline",))]
