"""Tests for the memo contract types."""

from __future__ import annotations

import dataclasses
import typing

import pytest

from bull.Modules.memo.Contracts import (
    BuildEntry,
    InterfaceEntry,
    Journey,
    LegacySection,
    Memo,
    MemoProblem,
    MemoReader,
    ModuleEntry,
    SideRef,
    Templates,
)

_FIELDS: dict[type, list[str]] = {
    ModuleEntry: [
        "name",
        "line",
        "part",
        "depends",
        "units",
        "legacy_files",
        "legacy_tests",
        "callers",
        "reference_tests",
        "changes",
        "contract_changes",
    ],
    BuildEntry: ["name", "depends", "line"],
    Journey: ["number", "title", "part"],
    SideRef: ["part", "module"],
    InterfaceEntry: [
        "name",
        "file",
        "format",
        "provider",
        "consumers",
        "contract_changes",
    ],
    LegacySection: ["app_shell", "app_shell_tests", "legacy_folders", "renames"],
    Memo: [
        "build_order",
        "modules",
        "journeys",
        "interfaces",
        "parts",
        "unmapped_reference_tests",
        "legacy",
        "parse_problems",
    ],
    MemoProblem: ["line", "message"],
}


@pytest.mark.parametrize("cls", list(_FIELDS))
def test_dataclass_has_exactly_the_specified_fields_in_order(cls: type) -> None:
    assert [f.name for f in dataclasses.fields(cls)] == _FIELDS[cls]


@pytest.mark.parametrize("cls", list(_FIELDS))
def test_dataclass_is_frozen(cls: type) -> None:
    assert cls.__dataclass_params__.frozen  # type: ignore[attr-defined]


def test_frozen_instance_rejects_assignment() -> None:
    problem = MemoProblem(3, "bad")
    with pytest.raises(dataclasses.FrozenInstanceError):
        problem.line = 4  # type: ignore[misc]


def test_memo_problem_holds_line_and_message() -> None:
    problem = MemoProblem(line=7, message="oops")
    assert (problem.line, problem.message) == (7, "oops")


def test_equal_instances_compare_equal() -> None:
    assert BuildEntry("A", (), 1) == BuildEntry("A", (), 1)
    assert SideRef("cli", "Export") != SideRef("web", "Export")


def test_journey_part_may_be_none() -> None:
    assert Journey(1, "Count things", None).part is None


def test_side_ref_holds_part_and_module() -> None:
    ref = SideRef(part="cli", module="Export")
    assert (ref.part, ref.module) == ("cli", "Export")


def test_module_entry_holds_all_values() -> None:
    entry = ModuleEntry(
        name="Counter",
        line=52,
        part="cli",
        depends=("Store",),
        units=(("a.py", "b.py"), ("c.py",)),
        legacy_files=("old.py",),
        legacy_tests=("test_old.py",),
        callers=("main.py",),
        reference_tests=("t.py::x",),
        changes={"slug": ("a.py",)},
        contract_changes={"slug": "adds a field"},
    )
    assert entry.units[1] == ("c.py",)
    assert entry.changes["slug"] == ("a.py",)
    assert entry.contract_changes["slug"] == "adds a field"
    assert entry.part == "cli"


def test_interface_entry_holds_provider_and_consumers() -> None:
    entry = InterfaceEntry(
        name="events",
        file="interfaces/events.json",
        format="json-schema",
        provider=SideRef("cli", "Events"),
        consumers=(SideRef("web", "Feed"),),
        contract_changes={},
    )
    assert entry.provider.module == "Events"
    assert entry.consumers[0].part == "web"


def test_legacy_section_holds_all_values() -> None:
    legacy = LegacySection(
        app_shell=("main.py",),
        app_shell_tests=("test_main.py",),
        legacy_folders=("old/",),
        renames={"A": "LegacyA"},
    )
    assert legacy.renames == {"A": "LegacyA"}
    assert legacy.legacy_folders == ("old/",)


def test_memo_holds_all_values_and_legacy_may_be_none() -> None:
    memo = Memo(
        build_order=(),
        modules=(),
        journeys=(),
        interfaces=(),
        parts=("cli (python_cli)",),
        unmapped_reference_tests=("x",),
        legacy=None,
    )
    assert memo.legacy is None
    assert memo.parts == ("cli (python_cli)",)
    assert memo.unmapped_reference_tests == ("x",)


def test_memo_parse_problems_defaults_to_empty_tuple() -> None:
    memo = Memo(
        build_order=(),
        modules=(),
        journeys=(),
        interfaces=(),
        parts=(),
        unmapped_reference_tests=(),
        legacy=None,
    )
    assert memo.parse_problems == ()


def test_memo_parse_problems_holds_given_problems() -> None:
    problem = MemoProblem(2, "x")
    memo = Memo((), (), (), (), (), (), None, parse_problems=(problem,))
    assert memo.parse_problems == (problem,)


def test_memo_reader_protocol_declares_parse_section_items_and_problems() -> None:
    hints = typing.get_type_hints(MemoReader.problems)
    assert hints["return"] == list[MemoProblem]
    assert hints["max_files"] is int
    for name in ("parse", "section_items", "problems"):
        assert callable(getattr(MemoReader, name))


def test_templates_protocol_declares_names_and_text() -> None:
    for name in ("names", "text"):
        assert callable(getattr(Templates, name))
    assert typing.get_type_hints(Templates.text)["return"] is str
