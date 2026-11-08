"""Tests for `bull.Modules.status.model`: the status.json model."""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest

from bull.Modules.foundation.Contracts import FileFormatError
from bull.Modules.status import model
from bull.Modules.status.Contracts import (
    ActiveFeature,
    Approval,
    ModuleState,
    ModuleStatus,
    Pause,
    Plan,
    PlanItem,
    ScanRecord,
    Status,
    Track,
    Unit,
    UnitKind,
    UnitState,
    Waiting,
)
from bull.Modules.status.mocks import SAMPLE_TIME, sample_status

TIME_TEXT = "2026-11-07T12:00:00Z"


def full_status() -> Status:
    base = sample_status()
    counter = replace(
        base.modules[1],
        reference_tests=True,
        scan=ScanRecord(SAMPLE_TIME, 4, 3, 2, 1),
        units=(
            *base.modules[1].units,
            Unit(3, (), UnitKind.SWITCH_OVER, UnitState.BLOCKED, 3),
        ),
    )
    return replace(
        base,
        modules=(base.modules[0], counter),
        pause=Pause("usage", SAMPLE_TIME, "Counter unit 2"),
        waiting=Waiting("Store", "contract change", SAMPLE_TIME),
        approvals=(Approval("Store", "ok", SAMPLE_TIME),),
        plan=Plan("verify", (PlanItem("a", True), PlanItem("b", False))),
        feature=ActiveFeature("dark-mode", Track(2, ("outline-approved",)), ("Store",)),
        adoption=Track(3, ("outline-approved", "setup")),
    )


def test_round_trip_keeps_a_full_status() -> None:
    status = full_status()
    assert model.status_from_json(model.status_to_json(status)) == status


def test_round_trip_keeps_the_sample_status() -> None:
    status = sample_status()
    assert model.status_from_json(model.status_to_json(status)) == status


def test_to_json_uses_the_documented_field_names() -> None:
    data = model.status_to_json(full_status())
    assert data["format"] == 1
    assert data["kind"] == "app"
    assert data["stage"] == 5
    assert data["checkpoints"] == [
        "outline-approved",
        "setup",
        "skeleton",
        "ui-approved",
    ]
    assert data["pause"] == {
        "reason": "usage",
        "since": TIME_TEXT,
        "unit": "Counter unit 2",
    }
    assert data["waiting"] == {
        "module": "Store",
        "what": "contract change",
        "since": TIME_TEXT,
    }
    assert data["approvals"] == [{"module": "Store", "note": "ok", "time": TIME_TEXT}]
    assert data["plan"] == {
        "label": "verify",
        "items": [{"name": "a", "done": True}, {"name": "b", "done": False}],
    }
    assert data["feature"] == {
        "slug": "dark-mode",
        "stage": 2,
        "checkpoints": ["outline-approved"],
        "applied_contracts": ["Store"],
    }
    assert data["adoption"] == {
        "stage": 3,
        "checkpoints": ["outline-approved", "setup"],
    }


def test_to_json_module_and_unit_fields_use_enum_strings() -> None:
    data: Any = model.status_to_json(full_status())
    counter = data["modules"][1]
    assert counter["name"] == "Counter"
    assert counter["part"] == "app"
    assert counter["depends"] == ["Store"]
    assert counter["state"] == "in_progress"
    assert counter["reference_tests"] is True
    assert counter["scan"] == {
        "time": TIME_TEXT,
        "covered": 4,
        "missed": 3,
        "contradicts": 2,
        "not_in_spec": 1,
    }
    assert counter["units"][0] == {
        "number": 1,
        "files": ["Contracts/counter.fx", "counter.fx"],
        "kind": "code",
        "state": "tests",
        "attempts": 1,
    }
    assert counter["units"][2]["kind"] == "switch-over"
    assert counter["units"][2]["state"] == "blocked"


def test_to_json_writes_null_for_absent_parts() -> None:
    data = model.status_to_json(sample_status())
    for key in ("pause", "waiting", "plan", "feature", "adoption"):
        assert data[key] is None
    assert data["approvals"] == []
    modules: Any = data["modules"]
    assert modules[0]["scan"] is None


def test_to_json_is_serialisable_json() -> None:
    assert json.loads(json.dumps(model.status_to_json(full_status())))["format"] == 1


def test_to_json_writes_times_as_utc_with_z() -> None:
    data: Any = model.status_to_json(full_status())
    assert data["pause"]["since"] == TIME_TEXT


def test_from_json_reads_times_as_utc_datetimes() -> None:
    status = model.status_from_json(model.status_to_json(full_status()))
    assert status.pause is not None
    assert status.pause.since == datetime(2026, 11, 7, 12, 0, 0, tzinfo=UTC)
    assert status.pause.since.utcoffset() is not None


def test_from_json_reads_a_new_app_status() -> None:
    data = {
        "format": 1,
        "kind": "app",
        "stage": 0,
        "checkpoints": [],
        "modules": [],
        "pause": None,
        "waiting": None,
        "approvals": [],
        "plan": None,
        "feature": None,
        "adoption": None,
    }
    status = model.status_from_json(data)
    assert status == Status(1, Track(0, ()), (), None, None, (), None, None, None)


def mutated(path: list[str | int], value: object) -> object:
    data: Any = copy.deepcopy(model.status_to_json(full_status()))
    target = data
    for step in path[:-1]:
        target = target[step]
    if value is _DELETE:
        del target[path[-1]]
    else:
        target[path[-1]] = value
    return data


_DELETE = object()


