"""Tests for the foundation contract: errors, AppLayout and RunResult."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from bull.Modules.foundation.Contracts import (
    AppLayout,
    BullError,
    FileFormatError,
    RunResult,
    ToolMissing,
)

LAYOUT_FIELDS = [
    "root",
    "bull_dir",
    "config_file",
    "parts_dir",
    "status_file",
    "backlog_file",
    "usage_file",
    "events_file",
    "passes_dir",
    "results_dir",
    "plugin_dir",
    "run_dir",
    "memo_file",
    "api_dir",
    "features_dir",
    "interfaces_dir",
]


def make_layout() -> AppLayout:
    return AppLayout(**{name: Path("/x") / name for name in LAYOUT_FIELDS})


def test_bull_error_keeps_message_and_fix() -> None:
    err = BullError("boom", "try again")
    assert err.message == "boom"
    assert err.fix == "try again"


def test_bull_error_fix_defaults_to_empty() -> None:
    assert BullError("boom").fix == ""


def test_bull_error_str_contains_message() -> None:
    assert "boom" in str(BullError("boom", "fix it"))


def test_bull_error_is_an_exception() -> None:
    with pytest.raises(BullError, match="boom"):
        raise BullError("boom")


@pytest.mark.parametrize("cls", [ToolMissing, FileFormatError])
def test_specific_errors_are_bull_errors(cls: type[BullError]) -> None:
    err = cls("msg", "fix")
    assert isinstance(err, BullError)
    assert err.message == "msg"
    assert err.fix == "fix"
    assert cls("msg").fix == ""


def test_tool_missing_and_format_error_are_distinct() -> None:
    assert not issubclass(ToolMissing, FileFormatError)
    assert not issubclass(FileFormatError, ToolMissing)


def test_app_layout_has_exactly_the_listed_fields() -> None:
    names = [f.name for f in dataclasses.fields(AppLayout)]
    assert names == LAYOUT_FIELDS


def test_app_layout_is_frozen() -> None:
    layout = make_layout()
    with pytest.raises(dataclasses.FrozenInstanceError):
        layout.root = Path("/other")  # type: ignore[misc]


def test_app_layout_equal_when_fields_equal() -> None:
    assert make_layout() == make_layout()


def test_run_result_has_listed_fields() -> None:
    names = [f.name for f in dataclasses.fields(RunResult)]
    assert names == ["argv", "returncode", "stdout", "stderr", "seconds"]


def test_run_result_keeps_values() -> None:
    r = RunResult(argv=("git", "status"), returncode=1, stdout="o", stderr="e", seconds=1.5)
    assert (r.argv, r.returncode, r.stdout, r.stderr, r.seconds) == (
        ("git", "status"),
        1,
        "o",
        "e",
        1.5,
    )


def test_run_result_is_frozen() -> None:
    r = RunResult(argv=("a",), returncode=0, stdout="", stderr="", seconds=0.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.returncode = 2  # type: ignore[misc]
