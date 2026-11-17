"""Tests for the stackflow contract types."""

from __future__ import annotations

import dataclasses

import pytest

from bull.Modules.stackflow.Contracts import (
    StackInstaller,
    StackRepoStatus,
    StackStage,
    StackWorkflow,
)


def _status(**overrides: object) -> StackRepoStatus:
    fields: dict[str, object] = {
        "format": 1,
        "name": "go_cli",
        "stage": StackStage.DISCUSS,
        "checkpoints": (),
        "static_pass": None,
        "test_pass": None,
    }
    fields.update(overrides)
    return StackRepoStatus(**fields)  # type: ignore[arg-type]  # overrides are dynamic test kwargs


def test_stack_stage_values_follow_the_workflow_order() -> None:
    assert [(s.name, s.value) for s in StackStage] == [
        ("DISCUSS", 1),
        ("SCAFFOLD", 2),
        ("FIXTURE", 3),
        ("GATE_CODE", 4),
        ("REVIEW", 5),
        ("ACCEPTED", 6),
    ]


def test_stack_stage_compares_as_an_integer() -> None:
    assert StackStage.DISCUSS < StackStage.ACCEPTED
    assert int(StackStage.FIXTURE) == 3
    assert StackStage(5) is StackStage.REVIEW


def test_stack_stage_rejects_an_unknown_number() -> None:
    with pytest.raises(ValueError):
        StackStage(7)
    with pytest.raises(ValueError):
        StackStage(0)


def test_repo_status_field_names() -> None:
    assert [f.name for f in dataclasses.fields(StackRepoStatus)] == [
        "format",
        "name",
        "stage",
        "checkpoints",
        "static_pass",
        "test_pass",
    ]


def test_repo_status_holds_its_fields() -> None:
    status = _status(
        stage=StackStage.REVIEW,
        checkpoints=("design-approved",),
        static_pass="abc",
        test_pass="def",
    )
    assert status.format == 1
    assert status.name == "go_cli"
    assert status.stage is StackStage.REVIEW
    assert status.checkpoints == ("design-approved",)
    assert status.static_pass == "abc"
    assert status.test_pass == "def"


def test_repo_status_is_frozen() -> None:
    status = _status()
    with pytest.raises(dataclasses.FrozenInstanceError):
        status.stage = StackStage.ACCEPTED  # type: ignore[misc]  # frozen dataclass; assignment must raise


def test_repo_status_equal_when_fields_equal() -> None:
    assert _status() == _status()
    assert _status() != _status(name="other")


def test_stack_workflow_protocol_methods() -> None:
    for name in (
        "init",
        "load",
        "set_stage",
        "checkpoint",
        "record_test",
        "next_step",
        "ref",
    ):
        assert callable(getattr(StackWorkflow, name))


def test_stack_installer_protocol_methods() -> None:
    assert callable(StackInstaller.install)
