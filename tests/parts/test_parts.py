"""Tests for `bull.Modules.parts.parts` (LiveParts).

Shape chosen here (for the code-writer): `LiveParts(registry, loader)` with
`registry: StackRegistry` (stack existence, scaffold, gitignore, test_glob, stack
defaults) and `loader: SettingsLoader` (`loader.load(app, stack_layer).get("source_dir" |
"test_dir", part_name)` gives each part's folders; the implicit part is asked for as
`"app"` or `None`). Part files, config.toml and .gitignore are read and written on disk.
"""

from __future__ import annotations

import os
import shutil
import tomllib
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from bull.Modules.foundation.Contracts import AppLayout, BullError
from bull.Modules.parts.Contracts import Part
from bull.Modules.parts.parts import LiveParts
from bull.Modules.stacks.mocks import MockStackRegistry

from .fakes import loader_with, new_app, write_part


def make(overrides: dict[str, dict[str, Any]] | None = None) -> LiveParts:
    return LiveParts(MockStackRegistry(), loader_with(overrides))


def toml_of(path: Path) -> dict[str, Any]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


# ------------------------------------------------------------------- all


def test_all_is_empty_without_parts_or_a_stack(tmp_path: Path) -> None:
    app = new_app(tmp_path, config="format = 1\n")
    assert make().all(app) == []


def test_all_is_empty_without_a_config_file(tmp_path: Path) -> None:
    app = new_app(tmp_path, config=None)
    assert make().all(app) == []


