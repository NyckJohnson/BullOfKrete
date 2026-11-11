"""Tests for the adoption mocks."""

from __future__ import annotations

from pathlib import Path

from bull.Modules.adoption.Contracts import Adoption, DetectionReport, LegacyLeft
from bull.Modules.adoption.mocks import MockAdoption
from bull.Modules.foundation.Contracts import AppLayout
from bull.Modules.foundation.mocks import sample_layout


def _layout(tmp_path: Path) -> AppLayout:
    return sample_layout(tmp_path)


def test_mock_satisfies_adoption_protocol() -> None:
    adoption: Adoption = MockAdoption()
    assert isinstance(adoption, MockAdoption)


def test_mock_starts_with_no_calls() -> None:
    assert MockAdoption().calls == []


def test_mock_detect_returns_report_and_records_root(tmp_path: Path) -> None:
    mock = MockAdoption()
    assert mock.detect(tmp_path) is mock.report
    assert mock.calls == [("detect", (tmp_path,))]


def test_mock_detect_returns_replaced_report(tmp_path: Path) -> None:
    mock = MockAdoption()
    mock.report = DetectionReport(stack=None, detection=None, issues=())
    assert mock.detect(tmp_path) is mock.report


def test_mock_legacy_returns_left_and_records_app(tmp_path: Path) -> None:
    mock = MockAdoption()
    app = _layout(tmp_path)
    assert mock.legacy(app) is mock.left
    assert mock.calls == [("legacy", (app,))]


def test_mock_legacy_returns_replaced_left(tmp_path: Path) -> None:
    mock = MockAdoption()
    mock.left = LegacyLeft(files=(), declarations=(), tests=(), memo_files=())
    assert mock.legacy(_layout(tmp_path)).empty is True


def test_mock_apply_records_app_report_and_stack(tmp_path: Path) -> None:
    mock = MockAdoption()
    app = _layout(tmp_path)
    mock.apply(app, mock.report, "fixture")
    assert mock.calls == [("apply", (app, mock.report, "fixture"))]


def test_mock_apply_stack_defaults_to_none(tmp_path: Path) -> None:
    mock = MockAdoption()
    app = _layout(tmp_path)
    mock.apply(app, mock.report)
    assert mock.calls == [("apply", (app, mock.report, None))]


def test_mock_start_finish_abandon_record_calls(tmp_path: Path) -> None:
    mock = MockAdoption()
    app = _layout(tmp_path)
    mock.start(app)
    mock.finish(app)
    mock.abandon(app)
    assert mock.calls == [("start", (app,)), ("finish", (app,)), ("abandon", (app,))]


def test_mock_records_calls_in_order(tmp_path: Path) -> None:
    mock = MockAdoption()
    app = _layout(tmp_path)
    mock.detect(tmp_path)
    mock.start(app)
    mock.legacy(app)
    assert [name for name, _ in mock.calls] == ["detect", "start", "legacy"]


def test_mock_instances_do_not_share_calls(tmp_path: Path) -> None:
    first, second = MockAdoption(), MockAdoption()
    first.detect(tmp_path)
    assert second.calls == []
