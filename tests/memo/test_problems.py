"""Tests for `bull.Modules.memo.problems`, reached through `LiveMemoReader.problems`."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from bull.Modules.memo.Contracts import (
    BuildEntry,
    InterfaceEntry,
    Journey,
    Memo,
    MemoProblem,
    ModuleEntry,
    SideRef,
)
from bull.Modules.memo.parser import LiveMemoReader


def _module(
    name: str,
    line: int,
    *,
    part: str | None = None,
    depends: tuple[str, ...] = (),
    units: tuple[tuple[str, ...], ...] = (("a.py",),),
    changes: Mapping[str, tuple[str, ...]] | None = None,
) -> ModuleEntry:
    return ModuleEntry(
        name=name,
        line=line,
        part=part,
        depends=depends,
        units=units,
        legacy_files=(),
        legacy_tests=(),
        callers=(),
        reference_tests=(),
        changes=changes or {},
        contract_changes={},
    )


def _memo(
    build: Sequence[BuildEntry],
    modules: Sequence[ModuleEntry],
    *,
    journeys: Sequence[Journey] = (),
    interfaces: Sequence[InterfaceEntry] = (),
    parts: Sequence[str] = (),
) -> Memo:
    return Memo(
        build_order=tuple(build),
        modules=tuple(modules),
        journeys=tuple(journeys),
        interfaces=tuple(interfaces),
        parts=tuple(parts),
        unmapped_reference_tests=(),
        legacy=None,
    )


def _problems(
    memo: Memo, known_parts: Sequence[str] = (), max_files: int = 5
) -> list[MemoProblem]:
    return LiveMemoReader().problems(memo, known_parts, max_files)


def _clean() -> Memo:
    return _memo(
        [BuildEntry("Store", (), 2), BuildEntry("Counter", ("Store",), 3)],
        [
            _module("Store", 10),
            _module("Counter", 20, depends=("Store",)),
        ],
    )


def _lines(problems: list[MemoProblem]) -> set[int]:
    return {p.line for p in problems}


def test_clean_memo_has_no_problems() -> None:
    assert _problems(_clean()) == []


def test_empty_memo_has_no_problems() -> None:
    assert _problems(_memo([], [])) == []


def test_build_order_module_without_block_is_reported_on_its_build_line() -> None:
    memo = _memo(
        [BuildEntry("Store", (), 2), BuildEntry("Ghost", ("Store",), 3)],
        [_module("Store", 10)],
    )
    problems = _problems(memo)
    assert len(problems) == 1
    assert problems[0].line == 3
    assert "Ghost" in problems[0].message


def test_block_without_build_order_entry_is_reported_on_its_block_line() -> None:
    memo = _memo(
        [BuildEntry("Store", (), 2)],
        [_module("Store", 10), _module("Extra", 20)],
    )
    problems = _problems(memo)
    assert len(problems) == 1
    assert problems[0].line == 20
    assert "Extra" in problems[0].message


def test_duplicate_module_names_ignoring_case_are_reported() -> None:
    memo = _memo(
        [BuildEntry("Store", (), 2)],
        [_module("Store", 10), _module("store", 20)],
    )
    problems = _problems(memo)
    assert problems
    assert 20 in _lines(problems)
    assert any("uplicate" in p.message for p in problems)


def test_duplicate_build_order_names_ignoring_case_are_reported() -> None:
    memo = _memo(
        [BuildEntry("Store", (), 2), BuildEntry("STORE", (), 3)],
        [_module("Store", 10)],
    )
    problems = _problems(memo)
    assert 3 in _lines(problems)
    assert any("uplicate" in p.message for p in problems)


def test_unknown_dependency_is_reported() -> None:
    memo = _memo(
        [BuildEntry("Store", (), 2), BuildEntry("Counter", ("Nowhere",), 3)],
        [_module("Store", 10), _module("Counter", 20, depends=("Nowhere",))],
    )
    problems = [p for p in _problems(memo) if "Nowhere" in p.message]
    assert problems
    assert _lines(problems) <= {3, 20}


def test_dependency_not_earlier_in_build_order_is_reported() -> None:
    memo = _memo(
        [BuildEntry("Counter", ("Store",), 2), BuildEntry("Store", (), 3)],
        [_module("Counter", 10, depends=("Store",)), _module("Store", 20)],
    )
    problems = [p for p in _problems(memo) if "Store" in p.message]
    assert problems
    assert _lines(problems) <= {2, 10}


def test_self_dependency_is_reported() -> None:
    memo = _memo(
        [BuildEntry("Store", ("Store",), 2)],
        [_module("Store", 10, depends=("Store",))],
    )
    assert _problems(memo)


def test_block_depends_on_differing_from_build_order_is_reported_on_block() -> None:
    memo = _memo(
        [
            BuildEntry("A", (), 2),
            BuildEntry("B", (), 3),
            BuildEntry("C", ("A",), 4),
        ],
        [
            _module("A", 10),
            _module("B", 20),
            _module("C", 30, depends=("A", "B")),
        ],
    )
    problems = _problems(memo)
    assert len(problems) == 1
    assert problems[0].line == 30


def test_module_without_files_is_reported_on_its_block() -> None:
    memo = _memo(
        [BuildEntry("Store", (), 2), BuildEntry("Counter", ("Store",), 3)],
        [_module("Store", 10), _module("Counter", 20, depends=("Store",), units=())],
    )
    problems = _problems(memo)
    assert len(problems) == 1
    assert problems[0].line == 20
    assert "Counter" in problems[0].message


def test_unit_over_max_files_is_reported_on_its_block() -> None:
    memo = _memo(
        [BuildEntry("Store", (), 2)],
        [_module("Store", 10, units=(("a.py", "b.py", "c.py"),))],
    )
    problems = _problems(memo, max_files=2)
    assert len(problems) == 1
    assert problems[0].line == 10


def test_unit_at_exactly_max_files_is_fine() -> None:
    memo = _memo(
        [BuildEntry("Store", (), 2)],
        [_module("Store", 10, units=(("a.py", "b.py"),))],
    )
    assert _problems(memo, max_files=2) == []


def test_only_the_oversized_unit_among_several_triggers() -> None:
    memo = _memo(
        [BuildEntry("Store", (), 2)],
        [_module("Store", 10, units=(("a.py",), ("b.py", "c.py", "d.py")))],
    )
    assert len(_problems(memo, max_files=2)) == 1


def test_module_part_not_in_known_parts_is_reported() -> None:
    memo = _memo(
        [BuildEntry("Store", (), 2)],
        [_module("Store", 10, part="mobile")],
        parts=("cli",),
    )
    problems = _problems(memo, known_parts=["cli"])
    assert len(problems) == 1
    assert problems[0].line == 10
    assert "mobile" in problems[0].message


def test_journey_part_not_in_known_parts_is_reported() -> None:
    memo = _memo(
        [BuildEntry("Store", (), 2)],
        [_module("Store", 10, part="cli")],
        journeys=[Journey(1, "Do it", "mobile")],
        parts=("cli",),
    )
    problems = _problems(memo, known_parts=["cli"])
    assert len(problems) == 1
    assert "mobile" in problems[0].message


def test_journey_with_known_part_is_fine() -> None:
    memo = _memo(
        [BuildEntry("Store", (), 2)],
        [_module("Store", 10, part="cli")],
        journeys=[Journey(1, "Do it", "cli")],
        parts=("cli",),
    )
    assert _problems(memo, known_parts=["cli"]) == []


def test_module_without_part_is_reported_when_several_parts() -> None:
    memo = _memo(
        [BuildEntry("Store", (), 2)],
        [_module("Store", 10)],
        parts=("cli", "web"),
    )
    problems = _problems(memo, known_parts=["cli", "web"])
    assert len(problems) == 1
    assert problems[0].line == 10


def test_module_without_part_is_fine_with_one_part() -> None:
    memo = _memo(
        [BuildEntry("Store", (), 2)],
        [_module("Store", 10)],
        parts=("cli",),
    )
    assert _problems(memo, known_parts=["cli"]) == []


def test_cross_part_dependency_is_reported_with_exact_message() -> None:
    memo = _memo(
        [BuildEntry("Export", (), 2), BuildEntry("Import", ("Export",), 3)],
        [
            _module("Export", 10, part="cli"),
            _module("Import", 20, part="web", depends=("Export",)),
        ],
        parts=("cli", "web"),
    )
    problems = _problems(memo, known_parts=["cli", "web"])
    assert len(problems) == 1
    assert problems[0].message == (
        "`web / Import` depends on `cli / Export` in another part; use an interface"
    )
    assert problems[0].line in {3, 20}


def test_same_part_dependency_is_fine() -> None:
    memo = _memo(
        [BuildEntry("Export", (), 2), BuildEntry("Import", ("Export",), 3)],
        [
            _module("Export", 10, part="cli"),
            _module("Import", 20, part="cli", depends=("Export",)),
        ],
        parts=("cli", "web"),
    )
    assert _problems(memo, known_parts=["cli", "web"]) == []


def _iface(provider: SideRef, consumers: tuple[SideRef, ...]) -> InterfaceEntry:
    return InterfaceEntry(
        name="feed",
        file="docs/feed.json",
        format="json",
        provider=provider,
        consumers=consumers,
        contract_changes={},
    )


def _two_part_memo(iface: InterfaceEntry) -> Memo:
    return _memo(
        [BuildEntry("Export", (), 2), BuildEntry("Import", (), 3)],
        [_module("Export", 10, part="cli"), _module("Import", 20, part="web")],
        interfaces=[iface],
        parts=("cli", "web"),
    )


def test_valid_interface_is_fine() -> None:
    memo = _two_part_memo(_iface(SideRef("cli", "Export"), (SideRef("web", "Import"),)))
    assert _problems(memo, known_parts=["cli", "web"]) == []


def test_interface_provider_unknown_module_is_reported() -> None:
    memo = _two_part_memo(
        _iface(SideRef("cli", "Missing"), (SideRef("web", "Import"),))
    )
    problems = _problems(memo, known_parts=["cli", "web"])
    assert len(problems) == 1
    assert "Missing" in problems[0].message


def test_interface_consumer_unknown_module_is_reported() -> None:
    memo = _two_part_memo(
        _iface(SideRef("cli", "Export"), (SideRef("web", "Missing"),))
    )
    problems = _problems(memo, known_parts=["cli", "web"])
    assert len(problems) == 1
    assert "Missing" in problems[0].message


def test_interface_provider_unknown_part_is_reported() -> None:
    memo = _two_part_memo(
        _iface(SideRef("mobile", "Export"), (SideRef("web", "Import"),))
    )
    problems = _problems(memo, known_parts=["cli", "web"])
    assert problems
    assert any("mobile" in p.message for p in problems)


def test_interface_consumer_unknown_part_is_reported() -> None:
    memo = _two_part_memo(
        _iface(SideRef("cli", "Export"), (SideRef("mobile", "Import"),))
    )
    problems = _problems(memo, known_parts=["cli", "web"])
    assert problems
    assert any("mobile" in p.message for p in problems)


def test_changes_naming_file_not_in_files_is_reported() -> None:
    memo = _memo(
        [BuildEntry("Store", (), 2)],
        [
            _module(
                "Store",
                10,
                units=(("a.py",), ("b.py",)),
                changes={"tweak": ("a.py", "z.py")},
            )
        ],
    )
    problems = _problems(memo)
    assert len(problems) == 1
    assert problems[0].line == 10
    assert "z.py" in problems[0].message


def test_changes_naming_only_listed_files_is_fine() -> None:
    memo = _memo(
        [BuildEntry("Store", (), 2)],
        [_module("Store", 10, units=(("a.py",), ("b.py",)), changes={"t": ("b.py",)})],
    )
    assert _problems(memo) == []


def test_parsed_memo_with_missing_block_reports_build_order_line() -> None:
    reader = LiveMemoReader()
    text = (
        "## Build order\n"
        "1. A (depends on: none)\n"
        "2. B (depends on: A)\n"
        "\n"
        "## Modules\n"
        "### A\n"
        "- Files: a.py\n"
    )
    problems = reader.problems(reader.parse(text), [], 5)
    assert [(p.line, "B" in p.message) for p in problems] == [(3, True)]
