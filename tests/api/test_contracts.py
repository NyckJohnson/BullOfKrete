"""Tests for the api contract types (`bull.Modules.api.Contracts`)."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from bull.Modules.api.Contracts import ApiCheck, ApiSnapshots, ApprovalNeeded, Snapshot
from bull.Modules.foundation.Contracts import BullError


def test_approval_needed_is_a_bull_error() -> None:
    assert issubclass(ApprovalNeeded, BullError)


def test_approval_needed_can_be_caught_as_bull_error() -> None:
    with pytest.raises(BullError):
        raise ApprovalNeeded("the x contract changed", "approve it")


def test_snapshot_holds_name_and_files() -> None:
    files = {"Contracts/a.py": ("pub a",)}
    snap = Snapshot(name="m", files=files)
    assert snap.name == "m"
    assert snap.files == files


def test_snapshot_field_names() -> None:
    assert [f.name for f in dataclasses.fields(Snapshot)] == ["name", "files"]


def test_snapshot_is_frozen() -> None:
    snap = Snapshot(name="m", files={})
    with pytest.raises(dataclasses.FrozenInstanceError):
        snap.name = "other"  # type: ignore[misc]


def test_snapshot_equal_when_fields_equal() -> None:
    assert Snapshot("m", {"a": ("x",)}) == Snapshot("m", {"a": ("x",)})
    assert Snapshot("m", {"a": ("x",)}) != Snapshot("m", {"a": ("y",)})


def test_api_check_holds_fields() -> None:
    check = ApiCheck(name="m", ok=False, stored=True, diff="-a\n+b")
    assert (check.name, check.ok, check.stored, check.diff) == ("m", False, True, "-a\n+b")


def test_api_check_field_names() -> None:
    assert [f.name for f in dataclasses.fields(ApiCheck)] == ["name", "ok", "stored", "diff"]


def test_api_check_is_frozen() -> None:
    check = ApiCheck(name="m", ok=True, stored=True, diff="")
    with pytest.raises(dataclasses.FrozenInstanceError):
        check.ok = False  # type: ignore[misc]


@pytest.mark.parametrize(
    "method",
    [
        "current",
        "check",
        "write",
        "check_interface",
        "write_interface",
        "render",
        "parse",
    ],
)
def test_api_snapshots_protocol_declares_method(method: str) -> None:
    assert callable(getattr(ApiSnapshots, method))


def test_api_snapshots_write_returns_optional_path_annotation() -> None:
    assert "Path" in str(ApiSnapshots.write.__annotations__["return"])
    assert Path is not None
