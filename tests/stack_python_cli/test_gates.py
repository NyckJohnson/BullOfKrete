"""Tests for `bull.Modules.stack_python_cli.python_cli.gates`.

Most tests call `gates.main(argv)` in-process with the `BULL_*` environment set and the module's
`subprocess.run` replaced by a recorder (so no real tools run); a few end-to-end tests run the
steps against a tiny project with the real `uv` and skip when it isn't on PATH or can't sync.

Choices where the spec is open: the tool calls go through `subprocess.run` (argv lists, found by
the words `mypy`, `pytest`, `ruff`, `uv`); a failing step returns a non-zero exit; `preflight`
returns 2 when `uv` or `uv sync` is missing; the `bull-fail:` lines go to stdout.
"""

from __future__ import annotations

import itertools
import json
import shutil
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

import bull.Modules.stack_python_cli as pkg
from bull.Modules.stack_python_cli.python_cli import gates

_STACK_DIR = Path(pkg.__file__).parent / "python_cli"
_SOURCE = "src/demo_pkg"

Rule = Callable[[list[str]], subprocess.CompletedProcess[str] | None]


def _done(
    rc: int = 0, out: str = "", err: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], rc, out, err)


class Runner:
    """Records every subprocess.run call; `rules` decide each result (default: success)."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.rules: list[Rule] = []

    def __call__(self, args: Sequence[str] | str, *a: object, **kw: object) -> object:
        argv = [str(x) for x in ([args] if isinstance(args, str) else args)]
        self.calls.append(argv)
        for rule in self.rules:
            result = rule(argv)
            if result is not None:
                return result
        return _done()

    def when(self, *words: str, rc: int = 0, out: str = "", err: str = "") -> None:
        def rule(argv: list[str]) -> subprocess.CompletedProcess[str] | None:
            return _done(rc, out, err) if all(w in argv for w in words) else None

        self.rules.append(rule)

    def with_words(self, *words: str) -> list[list[str]]:
        return [c for c in self.calls if all(w in c for w in words)]

    def joined(self) -> str:
        return "\n".join(" ".join(c) for c in self.calls)


class App:
    def __init__(self, root: Path, mp: pytest.MonkeyPatch, runner: Runner) -> None:
        self.root = root
        self.results = root / "results"
        self.mp = mp
        self.runner = runner
        self.env()

    def env(self, scope: str = "", settings: dict[str, object] | None = None) -> None:
        mp = self.mp
        mp.setenv("BULL_PART_ROOT", str(self.root))
        mp.setenv("BULL_APP_ROOT", str(self.root))
        mp.setenv("BULL_RESULTS", str(self.results))
        mp.setenv("BULL_STACK_DIR", str(_STACK_DIR))
        mp.setenv("BULL_ADOPT_MODE", "0")
        mp.setenv("BULL_SCOPE_MODULE", scope)
        data: dict[str, object] = {
            "source_dir": _SOURCE,
            "test_dir": "tests",
            "package": "demo_pkg",
        }
        data.update(settings or {})
        mp.setenv("BULL_SETTINGS", json.dumps(data))

    def write(self, rel: str, text: str = "") -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def with_uv(self) -> None:
        bin_dir = self.root / "bin"
        bin_dir.mkdir(exist_ok=True)
        exe = bin_dir / "uv"
        exe.write_text("#!/bin/sh\nexit 0\n")
        exe.chmod(0o755)
        self.mp.setenv("PATH", str(bin_dir))

    def without_uv(self) -> None:
        empty = self.root / "emptybin"
        empty.mkdir(exist_ok=True)
        self.mp.setenv("PATH", str(empty))


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> App:
    runner = Runner()
    monkeypatch.setattr(subprocess, "run", runner)
    return App(tmp_path, monkeypatch, runner)


def _output(capsys: pytest.CaptureFixture[str]) -> str:
    captured = capsys.readouterr()
    return captured.out + captured.err


# --- dispatch ----------------------------------------------------------------------------


def test_main_without_arguments_is_a_usage_error(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    assert gates.main([]) != 0
    assert "usage" in _output(capsys).lower()


def test_main_unknown_step_is_a_usage_error(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    assert gates.main(["bogus"]) != 0
    assert "usage" in _output(capsys).lower()


# --- preflight ---------------------------------------------------------------------------


def test_preflight_passes_and_runs_uv_sync(app: App) -> None:
    app.with_uv()
    assert gates.main(["preflight"]) == 0
    assert app.runner.with_words("uv", "sync")


def test_preflight_without_uv_exits_2_with_the_fix(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    app.without_uv()
    assert gates.main(["preflight"]) == 2
    out = _output(capsys)
    assert "uv" in out
    assert "https://docs.astral.sh/uv" in out


def test_preflight_with_failing_uv_sync_exits_2_with_the_fix(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    app.with_uv()
    app.runner.when("uv", "sync", rc=1, err="resolution failed")
    assert gates.main(["preflight"]) == 2
    assert "uv sync" in _output(capsys)


# --- setup -------------------------------------------------------------------------------


def test_setup_without_pyproject_fails_naming_it(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    app.with_uv()
    assert gates.main(["setup"]) != 0
    assert "pyproject.toml" in _output(capsys)


# --- build-test --------------------------------------------------------------------------


def test_build_test_runs_strict_mypy_on_the_source_folder(app: App) -> None:
    assert gates.main(["build-test"]) == 0
    calls = app.runner.with_words("mypy", "--strict")
    assert calls
    assert any(_SOURCE in " ".join(c) for c in calls)


def test_build_test_labels_each_mypy_error_with_file_and_line(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    app.runner.when(
        "mypy",
        rc=1,
        out=(
            "src/demo_pkg/a.py:12: error: Incompatible types  [assignment]\n"
            "src/demo_pkg/b.py:7: error: Missing return  [return]\n"
            "Found 2 errors in 2 files (checked 3 source files)\n"
        ),
    )
    assert gates.main(["build-test"]) != 0
    out = capsys.readouterr().out
    assert "bull-fail: mypy src/demo_pkg/a.py:12" in out
    assert "bull-fail: mypy src/demo_pkg/b.py:7" in out


def test_build_test_clean_mypy_prints_no_fail_labels(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    assert gates.main(["build-test"]) == 0
    assert "bull-fail:" not in capsys.readouterr().out


def test_build_test_runs_pytest_over_tests_without_journeys_with_coverage_and_junit(
    app: App,
) -> None:
    assert gates.main(["build-test"]) == 0
    (call,) = app.runner.with_words("pytest")
    text = " ".join(call)
    assert "tests" in call
    assert "--ignore" in text and "tests/journey" in text
    assert "--cov" in text
    assert f"--junitxml={app.results}/junit.xml" in text


def test_build_test_writes_coverage_json_into_results(app: App) -> None:
    assert gates.main(["build-test"]) == 0
    assert str(app.results / "coverage.json") in app.runner.joined()


def test_build_test_failing_pytest_fails_the_step(app: App) -> None:
    app.runner.when("pytest", rc=1, out="1 failed")
    assert gates.main(["build-test"]) != 0


def test_build_test_scope_module_limits_pytest_to_that_modules_tests(app: App) -> None:
    app.env(scope="counter")
    assert gates.main(["build-test"]) == 0
    (call,) = app.runner.with_words("pytest")
    assert "tests/counter" in call
    assert "tests" not in call


# --- build-test-fast ---------------------------------------------------------------------


def test_fast_runs_only_the_modules_tests_without_coverage_but_with_junit(
    app: App,
) -> None:
    assert gates.main(["build-test-fast", "counter"]) == 0
    (call,) = app.runner.with_words("pytest")
    text = " ".join(call)
    assert "tests/counter" in call
    assert "--cov" not in text
    assert f"--junitxml={app.results}/junit.xml" in text


def test_fast_runs_strict_mypy_on_the_source_folder(app: App) -> None:
    assert gates.main(["build-test-fast", "counter"]) == 0
    calls = app.runner.with_words("mypy", "--strict")
    assert calls
    assert any(_SOURCE in c for c in calls)


def test_fast_mypy_error_fails_the_step_with_a_labelled_file_and_line(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    app.runner.when(
        "mypy",
        rc=1,
        out="src/demo_pkg/a.py:12: error: Incompatible types  [assignment]\n",
    )
    assert gates.main(["build-test-fast", "counter"]) != 0
    assert "bull-fail: mypy src/demo_pkg/a.py:12" in capsys.readouterr().out


def test_fast_clean_mypy_prints_no_fail_labels(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    assert gates.main(["build-test-fast", "counter"]) == 0
    assert "bull-fail:" not in capsys.readouterr().out


def test_fast_failing_pytest_fails_the_step(app: App) -> None:
    app.runner.when("pytest", rc=1)
    assert gates.main(["build-test-fast", "counter"]) != 0


def test_fast_without_a_module_is_a_usage_error(app: App) -> None:
    assert gates.main(["build-test-fast"]) != 0
    assert not app.runner.calls


# --- lint --------------------------------------------------------------------------------


def _ruff_check(app: App) -> list[str]:
    (call,) = [c for c in app.runner.with_words("ruff", "check") if "--check" not in c]
    return call


def _ruff_format(app: App) -> list[str]:
    (call,) = app.runner.with_words("ruff", "format", "--check")
    return call


def test_lint_runs_ruff_check_and_format_check_on_module_source_and_tests(
    app: App,
) -> None:
    assert gates.main(["lint", "counter"]) == 0
    for call in (_ruff_check(app), _ruff_format(app)):
        text = " ".join(call)
        assert f"{_SOURCE}/Modules/counter" in text
        assert "tests/counter" in text


def test_lint_uses_the_stacks_ruff_toml_when_the_app_has_no_config(app: App) -> None:
    assert gates.main(["lint", "counter"]) == 0
    for call in (_ruff_check(app), _ruff_format(app)):
        assert any(a.endswith("lint/ruff.toml") for a in call), call


@pytest.mark.parametrize(
    ("rel", "text"),
    [
        ("pyproject.toml", "[tool.ruff]\nline-length = 120\n"),
        ("ruff.toml", "line-length = 120\n"),
        (".ruff.toml", "line-length = 120\n"),
    ],
)
def test_lint_leaves_the_apps_own_ruff_config_in_charge(
    app: App, rel: str, text: str
) -> None:
    app.write(rel, text)
    assert gates.main(["lint", "counter"]) == 0
    for call in (_ruff_check(app), _ruff_format(app)):
        assert not any("python_cli/lint" in a for a in call), call


def test_lint_ignores_a_pyproject_without_ruff_table(app: App) -> None:
    app.write("pyproject.toml", '[project]\nname = "demo_pkg"\n')
    assert gates.main(["lint", "counter"]) == 0
    assert any(a.endswith("lint/ruff.toml") for a in _ruff_check(app))


def test_lint_fails_when_ruff_check_finds_problems(app: App) -> None:
    app.runner.rules.append(
        lambda argv: (
            _done(1, "src/demo_pkg/a.py:1:1: F401 unused import\n")
            if "ruff" in argv and "check" in argv
            else None
        )
    )
    assert gates.main(["lint", "counter"]) != 0


_RUFF_UNFORMATTED = (
    "src/demo_pkg/a.py:2:1: unformatted: File would be reformatted\n"
    "1 file would be reformatted\n"
)


def test_lint_fails_when_format_check_finds_problems(app: App) -> None:
    app.runner.when("ruff", "format", rc=1, out=_RUFF_UNFORMATTED)
    assert gates.main(["lint", "counter"]) != 0


def test_lint_labels_an_unformatted_file_from_ruffs_concise_output(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    app.runner.when("ruff", "format", rc=1, out=_RUFF_UNFORMATTED)
    assert gates.main(["lint", "counter"]) != 0
    assert "bull-fail: format src/demo_pkg/a.py" in capsys.readouterr().out


def test_lint_asks_ruff_format_for_concise_output(app: App) -> None:
    assert gates.main(["lint", "counter"]) == 0
    assert "--output-format=concise" in _ruff_format(app)


def test_lint_without_a_module_is_a_usage_error(app: App) -> None:
    assert gates.main(["lint"]) != 0
    assert not app.runner.calls


def test_stack_ruff_config_does_not_select_naming_rules() -> None:
    text = (_STACK_DIR / "lint" / "ruff.toml").read_text()
    assert '"N"' not in text
    assert "line-length = 100" in text


# --- rerun -------------------------------------------------------------------------------


def test_rerun_passes_the_node_ids_to_pytest(app: App) -> None:
    ids = ["tests/counter/test_a.py::test_one", "tests/other/test_b.py::test_two"]
    assert gates.main(["rerun", *ids]) == 0
    (call,) = app.runner.with_words("pytest")
    for node_id in ids:
        assert node_id in call


def test_rerun_failing_tests_fail_the_step(app: App) -> None:
    app.runner.when("pytest", rc=1)
    assert gates.main(["rerun", "tests/counter/test_a.py::test_one"]) != 0


# --- journeys ----------------------------------------------------------------------------


def test_journeys_run_pytest_over_the_journey_folder(app: App) -> None:
    assert gates.main(["journeys"]) == 0
    (call,) = app.runner.with_words("pytest")
    assert "tests/journey" in call


def test_journeys_failing_pytest_fails_the_step(app: App) -> None:
    app.runner.when("pytest", rc=1)
    assert gates.main(["journeys"]) != 0


# --- defaults ----------------------------------------------------------------------------


def _no_settings(app: App) -> None:
    app.mp.setenv("BULL_SETTINGS", "{}")


def test_build_test_without_settings_uses_the_manifest_default_source_folder(
    app: App,
) -> None:
    _no_settings(app)
    assert gates.main(["build-test"]) == 0
    (mypy,) = app.runner.with_words("mypy", "--strict")
    assert "src/myapp" in mypy
    (pytest_call,) = app.runner.with_words("pytest")
    assert "--cov=src/myapp" in pytest_call


def test_lint_without_settings_uses_the_manifest_default_source_folder(
    app: App,
) -> None:
    _no_settings(app)
    assert gates.main(["lint", "counter"]) == 0
    assert "src/myapp/Modules/counter" in " ".join(_ruff_check(app))


def test_setup_without_settings_checks_the_default_package_name(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    _no_settings(app)
    app.write("pyproject.toml", "[project]\nname = 'myapp'\n")
    app.runner.when("python", rc=1)
    assert gates.main(["setup"]) != 0
    assert "myapp" in capsys.readouterr().out


def test_package_setting_alone_puts_the_source_folder_under_src(app: App) -> None:
    app.mp.setenv("BULL_SETTINGS", json.dumps({"package": "other"}))
    assert gates.main(["build-test"]) == 0
    (mypy,) = app.runner.with_words("mypy", "--strict")
    assert "src/other" in mypy


# --- the package setting is never code -----------------------------------------------------

_PAYLOAD = "os; open('pwned','w')"


def test_setup_never_puts_the_package_setting_into_python_source(app: App) -> None:
    app.env(settings={"package": _PAYLOAD})
    app.write("pyproject.toml", "[project]\nname = 'demo_pkg'\n")
    gates.main(["setup"])
    for call in app.runner.calls:
        for flag, code in itertools.pairwise(call):
            if flag == "-c":
                assert "pwned" not in code, call


# --- tools that are missing or broken ----------------------------------------------------


def _tool_vanishes(app: App, exc: type[OSError]) -> None:
    def rule(argv: list[str]) -> subprocess.CompletedProcess[str] | None:
        if "uv" in argv:
            raise exc(2, "No such file or directory", "uv")
        return None

    app.runner.rules.append(rule)


@pytest.mark.parametrize("exc", [FileNotFoundError, PermissionError])
@pytest.mark.parametrize(
    "argv",
    [
        ["preflight"],
        ["setup"],
        ["build-test"],
        ["build-test-fast", "counter"],
        ["lint", "counter"],
        ["rerun", "tests/counter/test_a.py::test_one"],
        ["journeys"],
    ],
)
def test_a_tool_that_cannot_be_launched_gives_a_message_and_a_failing_exit(
    app: App,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    exc: type[OSError],
) -> None:
    app.with_uv()
    app.write("pyproject.toml", "[project]\nname = 'demo_pkg'\n")
    _tool_vanishes(app, exc)
    assert gates.main(argv) != 0
    assert "uv" in _output(capsys)


# --- end to end with the real uv ---------------------------------------------------------

_uv = shutil.which("uv")
needs_uv = pytest.mark.skipif(_uv is None, reason="uv is not on PATH")

_PYPROJECT = """\
[project]
name = "demo_pkg"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = []

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/demo_pkg"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]

