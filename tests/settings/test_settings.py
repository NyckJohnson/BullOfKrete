"""Tests for `bull.Modules.settings.settings` (get, show and set across the layers).

`LiveSettings` is built only through `LiveSettingsLoader(user_file).load(...)`.
Module-internal API under test: see test_loader.py.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from bull.Modules.foundation.Contracts import AppLayout, BullError
from bull.Modules.foundation.mocks import sample_layout
from bull.Modules.settings.Contracts import (
    Layer,
    Setting,
    Settings,
    SettingType,
    StackLayer,
)
from bull.Modules.settings.loader import LiveSettingsLoader

STACK = StackLayer(
    schema=(Setting("source_dir", SettingType.STR, None, "Source folder"),),
    values={"source_dir": "src", "coverage.exclude": ("gen/*",)},
)


class Env:
    def __init__(self, tmp_path: Path) -> None:
        self.app: AppLayout = sample_layout(tmp_path / "app")
        self.user_file = tmp_path / "home" / "bull" / "config.toml"

    def write(self, path: Path, text: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def load(self, app: bool = True) -> Settings:
        return LiveSettingsLoader(self.user_file).load(
            self.app if app else None, lambda name: STACK
        )

    def part_file(self, name: str) -> Path:
        return self.app.parts_dir / f"{name}.toml"


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


# --- get -------------------------------------------------------------------


def test_get_returns_the_bull_default(env: Env) -> None:
    assert env.load().get("max_attempts") == 3


def test_get_a_models_key_returns_its_default(env: Env) -> None:
    assert env.load().get("models.reviewer") == "sonnet"
    assert env.load().get("models.code-writer") == "inherit"


def test_get_list_default_is_a_tuple(env: Env) -> None:
    assert env.load().get("bookkeeping_paths") == (".bull/", "docs/")


def test_stack_value_beats_the_bull_default(env: Env) -> None:
    env.write(env.app.config_file, 'format = 1\nstack = "python_cli"\n')
    assert env.load().get("coverage.exclude") == ("gen/*",)


def test_user_beats_bull_default(env: Env) -> None:
    env.write(env.user_file, "max_attempts = 5\n")
    assert env.load().get("max_attempts") == 5


def test_app_beats_user(env: Env) -> None:
    env.write(env.user_file, "max_attempts = 5\n")
    env.write(env.app.config_file, "format = 1\nmax_attempts = 6\n")
    assert env.load().get("max_attempts") == 6


def test_user_beats_the_stack_layer(env: Env) -> None:
    env.write(env.app.config_file, 'format = 1\nstack = "python_cli"\n')
    env.write(env.user_file, "max_attempts = 2\n")
    assert env.load().get("max_attempts") == 2


def test_part_beats_app_only_when_the_part_is_given(env: Env) -> None:
    env.write(env.app.config_file, "format = 1\nmax_attempts = 6\n")
    env.write(env.part_file("api"), "format = 1\nmax_attempts = 9\n")
    settings = env.load()
    assert settings.get("max_attempts", "api") == 9
    assert settings.get("max_attempts") == 6


def test_part_without_the_key_falls_back_to_the_app_layer(env: Env) -> None:
    env.write(env.app.config_file, "format = 1\nmax_attempts = 6\n")
    env.write(env.part_file("api"), "format = 1\n")
    assert env.load().get("max_attempts", "api") == 6


def test_implicit_part_app_reads_the_app_file(env: Env) -> None:
    env.write(env.app.config_file, "format = 1\nmax_attempts = 6\n")
    assert env.load().get("max_attempts", "app") == 6


def test_get_unknown_key_raises_bull_error(env: Env) -> None:
    with pytest.raises(BullError) as info:
        env.load().get("nope")
    assert "unknown setting `nope`" in info.value.message


# --- show ------------------------------------------------------------------


def test_show_is_sorted_by_key(env: Env) -> None:
    keys = [r.key for r in env.load().show()]
    assert keys == sorted(keys)
    assert {"base_branch", "max_attempts", "review_mode"} <= set(keys)


def test_show_reports_the_layer_and_source_of_each_value(env: Env) -> None:
    app = env.write(env.app.config_file, "format = 1\nmax_attempts = 6\n")
    user = env.write(env.user_file, "review_mode = 'split'\n")
    by_key = {r.key: r for r in env.load().show()}
    assert (by_key["max_attempts"].value, by_key["max_attempts"].layer) == (
        6,
        Layer.APP,
    )
    assert by_key["max_attempts"].source == app
    assert by_key["review_mode"].layer is Layer.USER
    assert by_key["review_mode"].source == user
    assert by_key["max_files_per_unit"].layer is Layer.BULL
    assert by_key["max_files_per_unit"].value == 4


def test_show_marks_stack_values(env: Env) -> None:
    env.write(env.app.config_file, 'format = 1\nstack = "python_cli"\n')
    by_key = {r.key: r for r in env.load().show()}
    assert by_key["source_dir"].layer is Layer.STACK
    assert by_key["source_dir"].value == "src"


def test_stack_exclude_and_app_exclude_extra_both_resolve_from_one_load(
    env: Env,
) -> None:
    app = env.write(
        env.app.config_file,
        'format = 1\nstack = "python_cli"\ncoverage.exclude_extra = ["extra/*"]\n',
    )
    settings = env.load()
    by_key = {r.key: r for r in settings.show()}
    assert settings.get("coverage.exclude") == ("gen/*",)
    assert by_key["coverage.exclude"].layer is Layer.STACK
    assert settings.get("coverage.exclude_extra") == ("extra/*",)
    assert by_key["coverage.exclude_extra"].layer is Layer.APP
    assert by_key["coverage.exclude_extra"].source == app


def test_show_includes_a_set_models_key(env: Env) -> None:
    env.write(env.app.config_file, "format = 1\nmodels.reviewer = 'opus'\n")
    by_key = {r.key: r for r in env.load().show()}
    assert by_key["models.reviewer"].value == "opus"
    assert by_key["models.reviewer"].layer is Layer.APP


def test_show_with_a_part_includes_the_part_layer(env: Env) -> None:
    env.write(env.part_file("api"), "format = 1\nmax_attempts = 9\n")
    settings = env.load()
    with_part = {r.key: r for r in settings.show("api")}
    without = {r.key: r for r in settings.show()}
    assert with_part["max_attempts"].layer is Layer.PART
    assert with_part["max_attempts"].source == env.part_file("api")
    assert without["max_attempts"].layer is Layer.BULL


# --- set -------------------------------------------------------------------


def test_set_app_writes_the_app_file_and_returns_the_resolved_value(env: Env) -> None:
    resolved = env.load().set("max_attempts", "5")
    assert (resolved.key, resolved.value, resolved.layer) == (
        "max_attempts",
        5,
        Layer.APP,
    )
    assert resolved.source == env.app.config_file
    data = tomllib.loads(env.app.config_file.read_text())
    assert data["max_attempts"] == 5


def test_set_creates_a_missing_file_with_format_1(env: Env) -> None:
    assert not env.app.config_file.exists()
    env.load().set("max_attempts", "5")
    assert tomllib.loads(env.app.config_file.read_text())["format"] == 1


def test_set_user_writes_the_user_file(env: Env) -> None:
    resolved = env.load().set("max_attempts", "2", Layer.USER)
    assert resolved.layer is Layer.USER
    assert resolved.source == env.user_file
    assert tomllib.loads(env.user_file.read_text())["max_attempts"] == 2
    assert not env.app.config_file.exists()


def test_set_part_writes_the_part_file(env: Env) -> None:
    resolved = env.load().set("max_attempts", "8", Layer.PART, "api")
    assert resolved.layer is Layer.PART
    assert resolved.source == env.part_file("api")
    data = tomllib.loads(env.part_file("api").read_text())
    assert (data["format"], data["max_attempts"]) == (1, 8)


def test_set_part_layer_without_a_part_is_a_bull_error(env: Env) -> None:
    with pytest.raises(BullError):
        env.load().set("max_attempts", "8", Layer.PART)


def test_set_keeps_other_lines_and_comments(env: Env) -> None:
    env.write(
        env.app.config_file,
        "format = 1\n# keep me\nmax_attempts = 3  # inline\n\nreview_mode = 'split'\n",
    )
    env.load().set("max_attempts", "4")
    assert env.app.config_file.read_text() == (
        "format = 1\n# keep me\nmax_attempts = 4  # inline\n\nreview_mode = 'split'\n"
    )


def test_set_appends_a_missing_key(env: Env) -> None:
    env.write(env.app.config_file, "format = 1\n")
    env.load().set("usage.pause_5h", "70")
    assert tomllib.loads(env.app.config_file.read_text())["usage"]["pause_5h"] == 70


def test_set_is_visible_to_a_later_get_and_show(env: Env) -> None:
    settings = env.load()
    settings.set("max_attempts", "5")
    assert settings.get("max_attempts") == 5
    by_key = {r.key: r for r in settings.show()}
    assert by_key["max_attempts"].value == 5
    assert by_key["max_attempts"].layer is Layer.APP


def test_set_part_is_visible_to_a_later_get_with_that_part(env: Env) -> None:
    settings = env.load()
    settings.set("max_attempts", "8", Layer.PART, "api")
    assert settings.get("max_attempts", "api") == 8
    assert settings.get("max_attempts") == 3


def test_set_user_is_visible_to_a_later_get(env: Env) -> None:
    settings = env.load()
    settings.set("max_attempts", "2", Layer.USER)
    assert settings.get("max_attempts") == 2


def test_set_the_written_file_loads_again(env: Env) -> None:
    env.load().set("review_mode", "split")
    assert env.load().get("review_mode") == "split"


def test_set_rejects_a_non_integer_with_the_exact_message(env: Env) -> None:
    with pytest.raises(BullError) as info:
        env.load().set("max_attempts", "many")
    assert info.value.message == "max_attempts must be an integer ≥ 1"


def test_set_invalid_value_writes_nothing(env: Env) -> None:
    with pytest.raises(BullError):
        env.load().set("max_attempts", "many")
    assert not env.app.config_file.exists()


def test_set_out_of_range_is_rejected(env: Env) -> None:
    with pytest.raises(BullError):
        env.load().set("usage.pause_5h", "101")


def test_set_bad_choice_is_rejected(env: Env) -> None:
    with pytest.raises(BullError) as info:
        env.load().set("review_mode", "bogus")
    assert "combined" in info.value.message


def test_set_unknown_key_is_a_bull_error(env: Env) -> None:
    with pytest.raises(BullError) as info:
        env.load().set("nope", "1")
    assert "unknown setting `nope`" in info.value.message


@pytest.mark.parametrize(
    ("key", "layer"),
    [
        ("stack", Layer.USER),
        ("base_branch", Layer.PART),
        ("usage.pause_5h", Layer.PART),
        ("coverage.exclude", Layer.USER),
    ],
)
def test_set_in_a_disallowed_layer_is_a_bull_error(
    env: Env, key: str, layer: Layer
) -> None:
    with pytest.raises(BullError):
        env.load().set(key, "x", layer, "api")


def test_set_never_writes_the_bull_default_layer(env: Env) -> None:
    with pytest.raises(BullError):
        env.load().set("max_attempts", "5", Layer.BULL)


def test_set_a_string_is_quoted_correctly(env: Env) -> None:
    env.load().set("base_branch", 'ma"in')
    assert tomllib.loads(env.app.config_file.read_text())["base_branch"] == 'ma"in'


def test_set_a_list_is_comma_separated(env: Env) -> None:
    settings = env.load()
    resolved = settings.set("bookkeeping_paths", "a/, b/")
    assert resolved.value == ("a/", "b/")
    assert tomllib.loads(env.app.config_file.read_text())["bookkeeping_paths"] == [
        "a/",
        "b/",
    ]
    assert settings.get("bookkeeping_paths") == ("a/", "b/")


def test_set_a_stack_key_is_validated_by_the_stack_schema(env: Env) -> None:
    env.write(env.app.config_file, 'format = 1\nstack = "python_cli"\n')
    resolved = env.load().set("source_dir", "lib")
    assert resolved.value == "lib"
    assert tomllib.loads(env.app.config_file.read_text())["source_dir"] == "lib"


def test_schema_lists_bull_and_stack_keys(env: Env) -> None:
    env.write(env.app.config_file, 'format = 1\nstack = "python_cli"\n')
    keys = {s.key for s in env.load().schema()}
    assert {"max_attempts", "source_dir"} <= keys


# --- unset keys and stack defaults -----------------------------------------


def test_get_a_known_key_that_nothing_sets_is_a_bull_error_with_a_fix(
    env: Env,
) -> None:
    with pytest.raises(BullError) as info:
        env.load().get("stack")
    assert "stack" in info.value.message
    assert info.value.fix


def test_a_stack_default_for_a_stack_key_is_reported_with_the_stack_layer(
    env: Env,
) -> None:
    stack = StackLayer(
        schema=(Setting("jobs", SettingType.INT, 4, "Parallel jobs"),), values={}
    )
    env.write(env.app.config_file, 'format = 1\nstack = "s"\n')
    settings = LiveSettingsLoader(env.user_file).load(env.app, lambda name: stack)
    assert settings.get("jobs") == 4
    by_key = {r.key: r for r in settings.show()}
    assert by_key["jobs"].value == 4
    assert by_key["jobs"].layer is Layer.STACK
    assert by_key["jobs"].source is None


# --- set without an app, or on an unusable target --------------------------


def test_set_in_the_app_layer_without_an_app_is_a_bull_error(env: Env) -> None:
    with pytest.raises(BullError) as info:
        env.load(app=False).set("max_attempts", "5", Layer.APP)
    assert "app" in info.value.message


def test_set_in_a_part_layer_without_an_app_is_a_bull_error(env: Env) -> None:
    with pytest.raises(BullError):
        env.load(app=False).set("max_attempts", "5", Layer.PART, part="x")


def test_set_when_the_target_is_a_directory_is_a_cannot_read_error(env: Env) -> None:
    settings = env.load()
    env.app.config_file.mkdir(parents=True)
    with pytest.raises(BullError) as info:
        settings.set("max_attempts", "5")
    assert "cannot read" in info.value.message
    assert env.app.config_file.is_dir()


def test_set_when_the_target_is_not_utf8_leaves_it_untouched(env: Env) -> None:
    settings = env.load()
    env.app.config_file.parent.mkdir(parents=True, exist_ok=True)
    raw = b"format = 1\n# \xff\xfe\n"
    env.app.config_file.write_bytes(raw)
    with pytest.raises(BullError) as info:
        settings.set("max_attempts", "5")
    assert "cannot read" in info.value.message
    assert env.app.config_file.read_bytes() == raw


# --- atomic write failures -------------------------------------------------


def _fail_replace(exc: BaseException, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise exc

    monkeypatch.setattr("os.replace", boom)


def test_set_failing_to_replace_leaves_the_original_and_no_temp_file(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = "format = 1\nmax_attempts = 3\n"
    env.write(env.app.config_file, original)
    settings = env.load()
    _fail_replace(OSError(28, "No space left on device"), monkeypatch)
    with pytest.raises(BullError):
        settings.set("max_attempts", "5")
    assert env.app.config_file.read_text() == original
    assert [p.name for p in env.app.config_file.parent.iterdir()] == ["config.toml"]


def test_set_with_an_uncreatable_parent_folder_is_a_bull_error(env: Env) -> None:
    settings = env.load()
    blocker = env.user_file.parent
    blocker.parent.mkdir(parents=True, exist_ok=True)
    blocker.write_text("i am a file, not a folder")
    with pytest.raises(BullError):
        settings.set("max_attempts", "5", Layer.USER)
    assert blocker.read_text() == "i am a file, not a folder"


def test_set_interrupted_while_replacing_cleans_up_and_propagates(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = "format = 1\n"
    env.write(env.app.config_file, original)
    settings = env.load()
    _fail_replace(KeyboardInterrupt(), monkeypatch)
    with pytest.raises(KeyboardInterrupt):
        settings.set("max_attempts", "5")
    assert env.app.config_file.read_text() == original
    assert [p.name for p in env.app.config_file.parent.iterdir()] == ["config.toml"]
