"""Tests for `bull.Modules.parts.parts` (LiveParts).

Shape chosen here (for the code-writer): `LiveParts(registry, loader)` with
`registry: StackRegistry` (stack existence, scaffold, gitignore, test_glob, stack
defaults) and `loader: SettingsLoader` (`loader.load(app, stack_layer).get("source_dir" |
"test_dir", part_name)` gives each part's folders; the implicit part is asked for as
`"app"` or `None`). Part files, config.toml and .gitignore are read and written on disk.
"""

from __future__ import annotations

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
