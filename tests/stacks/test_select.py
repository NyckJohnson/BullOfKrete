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
import os
import stat
import tomllib
from dataclasses import replace
from pathlib import Path

import pytest

from bull.Modules.foundation.Contracts import (
    AppLayout,
    BullError,
    FileFormatError,
    RunResult,
)
from bull.Modules.foundation.mocks import MockRunner, sample_layout
from bull.Modules.settings.Contracts import (
    Setting,
    SettingType,
    SettingValue,
    StackLayer,
)
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


# ------------------------------------------------- review: part resolution


def add_parts(app: AppLayout, *names: str) -> None:
    app.parts_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        (app.parts_dir / f"{name}.toml").write_text(
            f'format = 1\nstack = "fixture"\ndir = "{name}_dir"\n', encoding="utf-8"
        )


SUB_VALUES: dict[str, SettingValue] = {**APP_VALUES, "dir": "sub"}


def test_check_with_an_app_part_file_uses_that_parts_dir_and_settings(
    tmp_path: Path,
) -> None:
    rig = CheckRig(tmp_path)
    rig.settings = FakeSettings(SUB_VALUES)
    add_parts(rig.app, "app")
    rig.make_folders(tmp_path / "sub", "src/fx", "tests")
    items = rig.ops().check(rig.app, "app")
    (_, (root, settings, _)) = rig.readers.calls[-1]
    assert root == tmp_path / "sub"
    assert settings == SUB_VALUES
    assert failing(items) == []


def test_check_with_an_app_part_file_looks_for_folders_inside_its_dir(
    tmp_path: Path,
) -> None:
    rig = CheckRig(tmp_path)
    rig.settings = FakeSettings(SUB_VALUES)
    add_parts(rig.app, "app")
    rig.make_folders(tmp_path, "src/fx", "tests")  # only at the app root
    assert len(failing(rig.ops().check(rig.app, "app"))) == 2


def test_run_command_with_an_app_part_file_uses_that_parts_dir(
    run_rig: RunRig,
) -> None:
    run_rig.settings = FakeSettings(SUB_VALUES)
    add_parts(run_rig.app, "app")
    run_rig.ops().run_command(run_rig.app, "prune", "app")
    _, cwd, env = run_rig.last_run()
    assert cwd == run_rig.tmp / "sub"
    assert env["BULL_PART"] == "app"
    assert env["BULL_PART_ROOT"] == str(run_rig.tmp / "sub")
    assert env["BULL_APP_ROOT"] == str(run_rig.tmp)


def test_check_with_parts_present_and_no_part_names_the_parts(rig: CheckRig) -> None:
    add_parts(rig.app, "api", "web")
    with pytest.raises(StackError) as caught:
        rig.ops().check(rig.app)
    assert "api" in message(caught.value)
    assert "web" in message(caught.value)
    assert rig.readers.calls == []


def test_run_command_with_parts_present_and_no_part_names_the_parts(
    run_rig: RunRig,
) -> None:
    add_parts(run_rig.app, "api", "web")
    with pytest.raises(StackError) as caught:
        run_rig.ops().run_command(run_rig.app, "prune")
    assert "api" in message(caught.value)
    assert "web" in message(caught.value)
    assert [n for n, _ in run_rig.runner.calls if n == "run"] == []


def test_check_of_an_unknown_part_raises(rig: CheckRig) -> None:
    add_parts(rig.app, "api")
    with pytest.raises(StackError) as caught:
        rig.ops().check(rig.app, "ghost")
    assert "ghost" in message(caught.value)


def test_check_of_an_unknown_part_in_an_app_without_parts_raises(
    rig: CheckRig,
) -> None:
    with pytest.raises(StackError):
        rig.ops().check(rig.app, "ghost")


def test_run_command_of_an_unknown_part_raises(run_rig: RunRig) -> None:
    add_parts(run_rig.app, "api")
    with pytest.raises(StackError) as caught:
        run_rig.ops().run_command(run_rig.app, "prune", "ghost")
    assert "ghost" in message(caught.value)
    assert [n for n, _ in run_rig.runner.calls if n == "run"] == []


