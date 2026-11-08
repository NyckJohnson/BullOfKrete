"""Tests for the parts mock other modules' tests rely on."""

from __future__ import annotations

import dataclasses
from pathlib import Path

from bull.Modules.foundation.Contracts import AppLayout
from bull.Modules.parts.Contracts import Part, Parts
from bull.Modules.parts.mocks import MockParts, sample_part


def _app(tmp_path: Path) -> AppLayout:
    values = {f.name: tmp_path / f.name for f in dataclasses.fields(AppLayout)}
    return AppLayout(**values)


def test_sample_part_is_a_part_with_requested_name_and_root() -> None:
    part = sample_part(Path("/r"), "web")
    assert isinstance(part, Part)
    assert part.name == "web"
    assert part.root == Path("/r")


def test_sample_part_defaults_to_the_implicit_app_part() -> None:
    part = sample_part()
    assert part.name == "app"
    assert part.dir == "."
    assert part.stack == "fixture"


def test_mock_satisfies_the_parts_protocol() -> None:
    parts: Parts = MockParts()
    assert parts is not None


def test_mock_starts_with_one_implicit_part(tmp_path: Path) -> None:
    mock = MockParts()
    assert [p.name for p in mock.all(_app(tmp_path))] == ["app"]


def test_get_without_name_returns_the_only_part(tmp_path: Path) -> None:
    mock = MockParts()
    assert mock.get(_app(tmp_path)).name == "app"


def test_get_by_name_returns_that_part(tmp_path: Path) -> None:
    mock = MockParts()
    app = _app(tmp_path)
    mock.add(app, "web", "fixture")
    assert mock.get(app, "web").name == "web"


def test_add_defaults_dir_to_the_name_and_roots_it_under_the_app(
    tmp_path: Path,
) -> None:
    mock = MockParts()
    app = _app(tmp_path)
    part = mock.add(app, "web", "fixture")
    assert part.dir == "web"
    assert part.root == app.root / "web"
    assert part.stack == "fixture"


def test_add_uses_an_explicit_dir(tmp_path: Path) -> None:
    mock = MockParts()
    app = _app(tmp_path)
    part = mock.add(app, "web", "fixture", "sites/w")
    assert part.dir == "sites/w"
    assert part.root == app.root / "sites/w"


def test_added_part_shows_up_in_all(tmp_path: Path) -> None:
    mock = MockParts()
    app = _app(tmp_path)
    mock.add(app, "web", "fixture")
    assert [p.name for p in mock.all(app)] == ["app", "web"]


def test_all_returns_a_copy(tmp_path: Path) -> None:
    mock = MockParts()
    app = _app(tmp_path)
    mock.all(app).clear()
    assert len(mock.all(app)) == 1


def test_check_reports_no_problems_by_default(tmp_path: Path) -> None:
    assert MockParts().check(_app(tmp_path)) == []


def test_check_reports_the_configured_problems(tmp_path: Path) -> None:
    mock = MockParts()
    mock.problems = ["a overlaps b"]
    assert mock.check(_app(tmp_path)) == ["a overlaps b"]


def test_module_src_is_root_source_dir_modules_module() -> None:
    part = sample_part(Path("/r"))
    assert MockParts().module_src(part, "core") == (
        Path("/r") / part.source_dir / "Modules" / "core"
    )


def test_module_tests_is_root_test_dir_module() -> None:
    part = sample_part(Path("/r"))
    assert MockParts().module_tests(part, "core") == (
        Path("/r") / part.test_dir / "core"
    )


def test_is_test_path_true_inside_a_tests_folder(tmp_path: Path) -> None:
    assert MockParts().is_test_path(_app(tmp_path), Path("tests/core/test_a.py"))


def test_is_test_path_false_for_source_files(tmp_path: Path) -> None:
    assert not MockParts().is_test_path(_app(tmp_path), Path("src/fx/a.py"))


def test_mock_records_calls_in_order(tmp_path: Path) -> None:
    mock = MockParts()
    app = _app(tmp_path)
    part = mock.get(app, "app")
    mock.module_src(part, "core")
    mock.check(app)
    assert [name for name, _ in mock.calls] == ["get", "module_src", "check"]
    assert mock.calls[0][1] == (app, "app")
    assert mock.calls[1][1] == (part, "core")