[tool.mypy]
python_version = "3.11"
strict = true
mypy_path = "src"

[dependency-groups]
dev = ["pytest>=8", "pytest-cov>=5", "coverage[toml]>=7", "mypy>=1.11", "ruff>=0.6"]
"""

_GOOD_SOURCE = "from __future__ import annotations\n\n\ndef add(a: int, b: int) -> int:\n    return a + b\n"
_GOOD_TEST = (
    "from __future__ import annotations\n\nfrom demo_pkg.Modules.counter.counter import add\n\n\n"
    "def test_add() -> None:\n    assert add(1, 2) == 3\n"
)


@pytest.fixture
def real(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> App:
    """A tiny synced project; the real subprocess layer."""
    app = App(tmp_path, monkeypatch, Runner())
    app.write("pyproject.toml", _PYPROJECT)
    app.write("src/demo_pkg/__init__.py")
    app.write(
        "src/demo_pkg/cli.py",
        "from __future__ import annotations\n\n\ndef main() -> int:\n    return 0\n",
    )
    app.write("src/demo_pkg/Modules/__init__.py")
    app.write("src/demo_pkg/Modules/counter/__init__.py")
    app.write("src/demo_pkg/Modules/counter/counter.py", _GOOD_SOURCE)
    app.write("tests/counter/__init__.py")
    app.write("tests/counter/test_counter.py", _GOOD_TEST)
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.chdir(tmp_path)
    sync = subprocess.run(
        ["uv", "sync"], cwd=tmp_path, capture_output=True, text=True, check=False
    )
    if sync.returncode != 0:
        pytest.skip(f"uv sync is not available here: {sync.stderr[-200:]}")
    return app


@needs_uv
def test_real_preflight_and_setup_pass_on_a_tiny_project(real: App) -> None:
    assert gates.main(["preflight"]) == 0
    assert gates.main(["setup"]) == 0


@needs_uv
def test_real_setup_fails_when_the_package_is_not_importable(real: App) -> None:
    shutil.rmtree(real.root / "src" / "demo_pkg")
    assert gates.main(["setup"]) != 0


@needs_uv
def test_real_build_test_passes_and_writes_junit_and_coverage(real: App) -> None:
    assert gates.main(["build-test"]) == 0
    assert (real.results / "junit.xml").is_file()
    assert (real.results / "coverage.json").is_file()


@needs_uv
def test_real_build_test_reports_a_mypy_error_with_its_label(
    real: App, capsys: pytest.CaptureFixture[str]
) -> None:
    real.write(
        "src/demo_pkg/Modules/counter/counter.py",
        "from __future__ import annotations\n\n\ndef add(a: int, b: int) -> int:\n    return 'x'\n",
    )
    assert gates.main(["build-test"]) != 0
    assert (
        "bull-fail: mypy src/demo_pkg/Modules/counter/counter.py:5"
        in capsys.readouterr().out
    )


@needs_uv
def test_real_fast_runs_the_modules_tests_and_a_failure_fails_it(real: App) -> None:
    assert gates.main(["build-test-fast", "counter"]) == 0
    real.write(
        "tests/counter/test_counter.py",
        _GOOD_TEST.replace("== 3", "== 4"),
    )
    assert gates.main(["build-test-fast", "counter"]) != 0
    assert (real.results / "junit.xml").is_file()


@needs_uv
def test_real_fast_reports_a_mypy_error_with_its_label(
    real: App, capsys: pytest.CaptureFixture[str]
) -> None:
    real.write(
        "src/demo_pkg/Modules/counter/counter.py",
        "from __future__ import annotations\n\n\ndef add(a: int, b: int) -> int:\n    return 'x'\n",
    )
    assert gates.main(["build-test-fast", "counter"]) != 0
    assert (
        "bull-fail: mypy src/demo_pkg/Modules/counter/counter.py:5"
        in capsys.readouterr().out
    )


@needs_uv
def test_real_lint_passes_clean_code_and_fails_unformatted_code(
    real: App, capsys: pytest.CaptureFixture[str]
) -> None:
    assert gates.main(["lint", "counter"]) == 0
    capsys.readouterr()
    real.write("src/demo_pkg/Modules/counter/counter.py", "import os\nx=1\n")
    assert gates.main(["lint", "counter"]) != 0
    out = capsys.readouterr().out
    assert "bull-fail: format src/demo_pkg/Modules/counter/counter.py" in out


@needs_uv
def test_real_rerun_runs_the_named_test(real: App) -> None:
    assert gates.main(["rerun", "tests/counter/test_counter.py::test_add"]) == 0


@needs_uv
def test_real_journeys_run_the_journey_folder(real: App) -> None:
    real.write("tests/journey/__init__.py")
    real.write(
        "tests/journey/test_run.py",
        "from __future__ import annotations\n\n\ndef test_journey() -> None:\n    assert True\n",
    )
    assert gates.main(["journeys"]) == 0
    real.write(
        "tests/journey/test_run.py", "def test_journey() -> None:\n    assert False\n"
    )
    assert gates.main(["journeys"]) != 0


@needs_uv
def test_real_setup_does_not_run_code_smuggled_through_the_package_setting(
    real: App,
) -> None:
    real.env(settings={"package": _PAYLOAD})
    assert gates.main(["setup"]) != 0
    assert not (real.root / "pwned").exists()


# --- coverage triage: error paths and junit node ids --------------------------------------


def test_invalid_bull_settings_json_is_a_usage_error_naming_the_variable(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    app.mp.setenv("BULL_SETTINGS", "{not json")
    assert gates.main(["journeys"]) == 2
    assert "BULL_SETTINGS" in _output(capsys)
    assert app.runner.calls == []


def test_junit_run_is_none_for_malformed_xml(tmp_path: Path) -> None:
    path = tmp_path / "junit.xml"
    path.write_text("<testsuites><testcase")
    assert gates.junit_run(path) is None


def test_junit_run_rebuilds_a_collection_error_node_id_from_its_name(
    tmp_path: Path,
) -> None:
    path = tmp_path / "junit.xml"
    path.write_text(
        '<testsuites><testsuite><testcase classname="" name="tests.x.test_y">'
        '<error message="boom"/></testcase></testsuite></testsuites>'
    )
    assert gates.junit_run(path) == (1, ["tests/x/test_y.py"])


def test_junit_run_puts_a_test_class_between_file_and_test_name(
    tmp_path: Path,
) -> None:
    path = tmp_path / "junit.xml"
    path.write_text(
        '<testsuites><testsuite><testcase classname="tests.x.test_y.TestY" '
        'name="test_z"><failure message="no"/></testcase></testsuite></testsuites>'
    )
    assert gates.junit_run(path) == (1, ["tests/x/test_y.py::TestY::test_z"])


def test_lint_treats_a_malformed_pyproject_as_having_no_ruff_config(app: App) -> None:
    app.write("pyproject.toml", "this is = [not toml")
    assert gates.main(["lint", "counter"]) == 0
    assert any(a.endswith("lint/ruff.toml") for a in _ruff_check(app))


def test_lint_prints_a_bare_lint_failure_when_ruff_check_fails_without_parsable_output(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    app.runner.when("ruff", "check", rc=2, out="ruff exploded\n")
    assert gates.main(["lint", "counter"]) != 0
    assert "bull-fail: lint\n" in capsys.readouterr().out


def test_lint_prints_a_bare_format_failure_when_format_check_fails_without_parsable_output(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    app.runner.when("ruff", "format", rc=2, out="ruff exploded\n")
    assert gates.main(["lint", "counter"]) != 0
    assert "bull-fail: format\n" in capsys.readouterr().out


def test_rerun_without_node_ids_is_a_usage_error(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    assert gates.main(["rerun"]) == 2
    assert "usage" in _output(capsys).lower()
    assert app.runner.with_words("pytest") == []


def test_a_step_that_takes_no_arguments_rejects_extra_ones(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    assert gates.main(["journeys", "x"]) == 2
    assert "usage" in _output(capsys).lower()
    assert app.runner.calls == []
