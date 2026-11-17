"""Tests for the appinit contract types."""

from __future__ import annotations

import dataclasses
import inspect
from pathlib import Path

import pytest

from bull.Modules.appinit.Contracts import AppInit, Doctor, DoctorReport, InitResult
from bull.Modules.stacks.Contracts import CheckItem

_OK = CheckItem(True, "thing", "")
_BAD = CheckItem(False, "thing", "install it")


def test_init_result_holds_root_and_flags() -> None:
    r = InitResult(Path("/x"), created=True, relinked=False, adopting=True)
    assert (r.root, r.created, r.relinked, r.adopting) == (
        Path("/x"),
        True,
        False,
        True,
    )


def test_init_result_is_frozen() -> None:
    r = InitResult(Path("/x"), True, False, False)
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.created = False  # type: ignore[misc]


def test_init_result_equality_is_by_value() -> None:
    assert InitResult(Path("/x"), True, False, False) == InitResult(
        Path("/x"), True, False, False
    )
    assert InitResult(Path("/x"), True, False, False) != InitResult(
        Path("/x"), False, True, False
    )


def test_doctor_report_holds_items_and_stacks() -> None:
    report = DoctorReport(items=(_OK,), stacks=(("s", (_BAD,)),))
    assert report.items == (_OK,)
    assert report.stacks == (("s", (_BAD,)),)


def test_doctor_report_is_frozen() -> None:
    report = DoctorReport((), ())
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.items = (_OK,)  # type: ignore[misc]


def test_doctor_report_ok_when_every_core_item_passes() -> None:
    assert DoctorReport((_OK, _OK), ()).ok is True


def test_doctor_report_not_ok_when_a_core_item_fails() -> None:
    assert DoctorReport((_OK, _BAD, _OK), ()).ok is False


def test_doctor_report_ok_ignores_failing_stack_items() -> None:
    report = DoctorReport((_OK,), (("go_cli", (_BAD,)),))
    assert report.ok is True


def test_doctor_report_not_ok_with_failing_core_despite_passing_stacks() -> None:
    report = DoctorReport((_BAD,), (("py", (_OK,)),))
    assert report.ok is False


def test_doctor_report_with_no_items_is_ok() -> None:
    assert DoctorReport((), ()).ok is True


def test_app_init_protocol_has_init_and_open_argv() -> None:
    assert callable(AppInit.init)
    assert callable(AppInit.open_argv)
    assert list(inspect.signature(AppInit.init).parameters) == [
        "self",
        "path",
        "adopt",
    ]
    assert inspect.signature(AppInit.init).parameters["adopt"].default is False
    assert list(inspect.signature(AppInit.open_argv).parameters) == [
        "self",
        "path",
        "extra",
    ]


def test_doctor_protocol_has_run() -> None:
    assert list(inspect.signature(Doctor.run).parameters) == ["self"]
