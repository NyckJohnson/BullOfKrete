"""Tests for the appinit mocks."""

from __future__ import annotations

from pathlib import Path

from bull.Modules.appinit.Contracts import AppInit, Doctor, DoctorReport, InitResult
from bull.Modules.appinit.mocks import MockAppInit, MockDoctor
from bull.Modules.stacks.Contracts import CheckItem


def test_mock_app_init_satisfies_protocol() -> None:
    app_init: AppInit = MockAppInit()
    assert app_init.init(Path("/p")).root == Path("/p")


def test_mock_app_init_starts_with_no_calls() -> None:
    assert MockAppInit().calls == []


def test_mock_app_init_returns_created_result_for_path() -> None:
    result = MockAppInit().init(Path("/p"))
    assert result == InitResult(
        Path("/p"), created=True, relinked=False, adopting=False
    )


def test_mock_app_init_adopt_sets_adopting() -> None:
    assert MockAppInit().init(Path("/p"), adopt=True).adopting is True


def test_mock_app_init_records_init_calls() -> None:
    m = MockAppInit()
    m.init(Path("/a"))
    m.init(Path("/b"), adopt=True)
    assert m.calls == [("init", (Path("/a"), False)), ("init", (Path("/b"), True))]


def test_mock_app_init_open_argv_is_claude_plugin_dir_then_extra() -> None:
    argv = MockAppInit().open_argv(Path("/p"), ["--resume", "x"])
    assert argv == [
        "claude",
        "--plugin-dir",
        str(Path("/p") / ".bull" / "plugin"),
        "--resume",
        "x",
    ]


def test_mock_app_init_open_argv_without_extra_has_only_base() -> None:
    assert MockAppInit().open_argv(Path("/p"), []) == [
        "claude",
        "--plugin-dir",
        str(Path("/p") / ".bull" / "plugin"),
    ]


def test_mock_app_init_records_open_argv_calls() -> None:
    m = MockAppInit()
    m.open_argv(Path("/p"), ["a"])
    assert m.calls == [("open_argv", (Path("/p"), ("a",)))]


def test_mock_doctor_satisfies_protocol() -> None:
    doctor: Doctor = MockDoctor()
    assert isinstance(doctor.run(), DoctorReport)


def test_mock_doctor_starts_with_no_calls() -> None:
    assert MockDoctor().calls == []


def test_mock_doctor_records_run_calls() -> None:
    d = MockDoctor()
    d.run()
    d.run()
    assert d.calls == [("run", ()), ("run", ())]


def test_mock_doctor_default_report_core_ok_with_a_failing_stack_tool() -> None:
    report = MockDoctor().run()
    assert report.ok is True
    assert any(not i.ok for _, items in report.stacks for i in items)


def test_mock_doctor_returns_configured_report() -> None:
    d = MockDoctor()
    d.report = DoctorReport((CheckItem(False, "git", "install git"),), ())
    assert d.run() is d.report
    assert d.run().ok is False