@pytest.mark.parametrize(
    "bad",
    [
        pytest.param([], id="list"),
        pytest.param("text", id="string"),
        pytest.param(None, id="null"),
        pytest.param(3, id="number"),
    ],
)
def test_from_json_rejects_a_non_object(bad: object) -> None:
    with pytest.raises(FileFormatError):
        model.status_from_json(bad)


@pytest.mark.parametrize(
    "path",
    [
        ["format"],
        ["stage"],
        ["checkpoints"],
        ["modules"],
        ["approvals"],
        ["modules", 0, "name"],
        ["modules", 0, "units"],
        ["modules", 0, "units", 0, "number"],
        ["modules", 0, "units", 0, "attempts"],
        ["pause", "reason"],
        ["plan", "items"],
    ],
)
def test_from_json_rejects_a_missing_field(path: list[str | int]) -> None:
    with pytest.raises(FileFormatError):
        model.status_from_json(mutated(path, _DELETE))


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (["format"], "1"),
        (["stage"], "5"),
        (["checkpoints"], "setup"),
        (["checkpoints"], [1, 2]),
        (["modules"], {}),
        (["modules", 0, "name"], 7),
        (["modules", 0, "depends"], "Store"),
        (["modules", 0, "reference_tests"], "yes"),
        (["modules", 0, "units", 0, "attempts"], "1"),
        (["modules", 0, "units", 0, "files"], "a.py"),
        (["pause"], "paused"),
        (["pause", "since"], 12),
        (["plan", "items"], [{"name": "a"}]),
        (["plan", "items"], ["a"]),
        (["feature", "applied_contracts"], "Store"),
        (["adoption"], []),
        (["approvals"], [{"module": "Store"}]),
        (["modules", 1, "scan", "covered"], "4"),
    ],
)
def test_from_json_rejects_a_wrongly_typed_field(
    path: list[str | int], value: object
) -> None:
    with pytest.raises(FileFormatError):
        model.status_from_json(mutated(path, value))


@pytest.mark.parametrize(
    "path",
    [
        ["modules", 0, "state"],
        ["modules", 0, "units", 0, "state"],
        ["modules", 0, "units", 0, "kind"],
    ],
)
def test_from_json_rejects_an_unknown_enum_string(path: list[str | int]) -> None:
    with pytest.raises(FileFormatError):
        model.status_from_json(mutated(path, "sideways"))


@pytest.mark.parametrize("text", ["yesterday", "2026-13-45T00:00:00Z", ""])
def test_from_json_rejects_a_bad_time(text: str) -> None:
    with pytest.raises(FileFormatError):
        model.status_from_json(mutated(["pause", "since"], text))


def test_from_json_error_names_the_field() -> None:
    with pytest.raises(FileFormatError) as caught:
        model.status_from_json(mutated(["modules", 0, "units", 0, "attempts"], "x"))
    assert "attempts" in caught.value.message


def test_enum_values_round_trip_for_every_state() -> None:
    status = sample_status()
    module = status.modules[1]
    for module_state in ModuleState:
        for unit_state in UnitState:
            unit = replace(module.units[0], state=unit_state)
            changed = replace(
                status,
                modules=(
                    status.modules[0],
                    replace(module, state=module_state, units=(unit,)),
                ),
            )
            assert model.status_from_json(model.status_to_json(changed)) == changed


def test_module_status_type_is_preserved() -> None:
    status = model.status_from_json(model.status_to_json(full_status()))
    assert all(isinstance(m, ModuleStatus) for m in status.modules)


# --- range checks (unit 3) ---------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        ["stage"],
        ["feature", "stage"],
        ["adoption", "stage"],
    ],
)
@pytest.mark.parametrize("value", [-1, 7, 100])
def test_from_json_rejects_a_stage_outside_0_to_6(
    path: list[str | int], value: int
) -> None:
    with pytest.raises(FileFormatError) as caught:
        model.status_from_json(mutated(path, value))
    assert "stage" in caught.value.message


@pytest.mark.parametrize("value", [0, 6])
def test_from_json_accepts_the_stage_limits(value: int) -> None:
    status = model.status_from_json(mutated(["stage"], value))
    assert status.app.stage == value


@pytest.mark.parametrize("value", [0, -1])
def test_from_json_rejects_attempts_below_one(value: int) -> None:
    with pytest.raises(FileFormatError) as caught:
        model.status_from_json(mutated(["modules", 0, "units", 0, "attempts"], value))
    assert "attempts" in caught.value.message


def test_from_json_accepts_one_attempt() -> None:
    status = model.status_from_json(mutated(["modules", 0, "units", 0, "attempts"], 1))
    assert status.modules[0].units[0].attempts == 1


@pytest.mark.parametrize("value", [0, -3])
def test_from_json_rejects_a_unit_number_below_one(value: int) -> None:
    with pytest.raises(FileFormatError) as caught:
        model.status_from_json(mutated(["modules", 0, "units", 0, "number"], value))
    assert "number" in caught.value.message


@pytest.mark.parametrize("field", ["covered", "missed", "contradicts", "not_in_spec"])
def test_from_json_rejects_a_negative_scan_count(field: str) -> None:
    with pytest.raises(FileFormatError) as caught:
        model.status_from_json(mutated(["modules", 1, "scan", field], -1))
    assert field in caught.value.message


@pytest.mark.parametrize("field", ["covered", "missed", "contradicts", "not_in_spec"])
def test_from_json_accepts_a_zero_scan_count(field: str) -> None:
    status = model.status_from_json(mutated(["modules", 1, "scan", field], 0))
    scan = status.modules[1].scan
    assert scan is not None
    assert getattr(scan, field) == 0
