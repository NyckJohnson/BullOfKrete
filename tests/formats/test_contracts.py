"""Tests for the formats contract (`bull.Modules.formats.Contracts`)."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from bull.Modules.formats.Contracts import (
    FileFormat,
    FormatTooNew,
    FormatTooOld,
)
from bull.Modules.foundation.Contracts import BullError


def test_format_too_old_is_a_bull_error() -> None:
    assert issubclass(FormatTooOld, BullError)


def test_format_too_new_is_a_bull_error() -> None:
    assert issubclass(FormatTooNew, BullError)


def test_the_two_format_errors_are_distinct() -> None:
    assert not issubclass(FormatTooOld, FormatTooNew)
    assert not issubclass(FormatTooNew, FormatTooOld)


def test_format_errors_carry_message_and_fix() -> None:
    error = FormatTooNew("msg", "fix it")
    assert error.message == "msg"
    assert error.fix == "fix it"


def test_file_format_holds_path_found_and_current() -> None:
    item = FileFormat(Path("a.json"), None, 1)
    assert (item.path, item.found, item.current) == (Path("a.json"), None, 1)


def test_file_format_is_frozen() -> None:
    item = FileFormat(Path("a.json"), 1, 1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        item.found = 2  # type: ignore[misc]