def test_the_implicit_app_part_exists_when_the_parts_folder_has_no_toml(
    rig: CheckRig,
) -> None:
    rig.app.parts_dir.mkdir(parents=True)
    (rig.app.parts_dir / "notes.txt").write_text("x", encoding="utf-8")
    assert failing(rig.ops().check(rig.app, "app")) == []
    assert rig.readers.calls[-1][1][0] == rig.tmp


# ------------------------------------------------ review: run_command output


def test_run_command_writes_captured_stdout_and_stderr_to_the_console(
    run_rig: RunRig, capsys: pytest.CaptureFixture[str]
) -> None:
    run_rig.runner.results[PYTHON] = RunResult(
        (PYTHON,), 4, "hello out\n", "hello err\n", 0.1
    )
    code = run_rig.ops().run_command(run_rig.app, "prune")
    captured = capsys.readouterr()
    assert code == 4
    assert captured.out == "hello out\n"
    assert captured.err == "hello err\n"


def test_run_command_with_no_output_writes_nothing(
    run_rig: RunRig, capsys: pytest.CaptureFixture[str]
) -> None:
    run_rig.ops().run_command(run_rig.app, "prune")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


# ------------------------------------------------ review: gate-step details


def test_run_command_fills_module_and_port_placeholders_with_empty_strings(
    run_rig: RunRig,
) -> None:
    run_rig.registry = registry_with(
        run_rig.home,
        commands={
            "probe": (
                "{python}",
                "{module}",
                "{module_src}",
                "{module_tests}",
                "{port}",
                "{failed_ids}",
                "end",
            )
        },
    )
    run_rig.ops().run_command(run_rig.app, "probe")
    argv, cwd, env = run_rig.last_run()
    assert argv == (PYTHON, "", "", "", "", "end")
    assert cwd == run_rig.tmp
    assert env["BULL_SCOPE_MODULE"] == ""


def test_run_command_runs_in_the_part_root_for_a_named_part(run_rig: RunRig) -> None:
    add_parts(run_rig.app, "api")
    run_rig.ops().run_command(run_rig.app, "prune", "api")
    _, cwd, _ = run_rig.last_run()
    assert cwd == run_rig.tmp / "services" / "api"


# --------------------------------------------- review: status and stack errors


def test_check_with_a_corrupt_status_file_raises_a_file_format_error(
    rig: CheckRig,
) -> None:
    rig.app.status_file.write_text("{not json", encoding="utf-8")
    with pytest.raises(FileFormatError):
        rig.ops().check(rig.app)


class NoStackSettings(FakeSettings):
    def __init__(self, stack: object) -> None:
        super().__init__(APP_VALUES)
        self.stack = stack

    def get(self, key: str, part: str | None = None) -> SettingValue:
        if key == "stack":
            return self.stack  # type: ignore[return-value]
        return super().get(key, part)


@pytest.mark.parametrize("stack", ["", None])
def test_check_without_a_stack_set_raises_a_stack_error(
    rig: CheckRig, stack: object
) -> None:
    rig.settings = NoStackSettings(stack)
    with pytest.raises(StackError):
        rig.ops().check(rig.app)


# ------------------------------------------------------ review: config edits


def test_select_keeps_comments_in_the_config(tmp_path: Path) -> None:
    app = make_app(tmp_path, "# my notes\nformat = 1  # version\n")
    ops_for(registry_with()).select(app, "fixture")
    text = app.config_file.read_text(encoding="utf-8")
    assert "# my notes" in text
    assert "format = 1  # version" in text
    assert tomllib.loads(text)["stack"] == "fixture"


def test_select_replaces_existing_stack_and_source_dir_lines_in_place(
    tmp_path: Path,
) -> None:
    app = make_app(
        tmp_path,
        'format = 1\nstack = "old"\nsource_dir = "old_src"\nmax_attempts = 5\n',
    )
    ops_for(registry_with()).select(app, "fixture")
    text = app.config_file.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert sum(ln.startswith("stack") for ln in lines) == 1
    assert sum(ln.startswith("source_dir") for ln in lines) == 1
    data = tomllib.loads(text)
    assert data["stack"] == "fixture"
    assert data["source_dir"] == "src/fx"
    assert data["max_attempts"] == 5
    assert lines[1].startswith("stack")
    assert lines[2].startswith("source_dir")


