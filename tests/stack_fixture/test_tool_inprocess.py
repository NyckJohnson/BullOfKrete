"""In-process tests for `bull.Modules.stack_fixture.tool`: call `main(argv)` directly."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from bull.Modules.stack_fixture import tool

SRC = "src/fx"


class App:
    def __init__(self, root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.root = root
        self.results = root / "results"
        (root / "fixture.toml").write_text("ok = true\n")
        self.mp = monkeypatch
        self.env(adopt=False, scope="")

    def env(self, adopt: bool = False, scope: str = "") -> None:
        mp = self.mp
        mp.setenv("BULL_PART_ROOT", str(self.root))
        mp.setenv("BULL_RESULTS", str(self.results))
        mp.setenv("BULL_ADOPT_MODE", "1" if adopt else "0")
        mp.setenv("BULL_SCOPE_MODULE", scope)
        mp.setenv("BULL_SETTINGS", json.dumps({"source_dir": SRC, "test_dir": "tests"}))

    def write(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def tests(self, module: str, name: str, text: str) -> None:
        self.write(f"tests/{module}/{name}", text)

    def tests_json(self) -> dict[str, object]:
        data: dict[str, object] = json.loads((self.results / "tests.json").read_text())
        return data

    def coverage_json(self) -> dict[str, list[int]]:
        data: dict[str, list[int]] = json.loads(
            (self.results / "coverage.json").read_text()
        )
        return data


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> App:
    return App(tmp_path, monkeypatch)


# --- dispatch and usage ------------------------------------------------------------------


def test_main_without_arguments_is_usage_error(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    assert tool.main([]) == 64
    assert "usage" in capsys.readouterr().err


def test_main_unknown_step_is_usage_error(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    assert tool.main(["bogus"]) == 64
    assert "usage" in capsys.readouterr().err


def test_invalid_settings_json_is_usage_error(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    app.mp.setenv("BULL_SETTINGS", "{not json")
    assert tool.main(["preflight"]) == 64
    assert "BULL_SETTINGS" in capsys.readouterr().err


def test_non_object_settings_json_falls_back_to_defaults(app: App) -> None:
    app.mp.setenv("BULL_SETTINGS", "[1, 2]")
    app.write("src/Modules/m/a.fx", "WARN here\n")
    assert tool.main(["build-test"]) == 1


def test_settings_defaults_used_when_env_unset(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    app.mp.delenv("BULL_SETTINGS")
    app.write("src/Modules/m/a.fx", "x\nWARN y\n")
    assert tool.main(["build-test"]) == 1
    assert "bull-fail: warning src/Modules/m/a.fx:2" in capsys.readouterr().out


def test_part_root_and_results_default_to_cwd(
    app: App, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("BULL_PART_ROOT")
    monkeypatch.delenv("BULL_RESULTS")
    monkeypatch.delenv("BULL_SETTINGS")
    monkeypatch.chdir(tmp_path)
    app.write("tests/m/a.test", "pass one\n")
    assert tool.main(["build-test"]) == 0
    assert (tmp_path / "results" / "tests.json").is_file()


# --- preflight / setup -------------------------------------------------------------------


def test_preflight_ok_returns_zero(app: App) -> None:
    assert tool.main(["preflight"]) == 0


def test_preflight_without_fixture_toml_returns_zero(app: App) -> None:
    (app.root / "fixture.toml").unlink()
    assert tool.main(["preflight"]) == 0


def test_preflight_broken_toolchain_returns_two(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    app.write("fixture.toml", "broken_toolchain = true\n")
    assert tool.main(["preflight"]) == 2
    assert "broken" in capsys.readouterr().out


def test_preflight_invalid_toml_is_treated_as_empty(app: App) -> None:
    app.write("fixture.toml", "this is = = not toml [\n")
    assert tool.main(["preflight"]) == 0


def test_setup_ok_with_fixture_toml(app: App) -> None:
    assert tool.main(["setup"]) == 0


def test_setup_missing_fixture_toml_fails(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    (app.root / "fixture.toml").unlink()
    assert tool.main(["setup"]) == 1
    assert "bull-fail: fixture.toml missing" in capsys.readouterr().out


# --- build-test --------------------------------------------------------------------------


def test_build_test_passing_writes_results(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    app.tests("m", "a.test", "# c\npass one\npass two\n")
    assert tool.main(["build-test"]) == 0
    assert app.tests_json() == {"count": 2, "failed": []}
    assert app.coverage_json() == {}
    assert "2 tests, 0 failed" in capsys.readouterr().out


def test_build_test_failing_reports_ids(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    app.tests("m", "a.test", "pass one\nfail two\n")
    assert tool.main(["build-test"]) == 1
    assert app.tests_json() == {"count": 2, "failed": ["m/a::two"]}
    assert "bull-fail: test m/a::two" in capsys.readouterr().out


def test_build_test_warn_line_fails_build(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    app.write(f"{SRC}/Modules/m/a.fx", "pub A\nWARN careful\n")
    app.tests("m", "a.test", "pass one\n")
    assert tool.main(["build-test"]) == 1
    assert f"bull-fail: warning {SRC}/Modules/m/a.fx:2" in capsys.readouterr().out
    assert app.tests_json() == {"count": 1, "failed": []}


def test_build_test_without_source_dir_has_no_warnings(app: App) -> None:
    app.tests("m", "a.test", "pass one\n")
    assert tool.main(["build-test"]) == 0


def test_build_test_adopt_mode_ignores_warn_outside_modules(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    app.env(adopt=True)
    app.write(f"{SRC}/legacy/old.fx", "WARN legacy\n")
    app.write(f"{SRC}/Modules/m/a.fx", "pub A\n")
    assert tool.main(["build-test"]) == 0
    assert "warning" not in capsys.readouterr().out


def test_build_test_adopt_mode_still_fails_warn_inside_modules(app: App) -> None:
    app.env(adopt=True)
    app.write(f"{SRC}/Modules/m/a.fx", "WARN x\n")
    assert tool.main(["build-test"]) == 1


def test_build_test_non_adopt_fails_warn_outside_modules(app: App) -> None:
    app.write(f"{SRC}/legacy/old.fx", "WARN legacy\n")
    assert tool.main(["build-test"]) == 1


def test_build_test_scope_module_runs_only_that_module(app: App) -> None:
    app.env(scope="m")
    app.tests("m", "a.test", "pass one\n")
    app.tests("other", "b.test", "fail two\n")
    assert tool.main(["build-test"]) == 0
    assert app.tests_json() == {"count": 1, "failed": []}


def test_build_test_runs_every_module_but_not_journeys(app: App) -> None:
    app.tests("m", "a.test", "pass one\n")
    app.tests("n", "b.test", "pass two\n")
    app.tests("journey", "j.test", "fail never\n")
    assert tool.main(["build-test"]) == 0
    assert app.tests_json() == {"count": 2, "failed": []}


def test_build_test_without_test_dir_runs_nothing(app: App) -> None:
    assert tool.main(["build-test"]) == 0
    assert app.tests_json() == {"count": 0, "failed": []}


def test_covers_lines_ranges_and_malformed_parts(app: App) -> None:
    app.tests(
        "m",
        "a.test",
        "covers src/a.fx:1,3-5,x,7-y,,9\ncovers src/a.fx:2\ncovers nocolon\npass one\n",
    )
    assert tool.main(["build-test"]) == 0
    assert app.coverage_json() == {"src/a.fx": [1, 2, 3, 4, 5, 9]}


def test_pass_or_fail_without_name_is_ignored(app: App) -> None:
    app.tests("m", "a.test", "pass\nfail\nunknown word\npass real\n")
    assert tool.main(["build-test"]) == 0
    assert app.tests_json() == {"count": 1, "failed": []}


# --- build-test-fast ---------------------------------------------------------------------


def test_build_test_fast_runs_only_named_module(app: App) -> None:
    app.tests("m", "a.test", "pass one\n")
    app.tests("other", "b.test", "fail two\n")
    assert tool.main(["build-test-fast", "m"]) == 0
    assert app.tests_json() == {"count": 1, "failed": []}


def test_build_test_fast_missing_module_is_usage_error(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    assert tool.main(["build-test-fast"]) == 64
    assert "build-test-fast" in capsys.readouterr().err


def test_build_test_fast_extra_argument_is_usage_error(app: App) -> None:
    assert tool.main(["build-test-fast", "m", "n"]) == 64


def test_build_test_fast_empty_module_is_usage_error(app: App) -> None:
    assert tool.main(["build-test-fast", ""]) == 64


# --- lint --------------------------------------------------------------------------------


def test_lint_clean_module_passes(app: App) -> None:
    app.write(f"{SRC}/Modules/m/a.fx", "pub A\n")
    assert tool.main(["lint", "m"]) == 0


def test_lint_reports_each_lint_line(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    app.write(f"{SRC}/Modules/m/a.fx", "pub A\nLINT bad\n# LINT comment\nLINT again\n")
    assert tool.main(["lint", "m"]) == 1
    out = capsys.readouterr().out
    assert f"bull-fail: lint {SRC}/Modules/m/a.fx:2" in out
    assert f"bull-fail: lint {SRC}/Modules/m/a.fx:4" in out
    assert ":3" not in out


def test_lint_ignores_other_modules(app: App) -> None:
    app.write(f"{SRC}/Modules/other/a.fx", "LINT bad\n")
    app.write(f"{SRC}/Modules/m/a.fx", "pub A\n")
    assert tool.main(["lint", "m"]) == 0


def test_lint_unknown_module_passes(app: App) -> None:
    assert tool.main(["lint", "ghost"]) == 0


def test_lint_requires_one_module(app: App) -> None:
    assert tool.main(["lint"]) == 64


def test_lint_source_dir_outside_root_uses_absolute_path(
    app: App, tmp_path_factory: pytest.TempPathFactory
) -> None:
    outside = tmp_path_factory.mktemp("outside")
    (outside / "Modules" / "m").mkdir(parents=True)
    (outside / "Modules" / "m" / "a.fx").write_text("LINT x\n")
    app.mp.setenv("BULL_SETTINGS", json.dumps({"source_dir": str(outside)}))
    assert tool.main(["lint", "m"]) == 1


def test_lint_outside_root_prints_absolute_posix_path(
    app: App,
    tmp_path_factory: pytest.TempPathFactory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    outside = tmp_path_factory.mktemp("outside2")
    (outside / "Modules" / "m").mkdir(parents=True)
    (outside / "Modules" / "m" / "a.fx").write_text("LINT x\n")
    app.mp.setenv("BULL_SETTINGS", json.dumps({"source_dir": str(outside)}))
    tool.main(["lint", "m"])
    expected = (outside / "Modules" / "m" / "a.fx").as_posix()
    assert f"bull-fail: lint {expected}:1" in capsys.readouterr().out


# --- rerun -------------------------------------------------------------------------------


def test_rerun_passing_test(app: App, capsys: pytest.CaptureFixture[str]) -> None:
    app.tests("m", "a.test", "pass one\nfail two\n")
    assert tool.main(["rerun", "m/a::one"]) == 0
    assert app.tests_json() == {"count": 1, "failed": []}
    assert "1 tests, 0 failed" in capsys.readouterr().out


def test_rerun_failing_test(app: App, capsys: pytest.CaptureFixture[str]) -> None:
    app.tests("m", "a.test", "pass one\nfail two\n")
    assert tool.main(["rerun", "m/a::two"]) == 1
    assert app.tests_json() == {"count": 1, "failed": ["m/a::two"]}
    assert "bull-fail: test m/a::two" in capsys.readouterr().out


def test_rerun_several_ids_across_files(app: App) -> None:
    app.tests("m", "a.test", "pass one\npass two\n")
    app.tests("n", "b.test", "fail three\n")
    assert tool.main(["rerun", "m/a::one", "m/a::two", "n/b::three"]) == 1
    assert app.tests_json() == {"count": 3, "failed": ["n/b::three"]}


@pytest.mark.parametrize(
    "bad", ["nosep", "m/a", "m::x", "/a::x", "m/::x", "m/a::", "ma::x"]
)
def test_rerun_malformed_id_is_usage_error(
    app: App, bad: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert tool.main(["rerun", bad]) == 64
    assert "not a test id" in capsys.readouterr().err


def test_rerun_unknown_test_name_is_not_found_and_failed(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    app.tests("m", "a.test", "pass one\n")
    assert tool.main(["rerun", "m/a::nope"]) == 1
    out = capsys.readouterr().out
    assert "test not found: m/a::nope" in out
    assert app.tests_json() == {"count": 1, "failed": ["m/a::nope"]}


def test_rerun_missing_file_is_not_found_and_failed(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    assert tool.main(["rerun", "ghost/file::x"]) == 1
    assert "test not found: ghost/file::x" in capsys.readouterr().out


def test_rerun_without_ids_runs_nothing(app: App) -> None:
    assert tool.main(["rerun"]) == 0
    assert app.tests_json() == {"count": 0, "failed": []}


def test_rerun_skips_coverage(app: App) -> None:
    app.tests("m", "a.test", "covers src/a.fx:1\npass one\n")
    assert tool.main(["rerun", "m/a::one"]) == 0
    assert not (app.results / "coverage.json").exists()


# --- journeys ----------------------------------------------------------------------------


def test_journeys_pass(app: App, capsys: pytest.CaptureFixture[str]) -> None:
    app.tests("journey", "j.test", "pass first\n")
    app.tests("m", "a.test", "fail unit\n")
    assert tool.main(["journeys"]) == 0
    assert "1 tests, 0 failed" in capsys.readouterr().out


def test_journeys_fail(app: App, capsys: pytest.CaptureFixture[str]) -> None:
    app.tests("journey", "j.test", "pass first\nfail second\n")
    assert tool.main(["journeys"]) == 1
    assert "bull-fail: test journey/j::second" in capsys.readouterr().out


def test_journeys_none_present_passes(app: App) -> None:
    assert tool.main(["journeys"]) == 0


# --- service steps -----------------------------------------------------------------------


@pytest.mark.parametrize("step", ["start", "ready", "stop"])
def test_service_steps_dispatch_to_serve_main(
    app: App, step: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def fake_main(argv: list[str]) -> int:
        calls.append(argv)
        return 7

    from bull.Modules.stack_fixture.fixture_service import serve

    monkeypatch.setattr(serve, "main", fake_main)
    assert tool.main([step, "8123", "--timeout", "2"]) == 7
    assert calls == [[step, "8123", "--timeout", "2"]]


def test_service_step_imports_serve_module_by_name(
    app: App, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = SimpleNamespace(main=lambda argv: 0)
    seen: list[str] = []

    def fake_import(name: str) -> SimpleNamespace:
        seen.append(name)
        return fake

    monkeypatch.setattr(tool.importlib, "import_module", fake_import)
    assert tool.main(["stop", "9"]) == 0
    assert seen == ["bull.Modules.stack_fixture.fixture_service.serve"]
