"""Tests for the status contract: enums, frozen models, StatusError and the Protocols."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from typing import Any

import pytest

from bull.Modules.foundation.Contracts import BullError
from bull.Modules.status.Contracts import (
    ActiveFeature,
    Approval,
    Mode,
    ModuleState,
    ModuleStatus,
    NextStep,
    Pause,
    Plan,
    PlanItem,
    Progress,
    Refs,
    ScanRecord,
    Status,
    StatusError,
    StatusStore,
    Track,
    Unit,
    UnitKind,
    UnitState,
    Waiting,
)

T = datetime(2026, 1, 1, tzinfo=UTC)


def _names(cls: type) -> list[str]:
    return [f.name for f in dataclasses.fields(cls)]


@pytest.mark.parametrize(
    ("enum", "values"),
    [
        (Mode, {"APP": "app", "FEATURE": "feature", "ADOPT": "adopt"}),
        (
            UnitState,
            {
                "PENDING": "pending",
                "TESTS": "tests",
                "CODE": "code",
                "DONE": "done",
                "BLOCKED": "blocked",
            },
        ),
        (
            ModuleState,
            {
                "PENDING": "pending",
                "IN_PROGRESS": "in_progress",
                "DONE": "done",
                "BLOCKED": "blocked",
            },
        ),
        (UnitKind, {"CODE": "code", "SWITCH_OVER": "switch-over"}),
    ],
)
def test_enum_members_carry_their_status_json_values(
    enum: Any, values: dict[str, str]
) -> None:
    assert {m.name: m.value for m in enum} == values


def test_status_error_is_a_bull_error_with_message_and_fix() -> None:
    err = StatusError("bad", "do this")
    assert isinstance(err, BullError)
    assert err.message == "bad"
    assert err.fix == "do this"


@pytest.mark.parametrize(
    ("cls", "fields"),
    [
        (Unit, ["number", "files", "kind", "state", "attempts"]),
        (ScanRecord, ["time", "covered", "missed", "contradicts", "not_in_spec"]),
        (
            ModuleStatus,
            [
                "name",
                "part",
                "depends",
                "state",
                "units",
                "reference_tests",
                "scan",
            ],
        ),
        (Track, ["stage", "checkpoints"]),
        (Pause, ["reason", "since", "unit"]),
        (Waiting, ["module", "what", "since"]),
        (Approval, ["module", "note", "time"]),
        (PlanItem, ["name", "done"]),
        (Plan, ["label", "items"]),
        (ActiveFeature, ["slug", "track", "applied_contracts"]),
        (
            Status,
            [
                "format",
                "app",
                "modules",
                "pause",
                "waiting",
                "approvals",
                "plan",
                "feature",
                "adoption",
            ],
        ),
        (NextStep, ["text", "mode"]),
    ],
)
def test_model_fields_are_in_the_documented_order(cls: type, fields: list[str]) -> None:
    assert dataclasses.is_dataclass(cls)
    assert _names(cls) == fields


@pytest.mark.parametrize(
    "instance",
    [
        Unit(1, ("a.py",), UnitKind.CODE, UnitState.PENDING, 1),
        ScanRecord(T, 1, 2, 3, 4),
        Track(1, ()),
        Pause("usage", T, None),
        Waiting("M", "x", T),
        Approval("M", "ok", T),
        PlanItem("a", False),
        Plan("p", ()),
        ActiveFeature("f", Track(1, ()), ()),
        NextStep("go", Mode.APP),
    ],
)
def test_models_are_frozen(instance: Any) -> None:
    field = dataclasses.fields(instance)[0].name
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(instance, field, None)


def test_status_and_module_status_are_frozen() -> None:
    module = ModuleStatus("M", "app", (), ModuleState.PENDING, (), False, None)
    status = Status(1, Track(0, ()), (module,), None, None, (), None, None, None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        status.format = 2  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        module.name = "N"  # type: ignore[misc]


def test_equal_models_compare_equal() -> None:
    a = Unit(1, ("a.py",), UnitKind.CODE, UnitState.DONE, 2)
    b = Unit(1, ("a.py",), UnitKind.CODE, UnitState.DONE, 2)
    assert a == b


def test_optional_status_parts_can_be_none() -> None:
    status = Status(1, Track(0, ()), (), None, None, (), None, None, None)
    assert status.pause is None
    assert status.waiting is None
    assert status.plan is None
    assert status.feature is None
    assert status.adoption is None


@pytest.mark.parametrize(
    ("proto", "members"),
    [
        (
            StatusStore,
            [
                "load",
                "create",
                "mode",
                "set_stage",
                "checkpoint",
                "init_modules",
                "set_module",
                "set_unit",
                "attempt",
                "unblock",
                "pause",
                "resume",
                "wait",
                "approve",
                "take_approval",
                "record_scan",
                "set_plan",
                "tick",
                "clear_plan",
                "start_feature",
                "end_feature",
                "mark_contract_applied",
                "reopen",
                "add_modules",
                "start_adoption",
                "finish_adoption",
                "abandon_adoption",
            ],
        ),
        (Refs, ["trunk", "base", "module_branch", "tag", "module_for_branch"]),
        (Progress, ["next_step", "summary", "as_json", "tags"]),
    ],
)
def test_protocol_declares_its_members(proto: type, members: list[str]) -> None:
    for member in members:
        assert callable(getattr(proto, member)), member
