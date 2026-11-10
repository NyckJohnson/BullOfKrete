"""Tests for `bull.Modules.interfaces.Contracts`."""

from __future__ import annotations

import pytest

from bull.Modules.interfaces.Contracts import InterfaceResult
from bull.Modules.stacks.Contracts import CheckItem, Role


def _result(*items: CheckItem) -> InterfaceResult:
    return InterfaceResult(
        interface="TallyEvents",
        part="cli",
        module="Export",
        role=Role.PROVIDER,
        items=items,
    )


def test_result_ok_when_every_item_ok() -> None:
    assert _result(CheckItem(True, "a", ""), CheckItem(True, "b", "")).ok is True


def test_result_not_ok_when_one_item_fails() -> None:
    assert _result(CheckItem(True, "a", ""), CheckItem(False, "b", "fix")).ok is False


def test_result_not_ok_when_all_items_fail() -> None:
    assert _result(CheckItem(False, "a", "x")).ok is False


def test_result_with_no_items_is_ok() -> None:
    assert _result().ok is True


@pytest.mark.parametrize("role", [Role.PROVIDER, Role.CONSUMER])
def test_result_keeps_its_fields(role: Role) -> None:
    item = CheckItem(True, "a", "")
    result = InterfaceResult("I", "web", "Import", role, (item,))
    assert (result.interface, result.part, result.module, result.role) == (
        "I",
        "web",
        "Import",
        role,
    )
    assert result.items == (item,)
