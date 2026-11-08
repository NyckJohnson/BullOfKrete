"""Tests for `bull.Modules.settings.loader` (reading and validating the settings files).

Module-internal API under test (defined by these tests, for the code-writer):
    LiveSettingsLoader(user_file: Path | None = None)
        `user_file` is the user config file; None means
        `$XDG_CONFIG_HOME/bull/config.toml`, else `~/.config/bull/config.toml`.
    LiveSettingsLoader.load(app, stack_layer) -> Settings
        Raises ConfigError (problems: file, line, key, message) for every problem found.
        A stack layer is requested (by stack name) only for a stack named in the app file
        or in a part file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bull.Modules.foundation.Contracts import AppLayout, BullError
from bull.Modules.foundation.mocks import sample_layout
from bull.Modules.settings.Contracts import (
    ConfigError,
    ConfigProblem,
    Setting,
    SettingType,
    StackLayer,
)
from bull.Modules.settings.loader import LiveSettingsLoader
from bull.Modules.settings.schema import BULL_SCHEMA


class Env:
    """A temp app folder, a user file location and a recording stack_layer."""

    def __init__(self, tmp_path: Path) -> None:
        self.app: AppLayout = sample_layout(tmp_path / "app")
        self.user_file = tmp_path / "home" / "bull" / "config.toml"
        self.stacks: dict[str, StackLayer] = {}
        self.requested: list[str] = []

    def stack_layer(self, name: str) -> StackLayer:
        self.requested.append(name)
        return self.stacks[name]

    def write(self, path: Path, text: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def user(self, text: str) -> Path:
        return self.write(self.user_file, text)

    def app_file(self, text: str) -> Path:
        return self.write(self.app.config_file, text)

    def part(self, name: str, text: str) -> Path:
        return self.write(self.app.parts_dir / f"{name}.toml", text)

    def load(self) -> object:
        return LiveSettingsLoader(self.user_file).load(self.app, self.stack_layer)

    def problems(self) -> list[ConfigProblem]:
        with pytest.raises(ConfigError) as info:
            self.load()
        return info.value.problems


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


SOURCE_DIR = Setting("source_dir", SettingType.STR, None, "Source folder")
TEST_DIR = Setting("test_dir", SettingType.STR, None, "Test folder")


def stack_with(**values: str) -> StackLayer:
    return StackLayer(schema=(SOURCE_DIR, TEST_DIR), values=dict(values))


# --- reading the files -----------------------------------------------------


def test_load_with_no_files_gives_the_bull_defaults(env: Env) -> None:
    settings = env.load()
    assert settings.get("max_attempts") == 3  # type: ignore[attr-defined]
    assert settings.get("base_branch") == "main"  # type: ignore[attr-defined]


def test_load_without_an_app_reads_only_the_user_file(env: Env) -> None:
    env.user("max_attempts = 6\n")
    settings = LiveSettingsLoader(env.user_file).load(None, env.stack_layer)
    assert settings.get("max_attempts") == 6
    assert env.requested == []


def test_load_reads_the_user_file(env: Env) -> None:
    env.user("max_files_per_unit = 9\n")
    assert env.load().get("max_files_per_unit") == 9  # type: ignore[attr-defined]


def test_load_reads_the_app_file(env: Env) -> None:
    env.app_file("format = 1\nmax_attempts = 5\n")
    assert env.load().get("max_attempts") == 5  # type: ignore[attr-defined]


def test_load_accepts_a_missing_user_file(env: Env) -> None:
    env.app_file("format = 1\n")
    assert not env.user_file.exists()
    assert env.load().get("max_attempts") == 3  # type: ignore[attr-defined]


def test_default_user_file_is_under_xdg_config_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    xdg = tmp_path / "xdg"
    (xdg / "bull").mkdir(parents=True)
    (xdg / "bull" / "config.toml").write_text("max_attempts = 8\n")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    monkeypatch.setenv("HOME", str(tmp_path / "nohome"))
    settings = LiveSettingsLoader().load(None, lambda name: stack_with())
    assert settings.get("max_attempts") == 8


def test_default_user_file_falls_back_to_home_dot_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    (home / ".config" / "bull").mkdir(parents=True)
    (home / ".config" / "bull" / "config.toml").write_text("max_attempts = 7\n")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(home))
    settings = LiveSettingsLoader().load(None, lambda name: stack_with())
    assert settings.get("max_attempts") == 7


def test_dotted_keys_are_accepted(env: Env) -> None:
    env.app_file("format = 1\nusage.pause_5h = 70\nmodels.reviewer = 'opus'\n")
    settings = env.load()
    assert settings.get("usage.pause_5h") == 70  # type: ignore[attr-defined]
    assert settings.get("models.reviewer") == "opus"  # type: ignore[attr-defined]


def test_table_form_is_accepted(env: Env) -> None:
    env.app_file("format = 1\n[usage]\npause_5h = 70\n[models]\nreviewer = 'opus'\n")
    settings = env.load()
    assert settings.get("usage.pause_5h") == 70  # type: ignore[attr-defined]
    assert settings.get("models.reviewer") == "opus"  # type: ignore[attr-defined]


def test_format_is_not_a_setting(env: Env) -> None:
    env.app_file("format = 1\n")
    settings = env.load()
    assert "format" not in [s.key for s in settings.schema()]  # type: ignore[attr-defined]
    assert "format" not in [r.key for r in settings.show()]  # type: ignore[attr-defined]


# --- stacks ----------------------------------------------------------------


def test_one_part_app_asks_for_the_stack_named_in_the_app_file(env: Env) -> None:
    env.stacks["python_cli"] = stack_with(source_dir="src")
    env.app_file('format = 1\nstack = "python_cli"\n')
    settings = env.load()
    assert env.requested == ["python_cli"]
    assert settings.get("source_dir") == "src"  # type: ignore[attr-defined]


def test_app_without_a_stack_asks_for_no_stack_layer(env: Env) -> None:
    env.app_file("format = 1\n")
    env.load()
    assert env.requested == []


def test_each_part_file_supplies_its_own_stack(env: Env) -> None:
    env.stacks["alpha"] = stack_with(source_dir="a-src")
    env.stacks["beta"] = stack_with(source_dir="b-src")
    env.app_file("format = 1\n")
    env.part("api", 'format = 1\nstack = "alpha"\ndir = "api"\n')
    env.part("web", 'format = 1\nstack = "beta"\ndir = "web"\n')
    settings = env.load()
    assert sorted(env.requested) == ["alpha", "beta"]
    assert settings.get("source_dir", "api") == "a-src"  # type: ignore[attr-defined]
    assert settings.get("source_dir", "web") == "b-src"  # type: ignore[attr-defined]


def test_stack_settings_extend_the_schema(env: Env) -> None:
    env.stacks["python_cli"] = stack_with(source_dir="src")
    env.app_file('format = 1\nstack = "python_cli"\n')
    keys = {s.key for s in env.load().schema()}  # type: ignore[attr-defined]
    assert {"source_dir", "test_dir"} <= keys


def test_schema_holds_every_bull_key(env: Env) -> None:
    env.app_file("format = 1\n")
    keys = {s.key for s in env.load().schema()}  # type: ignore[attr-defined]
    assert {s.key for s in BULL_SCHEMA} <= keys


def test_stack_keys_may_be_set_in_the_app_file(env: Env) -> None:
    env.stacks["python_cli"] = stack_with(source_dir="src")
    env.app_file('format = 1\nstack = "python_cli"\nsource_dir = "lib"\n')
    assert env.load().get("source_dir") == "lib"  # type: ignore[attr-defined]


# --- problems --------------------------------------------------------------


def test_unknown_key_is_a_problem_with_its_line(env: Env) -> None:
    path = env.app_file("format = 1\nmax_attempts = 3\nbogus = 1\n")
    [problem] = env.problems()
    assert problem.file == path
    assert problem.line == 3
    assert problem.key == "bogus"
    assert "unknown setting `bogus`" in problem.message


def test_unknown_key_in_table_form_points_at_its_assignment(env: Env) -> None:
    env.app_file("format = 1\n[bogus]\nthing = 1\n")
    [problem] = env.problems()
    assert problem.key == "bogus.thing"
    assert problem.line == 3


def test_config_error_message_is_a_bull_error(env: Env) -> None:
    env.app_file("format = 1\nbogus = 1\n")
    with pytest.raises(BullError):
        env.load()


def test_wrong_type_names_the_expected_type(env: Env) -> None:
    path = env.app_file('format = 1\nmax_attempts = "three"\n')
    [problem] = env.problems()
    assert (problem.file, problem.line, problem.key) == (path, 2, "max_attempts")
    assert "integer" in problem.message


def test_a_boolean_is_not_an_integer(env: Env) -> None:
    env.app_file("format = 1\nmax_attempts = true\n")
    [problem] = env.problems()
    assert problem.key == "max_attempts"
    assert "integer" in problem.message


def test_int_below_the_minimum_is_a_problem_naming_the_range(env: Env) -> None:
    env.app_file("format = 1\nmax_attempts = 0\n")
    [problem] = env.problems()
    assert problem.key == "max_attempts"
    assert "≥ 1" in problem.message


@pytest.mark.parametrize("value", [0, 101])
def test_int_outside_a_range_names_both_ends(env: Env, value: int) -> None:
    env.app_file(f"format = 1\nusage.pause_5h = {value}\n")
    [problem] = env.problems()
    assert problem.key == "usage.pause_5h"
    assert "1" in problem.message and "100" in problem.message


def test_bad_choice_names_the_choices(env: Env) -> None:
    env.app_file('format = 1\nreview_mode = "bogus"\n')
    [problem] = env.problems()
    assert problem.key == "review_mode"
    assert "combined" in problem.message and "split" in problem.message


def test_list_setting_given_a_string_is_a_problem(env: Env) -> None:
    env.app_file('format = 1\nbookkeeping_paths = "docs/"\n')
    [problem] = env.problems()
    assert problem.key == "bookkeeping_paths"
    assert "list" in problem.message


def test_stack_key_of_the_wrong_type_is_a_problem(env: Env) -> None:
    env.stacks["python_cli"] = stack_with(source_dir="src")
    env.app_file('format = 1\nstack = "python_cli"\nsource_dir = 5\n')
    [problem] = env.problems()
    assert problem.key == "source_dir"


def test_stack_key_in_the_user_file_is_in_a_disallowed_layer(env: Env) -> None:
    env.user('stack = "python_cli"\n')
    [problem] = env.problems()
    assert (problem.file, problem.line, problem.key) == (env.user_file, 1, "stack")


@pytest.mark.parametrize(
    ("text", "key"),
    [
        ("coverage.exclude = []\n", "coverage.exclude"),
        ('reference_dir = "ref"\n', "reference_dir"),
        ("max_attempts = 4\ndir = 'x'\n", "dir"),
    ],
)
def test_keys_in_a_layer_that_forbids_them_are_problems(
    env: Env, text: str, key: str
) -> None:
    env.user(text)
    assert [p.key for p in env.problems()] == [key]


def test_a_user_only_key_in_a_part_file_is_a_problem(env: Env) -> None:
    env.stacks["python_cli"] = stack_with()
    env.app_file("format = 1\n")
    path = env.part("api", 'format = 1\nstack = "python_cli"\nusage.pause_5h = 50\n')
    [problem] = env.problems()
    assert (problem.file, problem.key) == (path, "usage.pause_5h")


def test_part_only_key_in_the_app_file_is_a_problem(env: Env) -> None:
    env.app_file("format = 1\ndir = 'x'\n")
    assert [p.key for p in env.problems()] == ["dir"]


def test_app_file_without_format_is_a_problem(env: Env) -> None:
    path = env.app_file("max_attempts = 3\n")
    [problem] = env.problems()
    assert (problem.file, problem.key) == (path, "format")


def test_part_file_without_format_is_a_problem(env: Env) -> None:
    env.stacks["python_cli"] = stack_with()
    env.app_file("format = 1\n")
    path = env.part("api", 'stack = "python_cli"\n')
    [problem] = env.problems()
    assert (problem.file, problem.key) == (path, "format")


def test_every_problem_in_every_file_is_collected_into_one_error(env: Env) -> None:
    env.stacks["python_cli"] = stack_with()
    user = env.user('stack = "x"\nbogus = 1\n')
    app = env.app_file("max_attempts = 0\n")
    part = env.part("api", 'stack = "python_cli"\nreview_mode = "no"\n')
    found = {(p.file, p.key) for p in env.problems()}
    assert found == {
        (user, "stack"),
        (user, "bogus"),
        (app, "max_attempts"),
        (app, "format"),
        (part, "review_mode"),
        (part, "format"),
    }
