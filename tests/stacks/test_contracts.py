"""Tests for the stacks contract: enums, errors, dataclasses and protocol shapes."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import get_type_hints

import pytest

from bull.Modules.foundation.Contracts import BullError
from bull.Modules.settings.Contracts import StackLayer
from bull.Modules.stacks import Contracts as C
from bull.Modules.stacks.Contracts import (
    CheckItem,
    CoverageData,
    Detection,
    GateCommands,
    Issue,
    IssueLevel,
    Maturity,
    OptionalReaders,
    Requirement,
    Role,
    RunCommands,
    Stack,
    StackError,
    StackKind,
    StackManifest,
    TestRun,
)


@pytest.mark.parametrize(
    ("enum", "values"),
    [
        (StackKind, {"APP": "app", "SERVICE": "service", "TOOL": "tool"}),
        (
            Maturity,
            {"EXPERIMENTAL": "experimental", "VERIFIED": "verified", "TEST": "test"},
        ),
        (IssueLevel, {"BLOCK": "block", "FIX": "fix", "NOTE": "note"}),
        (Role, {"PROVIDER": "provider", "CONSUMER": "consumer"}),
    ],
)
def test_enum_members_have_the_specified_values(
    enum: type, values: dict[str, str]
) -> None:
    assert {m.name: m.value for m in enum} == values


def test_stack_error_is_a_bull_error() -> None:
    assert issubclass(StackError, BullError)
    with pytest.raises(BullError):
        raise StackError("nope")


def _field_names(cls: type) -> list[str]:
    return [f.name for f in dataclasses.fields(cls)]


@pytest.mark.parametrize(
    ("cls", "names"),
    [
        (Requirement, ["tool", "hint"]),
        (
            GateCommands,
            [
                "preflight",
                "setup",
                "build_test",
                "build_test_fast",
                "lint",
                "rerun_failed",
                "journeys",
            ],
        ),
        (RunCommands, ["start", "ready", "stop", "ready_timeout"]),
        (
            StackManifest,
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
                "settings",
                "gates",
                "run",
                "interface_formats",
                "commands",
            ],
        ),
        (CheckItem, ["ok", "item", "fix"]),
        (TestRun, ["count", "failed"]),
        (CoverageData, ["uncovered", "no_data"]),
        (Issue, ["level", "item", "fix"]),
        (Detection, ["confidence", "summary", "settings", "issues"]),
        (
            OptionalReaders,
            ["detect", "inventory", "legacy_declarations", "interface_check"],
        ),
        (Stack, ["manifest", "home", "builtin", "readers", "optional"]),
    ],
)
def test_dataclass_fields_match_the_memo_in_order(cls: type, names: list[str]) -> None:
    assert _field_names(cls) == names


@pytest.mark.parametrize(
    "cls",
    [
        Requirement,
        GateCommands,
        RunCommands,
        StackManifest,
        CheckItem,
        TestRun,
        CoverageData,
        Issue,
        Detection,
        OptionalReaders,
        Stack,
    ],
)
def test_dataclasses_are_frozen(cls: type) -> None:
    assert cls.__dataclass_params__.frozen  # type: ignore[attr-defined]


def test_requirement_is_immutable() -> None:
    req = Requirement("uv", "https://example.com")
    with pytest.raises(dataclasses.FrozenInstanceError):
        req.tool = "other"  # type: ignore[misc]


def test_check_item_is_immutable_and_comparable() -> None:
    item = CheckItem(True, "git on PATH", "")
    with pytest.raises(dataclasses.FrozenInstanceError):
        item.ok = False  # type: ignore[misc]
    assert item == CheckItem(True, "git on PATH", "")


def test_test_run_holds_count_and_failed_ids() -> None:
    run = TestRun(count=3, failed=("a", "b"))
    assert run.count == 3
    assert run.failed == ("a", "b")


def test_coverage_data_holds_uncovered_lines_and_no_data_files() -> None:
    data = CoverageData(uncovered={Path("a.py"): (1, 2)}, no_data=(Path("b.py"),))
    assert data.uncovered[Path("a.py")] == (1, 2)
    assert data.no_data == (Path("b.py"),)


def test_gate_commands_journeys_may_be_none() -> None:
    gates = GateCommands(("a",), ("b",), ("c",), ("d",), ("e",), ("f",), None)
    assert gates.journeys is None


def test_run_commands_is_immutable() -> None:
    run = RunCommands(("s",), ("r",), ("x",), 30.0)
    assert run.ready_timeout == 30.0
    with pytest.raises(dataclasses.FrozenInstanceError):
        run.ready_timeout = 1.0  # type: ignore[misc]


def test_detection_and_issue_hold_their_values() -> None:
    issue = Issue(IssueLevel.BLOCK, "no setup", "run setup")
    det = Detection(0.5, "looks like python", {"source_dir": "src"}, (issue,))
    assert det.issues[0].level is IssueLevel.BLOCK
    assert det.confidence == 0.5
    assert det.settings["source_dir"] == "src"


def test_manifest_is_immutable() -> None:
    from bull.Modules.stacks.mocks import sample_manifest

    manifest = sample_manifest()
    assert isinstance(manifest.settings, StackLayer)
    with pytest.raises(dataclasses.FrozenInstanceError):
        manifest.name = "other"  # type: ignore[misc]


def _protocol_methods(proto: type) -> set[str]:
    return {
        n for n in vars(proto) if not n.startswith("_") and callable(getattr(proto, n))
    }


def test_stack_readers_protocol_declares_the_four_required_functions() -> None:
    assert _protocol_methods(C.StackReaders) == {
        "contract_declarations",
        "test_results",
        "uncovered",
        "check",
    }


def test_stack_registry_protocol_declares_its_operations() -> None:
    assert _protocol_methods(C.StackRegistry) == {
        "all",
        "get",
        "load_path",
        "install",
    }


def test_stack_ops_protocol_declares_its_operations() -> None:
    assert _protocol_methods(C.StackOps) == {
        "select",
        "rules",
        "setup_guide",
        "check",
        "run_command",
    }


def test_registry_all_defaults_include_test_to_false() -> None:
    import inspect

    sig = inspect.signature(C.StackRegistry.all)
    assert sig.parameters["include_test"].default is False


def test_ops_optional_arguments_default_to_none() -> None:
    import inspect

    assert (
        inspect.signature(C.StackOps.setup_guide).parameters["section"].default is None
    )
    assert inspect.signature(C.StackOps.check).parameters["part"].default is None
    assert inspect.signature(C.StackOps.run_command).parameters["part"].default is None


def test_protocol_return_annotations_name_the_memo_types() -> None:
    assert "Stack" in str(get_type_hints(C.StackRegistry.get)["return"])
    assert get_type_hints(C.StackOps.rules)["return"] is str
    assert get_type_hints(C.StackOps.run_command)["return"] is int