def test_select_keeps_a_comment_above_the_first_table_attached_to_it(
    tmp_path: Path,
) -> None:
    app = make_app(tmp_path, "format = 1\n\n# sandbox options\n[sandbox]\nx = 1\n")
    ops_for(registry_with()).select(app, "fixture")
    text = app.config_file.read_text(encoding="utf-8")
    assert "# sandbox options\n[sandbox]\n" in text
    data = tomllib.loads(text)
    assert data["stack"] == "fixture"
    assert data["sandbox"] == {"x": 1}


def test_select_with_invalid_toml_in_the_config_errors_and_changes_nothing(
    tmp_path: Path,
) -> None:
    app = make_app(tmp_path, "format = [\n")
    (tmp_path / ".gitignore").write_text("keep/\n", encoding="utf-8")
    with pytest.raises(BullError):
        ops_for(registry_with(gitignore=("results/",))).select(app, "fixture")
    assert app.config_file.read_text(encoding="utf-8") == "format = [\n"
    assert (tmp_path / ".gitignore").read_text(encoding="utf-8") == "keep/\n"
    assert not (tmp_path / "src").exists()


# ------------------------------------------------------- review: file modes


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_select_keeps_the_existing_files_permission_mode(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    (tmp_path / ".gitignore").write_text("keep/\n", encoding="utf-8")
    app.config_file.chmod(0o664)
    (tmp_path / ".gitignore").chmod(0o664)
    ops_for(registry_with(gitignore=("results/",))).select(app, "fixture")
    assert "results/" in (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert mode(app.config_file) == 0o664
    assert mode(tmp_path / ".gitignore") == 0o664


def test_select_gives_new_files_a_normal_mode_that_respects_the_umask(
    tmp_path: Path,
) -> None:
    app = make_app(tmp_path, config=None)
    old = os.umask(0o022)
    try:
        ops_for(registry_with(gitignore=("results/",))).select(app, "fixture")
    finally:
        os.umask(old)
    assert mode(app.config_file) == 0o644
    assert mode(tmp_path / ".gitignore") == 0o644


# ------------------------------------------------------- review: write order


def test_select_leaves_the_config_unchanged_when_a_scaffold_folder_cannot_be_made(
    tmp_path: Path,
) -> None:
    app = make_app(tmp_path)
    (tmp_path / "src").write_text("a file, not a folder", encoding="utf-8")
    before = app.config_file.read_text(encoding="utf-8")
    registry = registry_with(scaffold=("src",), gitignore=("results/",))
    with pytest.raises((OSError, BullError)):
        ops_for(registry).select(app, "fixture")
    assert app.config_file.read_text(encoding="utf-8") == before


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_select_leaves_the_config_unchanged_when_gitignore_cannot_be_written(
    tmp_path: Path,
) -> None:
    app = make_app(tmp_path)
    before = app.config_file.read_text(encoding="utf-8")
    registry = registry_with(scaffold=(), gitignore=("results/",))
    tmp_path.chmod(0o555)  # .bull stays writable; the app root does not
    try:
        with pytest.raises((OSError, BullError)):
            ops_for(registry).select(app, "fixture")
    finally:
        tmp_path.chmod(0o755)
    assert app.config_file.read_text(encoding="utf-8") == before


# ------------------------------------------------ coverage triage: select/check edges


def test_check_with_a_non_string_source_dir_fails_and_still_checks_tests(
    tmp_path: Path,
) -> None:
    rig = CheckRig(tmp_path)
    rig.make_folders(tmp_path, "src/fx", "tests")
    rig.settings = FakeSettings({**APP_VALUES, "source_dir": 3})
    items = rig.ops().check(rig.app)
    bad = failing(items)
    assert len(bad) == 1
    assert "source_dir" in bad[0].fix
    assert any(i.ok and "tests" in i.item for i in items)


def test_check_of_a_part_without_a_string_dir_raises(tmp_path: Path) -> None:
    rig = CheckRig(tmp_path)
    rig.add_part()
    rig.settings = FakeSettings(APP_VALUES, {"api": {**PART_VALUES, "dir": 3}})
    with pytest.raises(StackError):
        rig.ops().check(rig.app, "api")


def _layer(*settings: Setting, **values: SettingValue) -> StackLayer:
    return StackLayer(schema=tuple(settings), values=values)


def test_select_uses_the_schema_default_when_the_layer_values_lack_source_dir(
    tmp_path: Path,
) -> None:
    app = make_app(tmp_path)
    layer = _layer(
        Setting("source_dir", SettingType.STR, "schema_src", "s"),
        Setting("test_dir", SettingType.STR, "schema_tests", "t"),
    )
    ops_for(registry_with(settings=layer, scaffold=(), gitignore=())).select(
        app, "fixture"
    )
    data = tomllib.loads(app.config_file.read_text(encoding="utf-8"))
    assert data["source_dir"] == "schema_src"
    assert data["test_dir"] == "schema_tests"


def test_select_without_a_string_default_for_source_dir_raises_and_writes_nothing(
    tmp_path: Path,
) -> None:
    app = make_app(tmp_path)
    before = app.config_file.read_text(encoding="utf-8")
    layer = _layer(Setting("test_dir", SettingType.STR, "tests", "t"))
    with pytest.raises(StackError) as caught:
        ops_for(registry_with(settings=layer)).select(app, "fixture")
    assert "source_dir" in message(caught.value)
    assert app.config_file.read_text(encoding="utf-8") == before


def test_check_with_status_json_as_a_directory_raises_file_format_error(
    rig: CheckRig,
) -> None:
    rig.app.status_file.mkdir(parents=True)
    with pytest.raises(FileFormatError):
        rig.ops().check(rig.app)


def test_select_with_config_toml_as_a_directory_raises_file_format_error(
    tmp_path: Path,
) -> None:
    app = make_app(tmp_path, config=None)
    app.config_file.mkdir(parents=True)
    with pytest.raises(FileFormatError):
        ops_for(registry_with()).select(app, "fixture")


def test_select_with_gitignore_as_a_directory_raises_file_format_error(
    tmp_path: Path,
) -> None:
    app = make_app(tmp_path)
    (tmp_path / ".gitignore").mkdir()
    before = app.config_file.read_text(encoding="utf-8")
    with pytest.raises(FileFormatError):
        ops_for(registry_with(gitignore=("results/",))).select(app, "fixture")
    assert app.config_file.read_text(encoding="utf-8") == before


def test_select_puts_the_new_key_on_its_own_line_when_config_lacks_a_newline(
    tmp_path: Path,
) -> None:
    app = make_app(tmp_path, "format = 1")
    ops_for(registry_with(scaffold=(), gitignore=())).select(app, "fixture")
    text = app.config_file.read_text(encoding="utf-8")
    assert "format = 1\n" in text
    assert tomllib.loads(text)["stack"] == "fixture"
    assert all(len(ln.split(" = ")) == 2 for ln in text.splitlines() if ln)


def test_select_refuses_a_stack_key_set_in_a_form_it_cannot_edit(
    tmp_path: Path,
) -> None:
    original = "format = 1\nstack.x = 1\n"
    app = make_app(tmp_path, original)
    with pytest.raises(StackError):
        ops_for(registry_with(gitignore=("results/",))).select(app, "fixture")
    assert app.config_file.read_text(encoding="utf-8") == original
    assert not (tmp_path / ".gitignore").exists()
    assert not (tmp_path / "src").exists()


def test_select_write_failure_raises_leaves_no_temp_file_and_keeps_the_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = make_app(tmp_path)
    before = app.config_file.read_text(encoding="utf-8")

    def failing_replace(src: object, dst: object) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", failing_replace)
    with pytest.raises(OSError):
        ops_for(registry_with(scaffold=(), gitignore=())).select(app, "fixture")
    monkeypatch.undo()
    assert app.config_file.read_text(encoding="utf-8") == before
    assert [p.name for p in app.bull_dir.iterdir()] == ["config.toml"]


def test_select_refuses_a_stack_line_inside_a_multi_line_string(
    tmp_path: Path,
) -> None:
    original = 'format = 1\nnote = """\nstack = "x"\n"""\n'
    app = make_app(tmp_path, original)
    with pytest.raises(StackError) as caught:
        ops_for(registry_with(gitignore=("results/",))).select(app, "fixture")
    text = message(caught.value).lower()
    assert "edit" in text or "update" in text
    assert app.config_file.read_text(encoding="utf-8") == original
    assert not (tmp_path / ".gitignore").exists()
    assert not (tmp_path / "src").exists()
