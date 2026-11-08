"""Tests for `bull.Modules.stacks.select` (`LiveStackOps`).

Shapes chosen here (for the code-writer):
  - `LiveStackOps(registry: StackRegistry, settings: Settings, runner: Runner,
    python: str = sys.executable)`. `settings` is the app's loaded settings (used by
    `check` and `run_command`, never by `select`); `python` is what `{python}` expands to.
  - `select` edits the real files under `app.root` (config.toml, .gitignore, scaffold).
  - `rules` / `setup_guide` delegate to `bull.Modules.stacks.docs`.
  - One-part app: the implicit part is named `app`, its folder is `app.root`, its stack is
    `settings.get("stack", None)`. A named part reads `stack`/`dir` from
    `.bull/parts/<part>.toml` (equal to `settings.get("stack"|"dir", part)`).
  - Results folder for a part: `app.results_dir / <part>` (`app` for the one-part app).
  - `check` returns the stack's reader items plus bull's own: one item per `requires` tool
    (its `item` names the tool, its `fix` carries the hint when missing) and one for the
    source folder and one for the test folder (`item` names the folder path).
  - `run_command` calls `runner.run(argv, cwd, env, timeout)` and returns its returncode.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import replace
from pathlib import Path

import pytest

from bull.Modules.foundation.Contracts import AppLayout, RunResult
from bull.Modules.foundation.mocks import MockRunner, sample_layout
from bull.Modules.settings.Contracts import SettingValue
from bull.Modules.stacks.Contracts import Requirement, StackError
from bull.Modules.stacks.docs import rules, setup_guide
from bull.Modules.stacks.mocks import MockStackReaders, MockStackRegistry
from bull.Modules.stacks.select import LiveStackOps

from .fakes import FakeSettings, registry_with, stack_of

PYTHON = "/fake/python"


def make_app(tmp_path: Path, config: str | None = "format = 1\n") -> AppLayout:
    app = sample_layout(tmp_path)
    app.bull_dir.mkdir(parents=True, exist_ok=True)
    if config is not None:
        app.config_file.write_text(config, encoding="utf-8")
    return app


def ops_for(
    registry: MockStackRegistry,
    settings: FakeSettings | None = None,
    runner: MockRunner | None = None,
) -> LiveStackOps:
    return LiveStackOps(
        registry,
        settings or FakeSettings({"stack": "fixture"}),
        runner or MockRunner(),
        python=PYTHON,
    )


def message(error: StackError) -> str:
    return f"{error.message} {error.fix}"


# ---------------------------------------------------------------- select


def test_select_writes_stack_and_default_folders_into_config(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    ops_for(registry_with()).select(app, "fixture")
    data = tomllib.loads(app.config_file.read_text(encoding="utf-8"))
    assert data["stack"] == "fixture"
    assert data["source_dir"] == "src/fx"
    assert data["test_dir"] == "tests"


def test_select_keeps_existing_config_entries(tmp_path: Path) -> None:
    app = make_app(tmp_path, "format = 1\nmax_attempts = 5\n")
    ops_for(registry_with()).select(app, "fixture")
    data = tomllib.loads(app.config_file.read_text(encoding="utf-8"))
    assert data["format"] == 1
    assert data["max_attempts"] == 5


def test_select_creates_config_with_format_when_missing(tmp_path: Path) -> None:
    app = make_app(tmp_path, config=None)
    ops_for(registry_with()).select(app, "fixture")
    data = tomllib.loads(app.config_file.read_text(encoding="utf-8"))
    assert data["format"] == 1
    assert data["stack"] == "fixture"


def test_select_uses_the_chosen_stacks_own_defaults(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    ops_for(registry_with()).select(app, "python_cli")
    data = tomllib.loads(app.config_file.read_text(encoding="utf-8"))
    assert data["stack"] == "python_cli"


def test_select_creates_gitignore_with_the_stacks_lines(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    registry = registry_with(gitignore=("results/", "*.log"))
    ops_for(registry).select(app, "fixture")
    lines = (tmp_path / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "results/" in lines
    assert "*.log" in lines


def test_select_merges_gitignore_without_duplicates_and_keeps_existing(
    tmp_path: Path,
) -> None:
    app = make_app(tmp_path)
    (tmp_path / ".gitignore").write_text("node_modules/\nresults/\n", encoding="utf-8")
    registry = registry_with(gitignore=("results/", "*.log"))
    ops_for(registry).select(app, "fixture")
    lines = (tmp_path / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert lines.count("results/") == 1
    assert "node_modules/" in lines
    assert "*.log" in lines


def test_select_merges_gitignore_when_the_last_line_has_no_newline(
    tmp_path: Path,
) -> None:
    app = make_app(tmp_path)
    (tmp_path / ".gitignore").write_text("node_modules/", encoding="utf-8")
    ops_for(registry_with(gitignore=("results/",))).select(app, "fixture")
    lines = (tmp_path / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert lines[0] == "node_modules/"
    assert "results/" in lines


def test_select_twice_changes_nothing_the_second_time(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    ops = ops_for(registry_with(gitignore=("results/", "*.log")))
    ops.select(app, "fixture")
    first = ((tmp_path / ".gitignore").read_text(), app.config_file.read_text())
    ops.select(app, "fixture")
    assert ((tmp_path / ".gitignore").read_text(), app.config_file.read_text()) == first


def test_select_creates_the_scaffold_folders(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    registry = registry_with(scaffold=("src", "tests", "docs/extra"))
    ops_for(registry).select(app, "fixture")
    assert (tmp_path / "src").is_dir()
    assert (tmp_path / "tests").is_dir()
    assert (tmp_path / "docs" / "extra").is_dir()


def test_select_accepts_scaffold_folders_that_already_exist(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "keep.txt").write_text("x", encoding="utf-8")
    ops_for(registry_with()).select(app, "fixture")
    assert (tmp_path / "src" / "keep.txt").read_text() == "x"


def test_select_refuses_an_app_with_parts_and_points_to_part_add(
    tmp_path: Path,
) -> None:
    app = make_app(tmp_path)
    app.parts_dir.mkdir(parents=True)
    (app.parts_dir / "api.toml").write_text('format = 1\nstack = "fixture"\n')
    before = app.config_file.read_text(encoding="utf-8")
    with pytest.raises(StackError) as caught:
        ops_for(registry_with()).select(app, "fixture")
    assert "bull part add" in message(caught.value)
    assert app.config_file.read_text(encoding="utf-8") == before
    assert not (tmp_path / "src").exists()


def test_select_allows_an_empty_parts_folder(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    app.parts_dir.mkdir(parents=True)
    ops_for(registry_with()).select(app, "fixture")
    data = tomllib.loads(app.config_file.read_text(encoding="utf-8"))
    assert data["stack"] == "fixture"


def test_select_unknown_stack_raises_and_writes_nothing(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    before = app.config_file.read_text(encoding="utf-8")
    with pytest.raises(StackError):
        ops_for(registry_with()).select(app, "nonesuch")
    assert app.config_file.read_text(encoding="utf-8") == before
    assert not (tmp_path / ".gitignore").exists()
    assert not (tmp_path / "src").exists()


# ------------------------------------------------------ rules and setup


def test_rules_delegates_to_the_docs_module(tmp_path: Path) -> None:
    (tmp_path / "rules.md").write_text("## common\n- C\n\n## reviewer\n- R\n")
    stack = stack_of(registry_with(tmp_path))
    ops = ops_for(registry_with(tmp_path))
    assert ops.rules(stack, "reviewer") == rules(stack, "reviewer")
    assert "- R" in ops.rules(stack, "reviewer")


def test_rules_for_a_missing_agent_raises(tmp_path: Path) -> None:
    (tmp_path / "rules.md").write_text("## common\n- C\n")
    stack = stack_of(registry_with(tmp_path))
    with pytest.raises(StackError):
        ops_for(registry_with(tmp_path)).rules(stack, "reviewer")


def test_setup_guide_delegates_to_the_docs_module(tmp_path: Path) -> None:
    (tmp_path / "setup.md").write_text("# Setup\n\n1. A\n\n## For a feature\n- F\n")
    stack = stack_of(registry_with(tmp_path))
    ops = ops_for(registry_with(tmp_path))
    assert ops.setup_guide(stack) == setup_guide(stack)
    assert "- F" in ops.setup_guide(stack, "For a feature")


def test_setup_guide_with_an_unknown_section_raises(tmp_path: Path) -> None:
    (tmp_path / "setup.md").write_text("# Setup\n\n1. A\n")
    stack = stack_of(registry_with(tmp_path))
    with pytest.raises(StackError):
        ops_for(registry_with(tmp_path)).setup_guide(stack, "Nope")


# ----------------------------------------------------------------- check

APP_VALUES: dict[str, SettingValue] = {
    "stack": "fixture",
    "dir": ".",
    "source_dir": "src/fx",
    "test_dir": "tests",
    "max_attempts": 3,
    "coverage.exclude": ("*/mocks/*", "*/x/*"),
}
PART_VALUES: dict[str, SettingValue] = {
    **APP_VALUES,
    "dir": "services/api",
    "source_dir": "api_src",
    "test_dir": "api_tests",
}


class CheckRig:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp = tmp_path
        self.app = make_app(tmp_path, 'format = 1\nstack = "fixture"\n')
        self.readers = MockStackReaders()
        self.runner = MockRunner()
        self.registry = registry_with(
            requires=(
                Requirement("git", "https://git-scm.com"),
                Requirement("uv", "https://uv.example/install"),
            )
        )
        stack = self.registry.stacks["fixture"]
        self.registry.stacks["fixture"] = replace(stack, readers=self.readers)
        self.settings = FakeSettings(APP_VALUES, {"api": PART_VALUES})

    def ops(self) -> LiveStackOps:
        return ops_for(self.registry, self.settings, self.runner)

    def make_folders(self, root: Path, source: str, tests: str) -> None:
        (root / source).mkdir(parents=True, exist_ok=True)
        (root / tests).mkdir(parents=True, exist_ok=True)

    def add_part(self) -> Path:
        self.app.parts_dir.mkdir(parents=True, exist_ok=True)
        (self.app.parts_dir / "api.toml").write_text(
            'format = 1\nstack = "fixture"\ndir = "services/api"\n', encoding="utf-8"
        )
        return self.tmp / "services" / "api"

    def set_adoption(self, adoption: object) -> None:
        self.app.status_file.write_text(
            json.dumps({"format": 1, "kind": "app", "adoption": adoption}),
            encoding="utf-8",
        )


@pytest.fixture
def rig(tmp_path: Path) -> CheckRig:
    r = CheckRig(tmp_path)
    r.make_folders(tmp_path, "src/fx", "tests")
    return r


def failing(items: list) -> list:  # type: ignore[type-arg]
    return [i for i in items if not i.ok]


def test_check_calls_the_stack_reader_with_the_app_root_and_resolved_settings(
    rig: CheckRig,
) -> None:
    rig.ops().check(rig.app)
    (name, (part_root, settings, adopting)) = rig.readers.calls[-1]
    assert name == "check"
    assert part_root == rig.tmp
    assert settings == APP_VALUES
    assert adopting is False


def test_check_includes_the_readers_items(rig: CheckRig) -> None:
    items = rig.ops().check(rig.app)
    assert any(i.item == "fixture.toml present" and i.ok for i in items)


def test_check_includes_a_failing_reader_item_unchanged(rig: CheckRig) -> None:
    from bull.Modules.stacks.Contracts import CheckItem

    rig.readers.items = [CheckItem(False, "fixture.toml present", "create it")]
    items = rig.ops().check(rig.app)
    assert CheckItem(False, "fixture.toml present", "create it") in items


def test_check_passes_when_every_item_is_fine(rig: CheckRig) -> None:
    assert failing(rig.ops().check(rig.app)) == []


def test_check_reports_a_required_tool_that_is_not_on_path(rig: CheckRig) -> None:
    del rig.runner.tools["uv"]
    bad = failing(rig.ops().check(rig.app))
    assert len(bad) == 1
    assert "uv" in bad[0].item
    assert "https://uv.example/install" in bad[0].fix


def test_check_looks_each_required_tool_up_through_the_runner(rig: CheckRig) -> None:
    rig.ops().check(rig.app)
    looked_up = [str(args[0]) for name, args in rig.runner.calls if name == "which"]
    assert sorted(looked_up) == ["git", "uv"]


def test_check_reports_each_required_tool_found(rig: CheckRig) -> None:
    items = rig.ops().check(rig.app)
    for tool in ("git", "uv"):
        assert any(tool in i.item and i.ok for i in items)


def test_check_reports_a_missing_source_folder(tmp_path: Path) -> None:
    r = CheckRig(tmp_path)
    (tmp_path / "tests").mkdir()
    bad = failing(r.ops().check(r.app))
    assert len(bad) == 1
    assert "src/fx" in bad[0].item
    assert bad[0].fix


def test_check_reports_a_missing_test_folder(tmp_path: Path) -> None:
    r = CheckRig(tmp_path)
    (tmp_path / "src" / "fx").mkdir(parents=True)
    bad = failing(r.ops().check(r.app))
    assert len(bad) == 1
    assert "tests" in bad[0].item
    assert bad[0].fix


def test_check_reports_both_folders_missing_as_two_failures(tmp_path: Path) -> None:
    r = CheckRig(tmp_path)
    assert len(failing(r.ops().check(r.app))) == 2


def test_check_with_no_adoption_in_status_is_not_adopting(rig: CheckRig) -> None:
    rig.set_adoption(None)
    rig.ops().check(rig.app)
    assert rig.readers.calls[-1][1][2] is False


def test_check_while_an_adoption_is_active_is_adopting(rig: CheckRig) -> None:
    rig.set_adoption({"stage": 2, "checkpoints": []})
    rig.ops().check(rig.app)
    assert rig.readers.calls[-1][1][2] is True


def test_check_without_a_status_file_is_not_adopting(rig: CheckRig) -> None:
    assert not rig.app.status_file.exists()
    rig.ops().check(rig.app)
    assert rig.readers.calls[-1][1][2] is False


def test_check_of_a_named_part_uses_the_parts_folder_and_settings(
    rig: CheckRig,
) -> None:
    part_root = rig.add_part()
    rig.make_folders(part_root, "api_src", "api_tests")
    items = rig.ops().check(rig.app, "api")
    (_, (root, settings, _)) = rig.readers.calls[-1]
    assert root == part_root
    assert settings == PART_VALUES
    assert failing(items) == []


def test_check_of_a_named_part_looks_for_folders_inside_the_part(
    rig: CheckRig,
) -> None:
    rig.add_part()  # app-level src/fx and tests exist, the part's own do not
    bad = failing(rig.ops().check(rig.app, "api"))
    assert {"api_src" in i.item or "api_tests" in i.item for i in bad} == {True}
    assert len(bad) == 2


def test_check_of_a_named_part_uses_that_parts_adoption_flag(rig: CheckRig) -> None:
    part_root = rig.add_part()
    rig.make_folders(part_root, "api_src", "api_tests")
    rig.set_adoption({"stage": 1, "checkpoints": []})
    rig.ops().check(rig.app, "api")
    assert rig.readers.calls[-1][1][2] is True


# ----------------------------------------------------------- run_command

PRUNE = (
    "{python}",
    "{stack_dir}/gates.py",
    "prune",
    "{app_root}",
    "{part_root}",
    "{results}",
    "{module}",
)


class RunRig:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp = tmp_path
        self.app = make_app(tmp_path, 'format = 1\nstack = "fixture"\n')
        self.runner = MockRunner()
        self.home = tmp_path / "stackhome"
        self.home.mkdir()
        self.registry = registry_with(
            self.home, commands={"prune": PRUNE, "tidy": ("{python}", "tidy")}
        )
        self.settings = FakeSettings(APP_VALUES, {"api": PART_VALUES})

    def ops(self) -> LiveStackOps:
        return ops_for(self.registry, self.settings, self.runner)

    def last_run(self) -> tuple[tuple[str, ...], Path, dict[str, str]]:
        runs = [a for name, a in self.runner.calls if name == "run"]
        argv, cwd, env, _timeout = runs[-1]
        assert isinstance(env, dict)
        return argv, cwd, env  # type: ignore[return-value]


@pytest.fixture
def run_rig(tmp_path: Path) -> RunRig:
    return RunRig(tmp_path)


def test_run_command_expands_placeholders_for_the_one_part_app(
    run_rig: RunRig,
) -> None:
    run_rig.ops().run_command(run_rig.app, "prune")
    argv, _, _ = run_rig.last_run()
    assert argv == (
        PYTHON,
        f"{run_rig.home}/gates.py",
        "prune",
        str(run_rig.tmp),
        str(run_rig.tmp),
        str(run_rig.app.results_dir / "app"),
        "",
    )


def test_run_command_sets_the_gate_step_environment(run_rig: RunRig) -> None:
    run_rig.ops().run_command(run_rig.app, "prune")
    _, _, env = run_rig.last_run()
    assert env["BULL_PART"] == "app"
    assert env["BULL_PART_ROOT"] == str(run_rig.tmp)
    assert env["BULL_APP_ROOT"] == str(run_rig.tmp)
    assert env["BULL_RESULTS"] == str(run_rig.app.results_dir / "app")
    assert env["BULL_STACK_DIR"] == str(run_rig.home)
    assert env["BULL_ADOPT_MODE"] == "0"
    assert env["BULL_SCOPE_MODULE"] == ""


def test_run_command_passes_the_resolved_settings_as_json(run_rig: RunRig) -> None:
    run_rig.ops().run_command(run_rig.app, "prune")
    _, _, env = run_rig.last_run()
    expected = {
        k: list(v) if isinstance(v, tuple) else v for k, v in APP_VALUES.items()
    }
    assert json.loads(env["BULL_SETTINGS"]) == expected


def test_run_command_sets_adopt_mode_while_adopting(run_rig: RunRig) -> None:
    run_rig.app.status_file.write_text(
        json.dumps({"format": 1, "adoption": {"stage": 1, "checkpoints": []}})
    )
    run_rig.ops().run_command(run_rig.app, "prune")
    assert run_rig.last_run()[2]["BULL_ADOPT_MODE"] == "1"


def test_run_command_for_a_named_part_uses_its_folder_results_and_settings(
    run_rig: RunRig,
) -> None:
    run_rig.app.parts_dir.mkdir(parents=True)
    (run_rig.app.parts_dir / "api.toml").write_text(
        'format = 1\nstack = "fixture"\ndir = "services/api"\n'
    )
    run_rig.ops().run_command(run_rig.app, "prune", "api")
    argv, _, env = run_rig.last_run()
    part_root = run_rig.tmp / "services" / "api"
    assert argv[3:6] == (
        str(run_rig.tmp),
        str(part_root),
        str(run_rig.app.results_dir / "api"),
    )
    assert env["BULL_PART"] == "api"
    assert env["BULL_PART_ROOT"] == str(part_root)
    assert env["BULL_APP_ROOT"] == str(run_rig.tmp)
    assert env["BULL_RESULTS"] == str(run_rig.app.results_dir / "api")
    assert json.loads(env["BULL_SETTINGS"])["source_dir"] == "api_src"


def test_run_command_returns_the_exit_code(run_rig: RunRig) -> None:
    run_rig.runner.results[PYTHON] = RunResult((PYTHON,), 3, "", "", 0.1)
    assert run_rig.ops().run_command(run_rig.app, "prune") == 3


def test_run_command_returns_zero_on_success(run_rig: RunRig) -> None:
    assert run_rig.ops().run_command(run_rig.app, "prune") == 0


def test_run_command_runs_only_the_named_command(run_rig: RunRig) -> None:
    run_rig.ops().run_command(run_rig.app, "tidy")
    argv, _, _ = run_rig.last_run()
    assert argv == (PYTHON, "tidy")
    assert len([n for n, _ in run_rig.runner.calls if n == "run"]) == 1


def test_run_command_unknown_name_raises_listing_the_commands(
    run_rig: RunRig,
) -> None:
    with pytest.raises(StackError) as caught:
        run_rig.ops().run_command(run_rig.app, "nope")
    text = message(caught.value)
    assert "nope" in text
    assert "prune" in text
    assert "tidy" in text
    assert [n for n, _ in run_rig.runner.calls if n == "run"] == []


def test_run_command_with_no_commands_defined_raises(tmp_path: Path) -> None:
    app = make_app(tmp_path, 'format = 1\nstack = "fixture"\n')
    ops = ops_for(registry_with(tmp_path), FakeSettings(APP_VALUES))
    with pytest.raises(StackError):
        ops.run_command(app, "prune")
