"""Tests for `bull.Modules.stack_fixture.tool`: the fixture stacks' gate tool.

Each test builds a small fixture app in `tmp_path` and runs
`python -m bull.Modules.stack_fixture.tool <step> ...` as a subprocess, with the environment
bull gives every gate step (`BULL_PART_ROOT`, `BULL_RESULTS`, ...) and the part root as cwd.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SRC = "src/fx"


class App:
    """A fixture app under a temporary directory."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.results = root / "results"
        self.results.mkdir()
        (root / "fixture.toml").write_text("ok = true\n")

    def write(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def source(self, module: str, name: str, text: str) -> str:
        rel = f"{SRC}/Modules/{module}/{name}"
        self.write(rel, text)
        return rel

    def test_file(self, module: str, name: str, text: str) -> None:
        self.write(f"tests/{module}/{name}", text)

    def run(
        self,
        *args: str,
        adopt: bool = False,
        scope: str = "",
    ) -> subprocess.CompletedProcess[str]:
        env = {k: v for k, v in os.environ.items() if not k.startswith("BULL_")}
        env.update(
            BULL_PART="main",
            BULL_PART_ROOT=str(self.root),
            BULL_APP_ROOT=str(self.root),
            BULL_RESULTS=str(self.results),
            BULL_STACK_DIR=str(self.root),
            BULL_ADOPT_MODE="1" if adopt else "0",
            BULL_SCOPE_MODULE=scope,
            BULL_SETTINGS=json.dumps({"source_dir": SRC, "test_dir": "tests"}),
        )
        return subprocess.run(
            [sys.executable, "-m", "bull.Modules.stack_fixture.tool", *args],
            cwd=self.root,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

    def tests_json(self) -> dict[str, object]:
        data = json.loads((self.results / "tests.json").read_text())
        assert isinstance(data, dict)
        return data

    def coverage_json(self) -> dict[str, list[int]]:
        data = json.loads((self.results / "coverage.json").read_text())
        assert isinstance(data, dict)
        return data


@pytest.fixture
def app(tmp_path: Path) -> App:
    return App(tmp_path)


def labels(result: subprocess.CompletedProcess[str]) -> list[str]:
    return [
        line.removeprefix("bull-fail: ")
        for line in result.stdout.splitlines()
        if line.startswith("bull-fail: ")
    ]


# --- preflight ---------------------------------------------------------------------------


def test_preflight_exits_2_when_toolchain_is_broken(app: App) -> None:
    app.write("fixture.toml", "broken_toolchain = true\n")
    assert app.run("preflight").returncode == 2


def test_preflight_passes_when_toolchain_is_not_broken(app: App) -> None:
    assert app.run("preflight").returncode == 0


def test_preflight_passes_when_broken_toolchain_is_false(app: App) -> None:
    app.write("fixture.toml", "broken_toolchain = false\n")
    assert app.run("preflight").returncode == 0


# --- setup -------------------------------------------------------------------------------


def test_setup_passes_when_fixture_toml_exists(app: App) -> None:
    assert app.run("setup").returncode == 0


def test_setup_fails_with_label_when_fixture_toml_is_missing(app: App) -> None:
    (app.root / "fixture.toml").unlink()
    result = app.run("setup")
    assert result.returncode != 0
    assert "fixture.toml missing" in labels(result)


# --- build-test --------------------------------------------------------------------------


def test_build_test_passes_and_writes_counts_for_passing_tests(app: App) -> None:
    app.source("counter", "a.fx", "let x\n")
    app.test_file("counter", "a.test", "pass one\npass two\n")
    result = app.run("build-test")
    assert result.returncode == 0
    assert app.tests_json() == {"count": 2, "failed": []}


def test_build_test_reports_failing_test_by_id(app: App) -> None:
    app.test_file("counter", "a.test", "pass one\nfail two\n")
    result = app.run("build-test")
    assert result.returncode != 0
    assert app.tests_json() == {"count": 2, "failed": ["counter/a::two"]}
    assert "counter/a::two" in result.stdout


def test_build_test_ids_use_module_and_file_stem(app: App) -> None:
    app.test_file("counter", "a.test", "fail one\n")
    app.test_file("other", "b.test", "fail two\n")
    app.run("build-test")
    failed = app.tests_json()["failed"]
    assert isinstance(failed, list)
    assert sorted(failed) == ["counter/a::one", "other/b::two"]


def test_build_test_with_no_tests_counts_zero(app: App) -> None:
    app.source("counter", "a.fx", "let x\n")
    result = app.run("build-test")
    assert result.returncode == 0
    assert app.tests_json() == {"count": 0, "failed": []}


def test_build_test_ignores_blank_and_comment_lines_in_test_files(app: App) -> None:
    app.test_file("counter", "a.test", "# a note\n\npass one\n   \n# fail nope\n")
    assert app.run("build-test").returncode == 0
    assert app.tests_json() == {"count": 1, "failed": []}


def test_build_test_fails_on_warn_with_file_and_line(app: App) -> None:
    rel = app.source("counter", "a.fx", "# note\n\nlet x WARN\nlet y\n")
    result = app.run("build-test")
    assert result.returncode != 0
    found = labels(result)
    assert any(
        lbl.startswith("warning ") and lbl.endswith("a.fx:3") for lbl in found
    ), found
    assert any(rel in lbl for lbl in found)


def test_build_test_reports_every_warning(app: App) -> None:
    app.source("counter", "a.fx", "let x WARN\nlet y WARN\n")
    found = [lbl for lbl in labels(app.run("build-test")) if lbl.startswith("warning ")]
    assert len(found) == 2
    assert found[0].endswith("a.fx:1")
    assert found[1].endswith("a.fx:2")


def test_build_test_does_not_fail_on_lint_lines(app: App) -> None:
    app.source("counter", "a.fx", "let x LINT\n")
    assert app.run("build-test").returncode == 0


def test_build_test_writes_covered_lines_expanding_ranges(app: App) -> None:
    rel = app.source(
        "counter", "a.fx", "\n".join(f"let v{i}" for i in range(1, 9)) + "\n"
    )
    app.test_file("counter", "a.test", f"pass one\ncovers {rel}:3,5-7\n")
    assert app.run("build-test").returncode == 0
    assert app.coverage_json()[rel] == [3, 5, 6, 7]


def test_build_test_merges_coverage_from_several_test_files(app: App) -> None:
    rel = app.source(
        "counter", "a.fx", "\n".join(f"let v{i}" for i in range(1, 9)) + "\n"
    )
    app.test_file("counter", "a.test", f"pass one\ncovers {rel}:1-2\n")
    app.test_file("counter", "b.test", f"pass two\ncovers {rel}:2,4\n")
    app.run("build-test")
    assert app.coverage_json()[rel] == [1, 2, 4]


def test_build_test_runs_every_module_without_scope(app: App) -> None:
    app.test_file("counter", "a.test", "pass one\n")
    app.test_file("other", "b.test", "pass two\npass three\n")
    app.run("build-test")
    assert app.tests_json()["count"] == 3


def test_build_test_scope_module_counts_only_that_module(app: App) -> None:
    app.test_file("counter", "a.test", "pass one\n")
    app.test_file("other", "b.test", "fail two\npass three\n")
    result = app.run("build-test", scope="counter")
    assert result.returncode == 0
    assert app.tests_json() == {"count": 1, "failed": []}


def test_build_test_does_not_run_journey_tests_as_module_tests(app: App) -> None:
    app.test_file("counter", "a.test", "pass one\n")
    app.write("tests/journey/j.test", "fail flow\n")
    result = app.run("build-test")
    assert result.returncode == 0
    assert app.tests_json() == {"count": 1, "failed": []}


def test_build_test_warn_outside_modules_fails_when_not_adopting(app: App) -> None:
    app.write(f"{SRC}/legacy.fx", "let old WARN\n")
    result = app.run("build-test")
    assert result.returncode != 0
    assert any(lbl.endswith("legacy.fx:1") for lbl in labels(result))


def test_build_test_adopt_mode_ignores_warn_outside_modules(app: App) -> None:
    app.write(f"{SRC}/legacy.fx", "let old WARN\n")
    result = app.run("build-test", adopt=True)
    assert result.returncode == 0
    assert labels(result) == []


def test_build_test_adopt_mode_still_fails_on_warn_inside_modules(app: App) -> None:
    app.source("counter", "a.fx", "let x WARN\n")
    result = app.run("build-test", adopt=True)
    assert result.returncode != 0
    assert any(lbl.endswith("a.fx:1") for lbl in labels(result))


# --- build-test-fast ---------------------------------------------------------------------


def test_build_test_fast_runs_only_the_named_module(app: App) -> None:
    app.test_file("counter", "a.test", "pass one\npass two\n")
    app.test_file("other", "b.test", "fail three\n")
    result = app.run("build-test-fast", "counter")
    assert result.returncode == 0
    assert app.tests_json() == {"count": 2, "failed": []}


def test_build_test_fast_reports_failing_test(app: App) -> None:
    app.test_file("counter", "a.test", "fail one\n")
    result = app.run("build-test-fast", "counter")
    assert result.returncode != 0
    assert app.tests_json() == {"count": 1, "failed": ["counter/a::one"]}


def test_build_test_fast_fails_on_warn_in_the_module(app: App) -> None:
    app.source("counter", "a.fx", "let x\nlet y WARN\n")
    result = app.run("build-test-fast", "counter")
    assert result.returncode != 0
    assert any(
        lbl.startswith("warning ") and lbl.endswith("a.fx:2") for lbl in labels(result)
    )


# --- lint --------------------------------------------------------------------------------


def test_lint_passes_when_module_has_no_lint_lines(app: App) -> None:
    app.source("counter", "a.fx", "let x\n")
    assert app.run("lint", "counter").returncode == 0


def test_lint_fails_with_file_and_line(app: App) -> None:
    app.source("counter", "a.fx", "let x\nlet y LINT\n")
    result = app.run("lint", "counter")
    assert result.returncode != 0
    found = labels(result)
    assert any(lbl.startswith("lint ") and lbl.endswith("a.fx:2") for lbl in found), (
        found
    )


def test_lint_ignores_other_modules(app: App) -> None:
    app.source("counter", "a.fx", "let x\n")
    app.source("other", "b.fx", "let y LINT\n")
    assert app.run("lint", "counter").returncode == 0


def test_lint_does_not_fail_on_warn_lines(app: App) -> None:
    app.source("counter", "a.fx", "let x WARN\n")
    assert app.run("lint", "counter").returncode == 0


# --- rerun -------------------------------------------------------------------------------


def test_rerun_passes_when_named_tests_pass(app: App) -> None:
    app.test_file("counter", "a.test", "pass one\nfail two\n")
    result = app.run("rerun", "counter/a::one")
    assert result.returncode == 0
    assert app.tests_json() == {"count": 1, "failed": []}


def test_rerun_fails_when_a_named_test_fails(app: App) -> None:
    app.test_file("counter", "a.test", "pass one\nfail two\n")
    result = app.run("rerun", "counter/a::two")
    assert result.returncode != 0
    assert app.tests_json() == {"count": 1, "failed": ["counter/a::two"]}


def test_rerun_runs_each_id_given(app: App) -> None:
    app.test_file("counter", "a.test", "pass one\nfail two\npass three\n")
    app.test_file("other", "b.test", "pass four\n")
    result = app.run("rerun", "counter/a::one", "counter/a::two", "other/b::four")
    assert result.returncode != 0
    assert app.tests_json() == {"count": 3, "failed": ["counter/a::two"]}


# --- journeys ----------------------------------------------------------------------------


def test_journeys_pass_when_journey_tests_pass(app: App) -> None:
    app.write("tests/journey/j.test", "pass flow\n")
    assert app.run("journeys").returncode == 0


def test_journeys_fail_and_name_the_failing_journey(app: App) -> None:
    app.write("tests/journey/j.test", "pass flow\nfail broken\n")
    result = app.run("journeys")
    assert result.returncode != 0
    assert "journey/j::broken" in result.stdout


def test_journeys_ignore_failing_module_tests(app: App) -> None:
    app.test_file("counter", "a.test", "fail one\n")
    app.write("tests/journey/j.test", "pass flow\n")
    assert app.run("journeys").returncode == 0


# --- service steps (dispatch to fixture_service.serve) -----------------------------------


def _free_port() -> int:
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


def test_start_ready_stop_dispatch_to_the_service(app: App) -> None:
    import urllib.request

    port = str(_free_port())
    try:
        assert app.run("start", port).returncode == 0
        assert app.run("ready", port, "--timeout", "20").returncode == 0
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as r:
            assert r.status == 200
        assert list(app.results.glob("*.pid"))
        assert app.run("stop", port).returncode == 0
        assert not list(app.results.glob("*.pid"))
    finally:
        for pid_file in app.results.glob("*.pid"):
            try:
                os.kill(int(pid_file.read_text().strip()), 9)
            except (ValueError, OSError):
                pass


def test_ready_through_the_tool_fails_when_nothing_listens(app: App) -> None:
    port = str(_free_port())
    assert app.run("ready", port, "--timeout", "1").returncode != 0