def test_all_gives_one_implicit_part_when_config_has_a_stack(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    (part,) = make().all(app)
    assert part == Part(
        name="app",
        stack="fixture",
        dir=".",
        root=app.root,
        source_dir=Path("src/fx"),
        test_dir=Path("tests"),
    )


def test_all_lists_part_files_sorted_by_name(tmp_path: Path) -> None:
    app = new_app(tmp_path, config="format = 1\n")
    write_part(app, "web")
    write_part(app, "api")
    write_part(app, "core")
    assert [p.name for p in make().all(app)] == ["api", "core", "web"]


def test_part_files_win_over_the_implicit_part(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    write_part(app, "web")
    assert [p.name for p in make().all(app)] == ["web"]


def test_part_reads_stack_and_dir_from_its_file(tmp_path: Path) -> None:
    app = new_app(tmp_path, config="format = 1\n")
    write_part(app, "web", stack="python_cli", dir="sites/w")
    (part,) = make().all(app)
    assert part.stack == "python_cli"
    assert part.dir == "sites/w"
    assert part.root == app.root / "sites/w"


def test_part_folders_come_from_that_parts_settings(tmp_path: Path) -> None:
    app = new_app(tmp_path, config="format = 1\n")
    write_part(app, "web")
    live = make({"web": {"source_dir": "lib/w", "test_dir": "spec"}})
    (part,) = live.all(app)
    assert part.source_dir == Path("lib/w")
    assert part.test_dir == Path("spec")


def test_implicit_part_folders_come_from_app_settings(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    live = make({"app": {"source_dir": "lib/x", "test_dir": "spec"}})
    (part,) = live.all(app)
    assert part.source_dir == Path("lib/x")
    assert part.test_dir == Path("spec")


# ------------------------------------------------------------------- get


def test_get_without_a_name_returns_the_only_part(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    assert make().get(app).name == "app"


def test_get_without_a_name_returns_the_single_part_file(tmp_path: Path) -> None:
    app = new_app(tmp_path, config="format = 1\n")
    write_part(app, "web")
    assert make().get(app).name == "web"


def test_get_without_a_name_and_several_parts_says_which(tmp_path: Path) -> None:
    app = new_app(tmp_path, config="format = 1\n")
    write_part(app, "web")
    write_part(app, "api")
    with pytest.raises(BullError) as raised:
        make().get(app)
    assert "say which part: api, web" in raised.value.message


def test_get_by_name_returns_that_part(tmp_path: Path) -> None:
    app = new_app(tmp_path, config="format = 1\n")
    write_part(app, "web")
    write_part(app, "api")
    assert make().get(app, "web").name == "web"


def test_get_unknown_name_raises(tmp_path: Path) -> None:
    app = new_app(tmp_path, config="format = 1\n")
    write_part(app, "web")
    with pytest.raises(BullError) as raised:
        make().get(app, "nope")
    assert "nope" in raised.value.message


def test_get_without_any_part_raises(tmp_path: Path) -> None:
    app = new_app(tmp_path, config="format = 1\n")
    with pytest.raises(BullError):
        make().get(app)


# ------------------------------------------------------------------- add


def test_add_writes_the_part_file_with_stack_defaults(tmp_path: Path) -> None:
    app = new_app(tmp_path, config="format = 1\n")
    part = make().add(app, "web", "fixture")
    data = toml_of(app.parts_dir / "web.toml")
    assert data["format"] == 1
    assert data["stack"] == "fixture"
    assert data["dir"] == "web"
    assert data["source_dir"] == "src/fx"
    assert data["test_dir"] == "tests"
    assert part.name == "web"
    assert part.stack == "fixture"
    assert part.root == app.root / "web"


def test_add_dir_defaults_to_the_name(tmp_path: Path) -> None:
    app = new_app(tmp_path, config="format = 1\n")
    assert make().add(app, "web", "fixture").dir == "web"


def test_add_uses_an_explicit_dir(tmp_path: Path) -> None:
    app = new_app(tmp_path, config="format = 1\n")
    part = make().add(app, "web", "fixture", "sites/w")
    assert part.dir == "sites/w"
    assert part.root == app.root / "sites/w"
    assert toml_of(app.parts_dir / "web.toml")["dir"] == "sites/w"


def test_add_creates_the_scaffold_folders(tmp_path: Path) -> None:
    app = new_app(tmp_path, config="format = 1\n")
    make().add(app, "web", "fixture")
    assert (app.root / "web" / "src").is_dir()
    assert (app.root / "web" / "tests").is_dir()


def test_add_returns_a_part_that_all_then_lists(tmp_path: Path) -> None:
    app = new_app(tmp_path, config="format = 1\n")
    live = make()
    part = live.add(app, "web", "fixture")
    assert live.all(app) == [part]


def test_add_merges_the_stacks_gitignore_lines_under_the_folder(
    tmp_path: Path,
) -> None:
    app = new_app(tmp_path, config="format = 1\n", gitignore="node_modules/\n")
    make().add(app, "web", "fixture")
    lines = (app.root / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "node_modules/" in lines
    assert "web/results/" in lines


def test_add_creates_gitignore_when_missing(tmp_path: Path) -> None:
    app = new_app(tmp_path, config="format = 1\n")
    make().add(app, "web", "fixture", "sites/w")
    lines = (app.root / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "sites/w/results/" in lines


def test_add_does_not_duplicate_gitignore_lines(tmp_path: Path) -> None:
    app = new_app(tmp_path, config="format = 1\n", gitignore="web/results/\n")
    make().add(app, "web", "fixture")
    lines = (app.root / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert lines.count("web/results/") == 1


def test_add_second_part_keeps_the_first_parts_file(tmp_path: Path) -> None:
    app = new_app(tmp_path, config="format = 1\n")
    live = make()
    live.add(app, "api", "fixture")
    live.add(app, "web", "fixture")
    assert [p.name for p in live.all(app)] == ["api", "web"]
    assert toml_of(app.parts_dir / "api.toml")["dir"] == "api"


@pytest.mark.parametrize("name", ["Web", "1web", "we-b", "we b", "", "_web", "web!"])
def test_add_rejects_bad_names(tmp_path: Path, name: str) -> None:
    app = new_app(tmp_path, config="format = 1\n")
    with pytest.raises(BullError):
        make().add(app, name, "fixture")
    assert not app.parts_dir.exists() or not list(app.parts_dir.iterdir())


@pytest.mark.parametrize("name", ["w", "web", "web_2", "a1"])
def test_add_accepts_good_names(tmp_path: Path, name: str) -> None:
    app = new_app(tmp_path, config="format = 1\n")
    assert make().add(app, name, "fixture").name == name


def test_add_rejects_an_existing_name(tmp_path: Path) -> None:
    app = new_app(tmp_path, config="format = 1\n")
    live = make()
    live.add(app, "web", "fixture")
    with pytest.raises(BullError):
        live.add(app, "web", "fixture", "other")


def test_add_rejects_the_name_of_the_implicit_part(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    with pytest.raises(BullError):
        make().add(app, "app", "fixture", "other")


def test_add_rejects_an_unknown_stack_and_writes_nothing(tmp_path: Path) -> None:
    app = new_app(tmp_path, config="format = 1\n")
    with pytest.raises(BullError):
        make().add(app, "web", "no_such_stack")
    assert not (app.parts_dir / "web.toml").exists()
    assert not (app.root / "web").exists()


@pytest.mark.parametrize("folder", ["/abs/place", "../outside", "a/../../outside"])
def test_add_rejects_dirs_that_are_absolute_or_outside_the_app(
    tmp_path: Path, folder: str
) -> None:
    app = new_app(tmp_path, config="format = 1\n")
    with pytest.raises(BullError):
        make().add(app, "web", "fixture", folder)
    assert not (app.parts_dir / "web.toml").exists()


def test_add_rejects_the_same_dir_as_another_part(tmp_path: Path) -> None:
    app = new_app(tmp_path, config="format = 1\n")
    live = make()
    live.add(app, "api", "fixture", "shared")
    with pytest.raises(BullError):
        live.add(app, "web", "fixture", "shared")


@pytest.mark.parametrize(("first", "second"), [("web", "web/sub"), ("web/sub", "web")])
def test_add_rejects_nested_dirs(tmp_path: Path, first: str, second: str) -> None:
    app = new_app(tmp_path, config="format = 1\n")
    live = make()
    live.add(app, "api", "fixture", first)
    with pytest.raises(BullError):
        live.add(app, "web", "fixture", second)


def test_add_allows_sibling_dirs_with_a_common_prefix(tmp_path: Path) -> None:
    app = new_app(tmp_path, config="format = 1\n")
    live = make()
    live.add(app, "api", "fixture", "web")
    assert live.add(app, "web2", "fixture", "web2").dir == "web2"


def test_add_allows_a_root_part_beside_a_part_outside_its_folders(
    tmp_path: Path,
) -> None:
    app = new_app(tmp_path, config="format = 1\n")
    live = make()
    live.add(app, "web", "fixture", "web")
    part = live.add(app, "core", "fixture", ".")
    assert part.root == app.root
    assert {p.name for p in live.all(app)} == {"core", "web"}


@pytest.mark.parametrize("folder", ["src/fx/inner", "tests", "tests/deep"])
def test_add_rejects_a_dir_inside_the_root_parts_source_or_test_folder(
    tmp_path: Path, folder: str
) -> None:
    app = new_app(tmp_path)
    with pytest.raises(BullError):
        make().add(app, "web", "fixture", folder)
    assert not (app.parts_dir / "web.toml").exists()


# ------------------------------------------------- add on the implicit part


def test_add_moves_the_implicit_part_into_app_toml(tmp_path: Path) -> None:
    app = new_app(
        tmp_path,
        config='format = 1\nstack = "fixture"\nsource_dir = "lib/x"\n'
        'test_dir = "spec"\nbase_branch = "trunk"\n',
    )
    make().add(app, "web", "fixture")
    moved = toml_of(app.parts_dir / "app.toml")
    assert moved["format"] == 1
    assert moved["stack"] == "fixture"
    assert moved["dir"] == "."
    assert moved["source_dir"] == "lib/x"
    assert moved["test_dir"] == "spec"
    config = toml_of(app.config_file)
    assert "stack" not in config
    assert "source_dir" not in config
    assert "test_dir" not in config
    assert config["base_branch"] == "trunk"
    assert config["format"] == 1


def test_add_after_the_move_lists_both_parts(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    live = make()
    live.add(app, "web", "fixture")
    parts = live.all(app)
    assert [p.name for p in parts] == ["app", "web"]
    assert parts[0].dir == "."
    assert parts[0].root == app.root


def test_add_without_an_implicit_part_leaves_config_alone(tmp_path: Path) -> None:
    app = new_app(tmp_path, config='format = 1\nbase_branch = "trunk"\n')
    before = app.config_file.read_text(encoding="utf-8")
    make().add(app, "web", "fixture")
    assert app.config_file.read_text(encoding="utf-8") == before
    assert not (app.parts_dir / "app.toml").exists()


# ----------------------------------------------------------------- check


def _ready(app: AppLayout, *names: str) -> LiveParts:
    live = make()
    for name in names:
        live.add(app, name, "fixture")
    return live


def test_check_is_clean_for_a_healthy_app(tmp_path: Path) -> None:
    app = new_app(tmp_path, config="format = 1\n")
    live = _ready(app, "api", "web")
    assert live.check(app) == []


def test_check_is_clean_with_no_parts(tmp_path: Path) -> None:
    app = new_app(tmp_path, config="format = 1\n")
    assert make().check(app) == []


def test_check_reports_overlapping_folders_once(tmp_path: Path) -> None:
    app = new_app(tmp_path, config="format = 1\n")
    write_part(app, "api", dir="web")
    write_part(app, "web", dir="web/sub")
    problems = make().check(app)
    assert len(problems) == 1
    assert "api" in problems[0]
    assert "web" in problems[0]


def test_check_reports_an_unknown_stack_once(tmp_path: Path) -> None:
    app = new_app(tmp_path, config="format = 1\n")
    write_part(app, "web", stack="no_such_stack")
    problems = make().check(app)
    assert len(problems) == 1
    assert "no_such_stack" in problems[0]
    assert "web" in problems[0]


def test_check_reports_a_missing_folder_once(tmp_path: Path) -> None:
    app = new_app(tmp_path, config="format = 1\n")
    live = _ready(app, "api", "web")
    shutil.rmtree(app.root / "web")
    problems = live.check(app)
    assert len(problems) == 1
    assert "web" in problems[0]


def test_check_gives_one_message_per_problem(tmp_path: Path) -> None:
    app = new_app(tmp_path, config="format = 1\n")
    write_part(app, "web", stack="no_such_stack")
    write_part(app, "api")
    shutil.rmtree(app.root / "api")
    assert len(make().check(app)) == 2


# ------------------------------------------------------ module paths


def test_module_src_is_root_source_dir_modules_module(tmp_path: Path) -> None:
    part = Part(
        "web", "fixture", "web", tmp_path / "web", Path("src/fx"), Path("tests")
    )
    assert make().module_src(part, "core") == tmp_path / "web/src/fx/Modules/core"


def test_module_tests_is_root_test_dir_module(tmp_path: Path) -> None:
    part = Part("web", "fixture", "web", tmp_path / "web", Path("src/fx"), Path("spec"))
    assert make().module_tests(part, "core") == tmp_path / "web/spec/core"


# ---------------------------------------------------------- is_test_path


def test_is_test_path_true_inside_a_parts_test_folder(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    assert make().is_test_path(app, app.root / "tests/core/helper.fx")


def test_is_test_path_true_inside_a_nested_parts_test_folder(tmp_path: Path) -> None:
    app = new_app(tmp_path, config="format = 1\n")
    live = _ready(app, "web")
    assert live.is_test_path(app, app.root / "web/tests/core/helper.fx")


def test_is_test_path_true_for_a_file_matching_the_stack_test_glob(
    tmp_path: Path,
) -> None:
    app = new_app(tmp_path)
    assert make().is_test_path(app, app.root / "src/fx/core/a.test")


def test_is_test_path_uses_the_glob_of_the_stack_of_any_part(tmp_path: Path) -> None:
    registry = MockStackRegistry()
    other = registry.stacks["python_cli"]
    registry.stacks["python_cli"] = replace(
        other, manifest=replace(other.manifest, test_glob=("test_*.py",))
    )
    app = new_app(tmp_path, config="format = 1\n")
    live = LiveParts(registry, loader_with())
    live.add(app, "api", "fixture")
    live.add(app, "tool", "python_cli")
    assert live.is_test_path(app, app.root / "tool/src/test_x.py")


def test_is_test_path_false_for_source_files(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    assert not make().is_test_path(app, app.root / "src/fx/core/a.fx")


def test_is_test_path_false_when_there_are_no_parts(tmp_path: Path) -> None:
    app = new_app(tmp_path, config="format = 1\n")
    assert not make().is_test_path(app, app.root / "tests/a.fx")


# ------------------------------------------------ review-driven additions

CONFIG_WITH_STACK = 'format = 1\nstack = "fixture"\n'


def snapshot(root: Path) -> dict[str, str]:
    """Every entry under `root` (symlinks not followed) mapped to its content or kind."""
    seen: dict[str, str] = {}
    for folder, dirs, files in os.walk(root, followlinks=False):
        base = Path(folder)
        for name in dirs:
            path = base / name
            rel = str(path.relative_to(root))
            seen[rel] = f"link:{os.readlink(path)}" if path.is_symlink() else "dir"
        for name in files:
            path = base / name
            rel = str(path.relative_to(root))
            seen[rel] = (
                f"link:{os.readlink(path)}"
                if path.is_symlink()
                else path.read_text(encoding="utf-8")
            )
    return seen


def registry_with_gitignore(*lines: str) -> MockStackRegistry:
    registry = MockStackRegistry()
    stack = registry.stacks["fixture"]
    registry.stacks["fixture"] = replace(
        stack, manifest=replace(stack.manifest, gitignore=tuple(lines))
    )
    return registry


# ---------------------------------------------------- add: dir safety


def _outside(tmp_path: Path) -> Path:
    outside = tmp_path / "outside"
    outside.mkdir()
    return outside


def test_add_rejects_a_dir_that_is_a_symlink_to_a_folder_outside_the_app(
    tmp_path: Path,
) -> None:
    app = new_app(tmp_path, config=CONFIG_WITH_STACK, gitignore="keep/\n")
    outside = _outside(tmp_path)
    (app.root / "web").symlink_to(outside, target_is_directory=True)
    before_app = snapshot(app.root)
    before_outside = snapshot(outside)
    with pytest.raises(BullError):
        make().add(app, "web", "fixture")
    assert snapshot(app.root) == before_app
    assert snapshot(outside) == before_outside


def test_add_rejects_a_dir_under_a_symlinked_parent_pointing_outside(
    tmp_path: Path,
) -> None:
    app = new_app(tmp_path, config=CONFIG_WITH_STACK, gitignore="keep/\n")
    outside = _outside(tmp_path)
    (app.root / "link").symlink_to(outside, target_is_directory=True)
    before_app = snapshot(app.root)
    with pytest.raises(BullError):
        make().add(app, "web", "fixture", "link/web")
    assert snapshot(app.root) == before_app
    assert snapshot(outside) == {}


def test_add_rejects_a_dir_that_exists_as_a_file(tmp_path: Path) -> None:
    app = new_app(tmp_path, config=CONFIG_WITH_STACK, gitignore="keep/\n")
    (app.root / "web").write_text("not a folder", encoding="utf-8")
    before = snapshot(app.root)
    with pytest.raises(BullError):
        make().add(app, "web", "fixture")
    assert snapshot(app.root) == before
    assert not (app.parts_dir / "web.toml").exists()


# ------------------------------------------- add: gitignore prefixing


def _gitignore_after_add(tmp_path: Path, folder: str, *lines: str) -> list[str]:
    app = new_app(tmp_path, config="format = 1\n")
    live = LiveParts(registry_with_gitignore(*lines), loader_with())
    live.add(app, "web", "fixture", folder)
    return (app.root / ".gitignore").read_text(encoding="utf-8").splitlines()


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("__pycache__/", "web/**/__pycache__/"),
        ("*.pyc", "web/**/*.pyc"),
        (".venv/", "web/**/.venv/"),
        ("build/out/", "web/build/out/"),
        ("/dist", "/web/dist"),
        ("**/x", "web/**/x"),
    ],
)
def test_add_prefixes_gitignore_lines_keeping_their_meaning(
    tmp_path: Path, line: str, expected: str
) -> None:
    lines = _gitignore_after_add(tmp_path, "web", line)
    assert expected in lines
    assert line not in lines


def test_add_leaves_gitignore_lines_unchanged_for_a_part_at_the_root(
    tmp_path: Path,
) -> None:
    given = ("__pycache__/", "build/out/", "/dist", "**/x", "*.pyc")
    lines = _gitignore_after_add(tmp_path, ".", *given)
    for line in given:
        assert line in lines


# --------------------------------------------------- is_test_path


def test_is_test_path_normalizes_dotdot_into_the_test_folder(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    assert make().is_test_path(app, app.root / "src/../tests/x.py")


def test_is_test_path_normalizes_dotdot_out_of_the_test_folder(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    assert not make().is_test_path(app, app.root / "tests/../src/a.py")


def test_is_test_path_follows_a_symlink_from_source_into_the_test_folder(
    tmp_path: Path,
) -> None:
    app = new_app(tmp_path)
    (app.root / "tests").mkdir()
    (app.root / "src/fx").mkdir(parents=True)
    (app.root / "src/fx/linked").symlink_to(
        app.root / "tests", target_is_directory=True
    )
    (app.root / "tests/x.fx").write_text("", encoding="utf-8")
    assert make().is_test_path(app, app.root / "src/fx/linked/x.fx")


def test_is_test_path_takes_relative_paths_relative_to_the_app_root(
    tmp_path: Path,
) -> None:
    app = new_app(tmp_path)
    live = make()
    assert live.is_test_path(app, Path("tests/core/x.fx"))
    assert not live.is_test_path(app, Path("src/fx/core/a.fx"))


def test_is_test_path_is_false_outside_the_app(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    live = make()
    assert not live.is_test_path(app, tmp_path / "elsewhere/tests/x.fx")
    assert not live.is_test_path(app, tmp_path / "elsewhere/x.test")


def test_is_test_path_matches_globs_against_the_file_name_only(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    live = make()
    assert live.is_test_path(app, app.root / "src/fx/deep/er/a.test")
    assert not live.is_test_path(app, app.root / "src/fx/a.test.fx")


# ---------------------------------------- add: whole-operation safety


def test_add_failing_in_the_scaffold_step_rolls_everything_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Chosen behavior: rollback. A failed add leaves config.toml, .gitignore and the
    # part files exactly as they were, so the app still lists its one implicit part.
    app = new_app(tmp_path, config=CONFIG_WITH_STACK, gitignore="keep/\n")
    live = make()
    parts_before = live.all(app)
    config_before = app.config_file.read_text(encoding="utf-8")
    gitignore_before = (app.root / ".gitignore").read_text(encoding="utf-8")
    real_mkdir = Path.mkdir
    web = app.root / "web"

    def failing_mkdir(self: Path, *args: Any, **kwargs: Any) -> None:
        if self.parent == web:
            raise OSError("disk full")
        real_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", failing_mkdir)
    with pytest.raises((BullError, OSError)):
        live.add(app, "web", "fixture")
    monkeypatch.undo()

    assert app.config_file.read_text(encoding="utf-8") == config_before
    assert (app.root / ".gitignore").read_text(encoding="utf-8") == gitignore_before
    assert not (app.parts_dir / "web.toml").exists()
    assert not (app.parts_dir / "app.toml").exists()
    assert live.all(app) == parts_before


# ------------------------------------------------- add: refusals


def _refusal_cases() -> list[tuple[str, str, str | None]]:
    return [
        ("bad name", "Web", None),
        ("existing name", "api", "other"),
        ("overlap", "web", "api/inner"),
        ("outside dir", "web", "../outside"),
        ("absolute dir", "web", "/abs/place"),
    ]


@pytest.mark.parametrize(("label", "name", "folder"), _refusal_cases())
def test_add_refusals_write_nothing(
    tmp_path: Path, label: str, name: str, folder: str | None
) -> None:
    app = new_app(tmp_path, config=CONFIG_WITH_STACK, gitignore="keep/\n")
    live = make()
    live.add(app, "api", "fixture")  # moves the implicit part, then adds `api`
    before = snapshot(app.root)
    with pytest.raises(BullError):
        live.add(app, name, "fixture", folder)
    assert snapshot(app.root) == before


@pytest.mark.parametrize("name", ["Web", "app"])
def test_add_refused_on_an_implicit_app_leaves_config_and_gitignore_alone(
    tmp_path: Path, name: str
) -> None:
    app = new_app(tmp_path, config=CONFIG_WITH_STACK, gitignore="keep/\n")
    before = snapshot(app.root)
    with pytest.raises(BullError):
        make().add(app, name, "fixture", "other")
    assert snapshot(app.root) == before


def test_add_overlap_with_the_implicit_part_writes_nothing(tmp_path: Path) -> None:
    app = new_app(tmp_path, config=CONFIG_WITH_STACK, gitignore="keep/\n")
    before = snapshot(app.root)
    with pytest.raises(BullError):
        make().add(app, "web", "fixture", "tests/deep")
    assert snapshot(app.root) == before


# --------------------------------------- add: implicit move fidelity


def test_implicit_move_keeps_comments_and_unrelated_lines_byte_for_byte(
    tmp_path: Path,
) -> None:
    kept = (
        "# top comment\n"
        "format = 1\n"
        "# keep me\n"
        'base_branch = "trunk"  # trailing note\n'
        "\n"
        "[models]\n"
        'reviewer = "opus"\n'
    )
    original = (
        "# top comment\n"
        "format = 1\n"
        'stack = "fixture"\n'
        'source_dir = "lib/x"\n'
        "# keep me\n"
        'base_branch = "trunk"  # trailing note\n'
        'test_dir = "spec"\n'
        "\n"
        "[models]\n"
        'reviewer = "opus"\n'
    )
    app = new_app(tmp_path, config=original)
    make().add(app, "web", "fixture")
    assert app.config_file.read_text(encoding="utf-8") == kept
    moved = toml_of(app.parts_dir / "app.toml")
    assert moved["source_dir"] == "lib/x"
    assert moved["test_dir"] == "spec"


def test_implicit_move_refuses_stack_keys_it_cannot_move_and_writes_nothing(
    tmp_path: Path,
) -> None:
    original = (
        'format = 1\nstack = "fixture"\nsource_dir = [\n  "lib/x",\n  "lib/y",\n]\n'
    )
    app = new_app(tmp_path, config=original, gitignore="keep/\n")
    before = snapshot(app.root)
    with pytest.raises(BullError):
        make().add(app, "web", "fixture")
    assert snapshot(app.root) == before


def test_a_stray_non_toml_file_in_parts_does_not_block_the_implicit_move(
    tmp_path: Path,
) -> None:
    app = new_app(tmp_path)
    app.parts_dir.mkdir(parents=True)
    (app.parts_dir / "README.md").write_text("notes", encoding="utf-8")
    (app.parts_dir / "app.toml.bak").write_text("old", encoding="utf-8")
    live = make()
    assert [p.name for p in live.all(app)] == ["app"]
    live.add(app, "web", "fixture")
    assert (app.parts_dir / "app.toml").exists()
    assert [p.name for p in live.all(app)] == ["app", "web"]
    assert "stack" not in toml_of(app.config_file)


# ---------------------------------------------------- check reports


@pytest.mark.parametrize("folder", ["/abs/place", "../outside", "a/../../outside"])
def test_check_reports_a_part_file_with_a_bad_dir_instead_of_raising(
    tmp_path: Path, folder: str
) -> None:
    app = new_app(tmp_path, config="format = 1\n")
    app.parts_dir.mkdir(parents=True)
    (app.parts_dir / "web.toml").write_text(
        f'format = 1\nstack = "fixture"\ndir = "{folder}"\n', encoding="utf-8"
    )
    problems = make().check(app)
    assert len(problems) == 1
    assert "web" in problems[0]


@pytest.mark.parametrize("missing", ["src/fx", "tests"])
def test_check_reports_a_missing_source_or_test_folder_once(
    tmp_path: Path, missing: str
) -> None:
    app = new_app(tmp_path, config="format = 1\n")
    write_part(app, "web")
    shutil.rmtree(app.root / "web" / missing)
    problems = make().check(app)
    assert len(problems) == 1
    assert "web" in problems[0]


def test_check_reports_a_root_part_whose_source_folder_contains_another_part(
    tmp_path: Path,
) -> None:
    app = new_app(tmp_path, config="format = 1\n")
    write_part(app, "core", dir=".")
    write_part(app, "web", dir="src/fx/web")
    problems = make().check(app)
    assert len(problems) == 1
    assert "core" in problems[0]
    assert "web" in problems[0]


# ------------------------------------------- add: root part refusals


@pytest.mark.parametrize("existing", ["src/fx/web", "tests/web"])
def test_add_root_part_refused_when_its_folders_would_contain_an_existing_part(
    tmp_path: Path, existing: str
) -> None:
    app = new_app(tmp_path, config="format = 1\n")
    live = make()
    live.add(app, "web", "fixture", existing)
    before = snapshot(app.root)
    with pytest.raises(BullError):
        live.add(app, "core", "fixture", ".")
    assert snapshot(app.root) == before
