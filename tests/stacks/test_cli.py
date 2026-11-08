"""Tests for `bull.Modules.stacks.cli` (`bull stacks` and `bull stack ...`).

Shapes chosen here (for the code-writer):
  - `register(commands, registry, ops, app, settings, before_install=None)`: the first
    argument is the argparse subparsers action; the next four are zero-argument providers
    (`Callable[[], StackRegistry]`, `Callable[[], StackOps]`, `Callable[[], AppLayout]`,
    `Callable[[], Settings]`), called only when a command runs. `before_install` is an
    optional `Callable[[Path], None]` called with the folder before the registry installs it
    (the composition root passes the static self-test; an exception stops the install).
  - Adds a `stacks` parser (`--all`, `--json`) and a `stack` parser with leaves `select`,
    `rules`, `setup`, `check`, `run`, `install`. Each leaf sets `run(args, out) -> int`.
  - `stacks`: one line per stack with name, kind, maturity, title, and the word
    "installed" for stacks that are not built in. `--all` lists test stacks too. `--json`: a
    list of `{"name", "kind", "maturity", "title", "installed": bool}`, nothing else on `out`.
  - `stack rules|setup` find the stack by `settings.get("stack", part)` and
    `registry.get(name)`, then print `ops.rules(stack, agent)` / `ops.setup_guide(stack,
    section)`; `--part p` selects the part.
  - `stack select <name>` -> `ops.select(app, name)`; `stack run <cmd> [--part p]` returns
    `ops.run_command(app, cmd, part)`; `stack install <path>` prints the installed name.
  - `stack check [--part p] [--json]` prints `✓ item` / `✗ item — fix` lines, exit 1 when any
    item failed (else 0); `--json` prints a list of `{"ok", "item", "fix"}`.
  - Errors are raised (BullError), not printed.
"""

from __future__ import annotations

import argparse
import io
import json
from dataclasses import replace
from pathlib import Path

import pytest

from bull.Modules.foundation.Contracts import AppLayout
from bull.Modules.foundation.mocks import sample_layout
from bull.Modules.stacks.cli import register
from bull.Modules.stacks.Contracts import CheckItem, StackError
from bull.Modules.stacks.mocks import MockStackOps, MockStackRegistry

from .fakes import FakeSettings

APP = sample_layout(Path("/tmp/apps/tally"))


class Rig:
    def __init__(self) -> None:
        self.registry = MockStackRegistry()
        self.ops = MockStackOps()
        self.settings = FakeSettings(
            {"stack": "python_cli"}, {"api": {"stack": "fixture"}}
        )
        self.provided: list[str] = []
        self.before: list[Path] = []
        self.parser = argparse.ArgumentParser(prog="bull")
        commands = self.parser.add_subparsers(dest="command")
        register(
            commands,
            lambda: self._note("registry", self.registry),
            lambda: self._note("ops", self.ops),
            lambda: self._note("app", APP),
            lambda: self._note("settings", self.settings),
            before_install=self.before.append,
        )

    def _note(self, name: str, value):  # type: ignore[no-untyped-def]
        self.provided.append(name)
        return value

    def run(self, *argv: str) -> tuple[int, str]:
        args = self.parser.parse_args(argv)
        out = io.StringIO()
        code = args.run(args, out)
        return code, out.getvalue()


@pytest.fixture
def rig() -> Rig:
    return Rig()


def test_register_does_not_call_any_provider(rig: Rig) -> None:
    rig.parser.parse_args(["stacks"])
    rig.parser.parse_args(["stack", "check"])
    assert rig.provided == []


# ----------------------------------------------------------------- stacks


def test_stacks_lists_name_kind_maturity_and_title(rig: Rig) -> None:
    code, text = rig.run("stacks")
    assert code == 0
    (line,) = [ln for ln in text.splitlines() if "python_cli" in ln]
    manifest = rig.registry.stacks["python_cli"].manifest
    assert manifest.kind.value in line
    assert manifest.maturity.value in line
    assert manifest.title in line


def test_stacks_hides_test_stacks_by_default(rig: Rig) -> None:
    _, text = rig.run("stacks")
    assert "fixture" not in text
    assert ("all", (False,)) in rig.registry.calls


def test_stacks_all_includes_test_stacks(rig: Rig) -> None:
    _, text = rig.run("stacks", "--all")
    assert "fixture" in text
    assert "python_cli" in text
    assert ("all", (True,)) in rig.registry.calls


def test_stacks_marks_installed_stacks_only(rig: Rig) -> None:
    stack = rig.registry.stacks["python_cli"]
    rig.registry.stacks["extra"] = replace(
        stack, manifest=replace(stack.manifest, name="extra"), builtin=False
    )
    _, text = rig.run("stacks")
    lines = text.splitlines()
    assert "installed" in next(ln for ln in lines if "extra" in ln)
    assert "installed" not in next(ln for ln in lines if "python_cli" in ln)


def test_stacks_lists_in_registry_order(rig: Rig) -> None:
    _, text = rig.run("stacks", "--all")
    assert text.index("fixture") < text.index("python_cli")


def test_stacks_json_is_a_list_of_objects_and_nothing_else(rig: Rig) -> None:
    code, text = rig.run("stacks", "--all", "--json")
    assert code == 0
    data = json.loads(text)
    assert [d["name"] for d in data] == ["fixture", "python_cli"]
    entry = data[1]
    assert entry["kind"] == "tool"
    assert entry["maturity"] == "experimental"
    assert entry["title"] == rig.registry.stacks["python_cli"].manifest.title
    assert entry["installed"] is False


def test_stacks_json_flags_installed_stacks(rig: Rig) -> None:
    stack = rig.registry.stacks["python_cli"]
    rig.registry.stacks["python_cli"] = replace(stack, builtin=False)
    _, text = rig.run("stacks", "--json")
    assert json.loads(text)[0]["installed"] is True


# ------------------------------------------------------------ select, run


def test_stack_select_calls_ops_with_the_app_and_name(rig: Rig) -> None:
    code, _ = rig.run("stack", "select", "python_cli")
    assert code == 0
    assert rig.ops.calls == [("select", (APP, "python_cli"))]


def test_stack_select_propagates_a_stack_error(rig: Rig) -> None:
    def refuse(app: object, name: str) -> None:
        raise StackError("no parts please", "use `bull part add`")

    rig.ops.select = refuse  # type: ignore[method-assign]
    with pytest.raises(StackError):
        rig.run("stack", "select", "python_cli")


def test_stack_run_passes_command_and_no_part_by_default(rig: Rig) -> None:
    code, _ = rig.run("stack", "run", "prune")
    assert code == 0
    assert rig.ops.calls == [("run_command", (APP, "prune", None))]


def test_stack_run_passes_the_part_through(rig: Rig, tmp_path: Path) -> None:
    app = parts_app(tmp_path, "api")
    run_with(build(rig, app), "stack", "run", "prune", "--part", "api")
    assert rig.ops.calls == [("run_command", (app, "prune", "api"))]


def test_stack_run_returns_the_commands_exit_code(rig: Rig) -> None:
    rig.ops.exit_code = 7
    code, _ = rig.run("stack", "run", "prune")
    assert code == 7


# ----------------------------------------------------------- rules, setup


def test_stack_rules_prints_the_rules_for_the_apps_stack(rig: Rig) -> None:
    code, text = rig.run("stack", "rules", "test-writer")
    assert code == 0
    ((name, (stack, agent)),) = rig.ops.calls
    assert name == "rules"
    assert stack is rig.registry.stacks["python_cli"]
    assert agent == "test-writer"
    assert "## test-writer" in text


def test_stack_rules_with_part_uses_that_parts_stack(rig: Rig, tmp_path: Path) -> None:
    run_with(
        build(rig, parts_app(tmp_path, "api")),
        "stack",
        "rules",
        "reviewer",
        "--part",
        "api",
    )
    ((_, (stack, _)),) = rig.ops.calls
    assert stack is rig.registry.stacks["fixture"]


def test_stack_setup_prints_the_whole_guide(rig: Rig) -> None:
    code, text = rig.run("stack", "setup")
    assert code == 0
    assert rig.ops.calls == [("setup_guide", (rig.registry.stacks["python_cli"], None))]
    assert "Create `fixture.toml`" in text


def test_stack_setup_section_is_passed_through(rig: Rig) -> None:
    rig.run("stack", "setup", "--section", "For a feature")
    assert rig.ops.calls == [
        ("setup_guide", (rig.registry.stacks["python_cli"], "For a feature"))
    ]


def test_stack_setup_with_part_uses_that_parts_stack(rig: Rig, tmp_path: Path) -> None:
    run_with(build(rig, parts_app(tmp_path, "api")), "stack", "setup", "--part", "api")
    ((_, (stack, _)),) = rig.ops.calls
    assert stack is rig.registry.stacks["fixture"]


# ------------------------------------------------------------------ check


def test_stack_check_all_passing_exits_zero(rig: Rig) -> None:
    code, text = rig.run("stack", "check")
    assert code == 0
    assert "✗" not in text
    assert "git on PATH" in text
    assert rig.ops.calls == [("check", (APP, None))]


def test_stack_check_failing_item_exits_one_and_prints_item_and_fix(rig: Rig) -> None:
    rig.ops.items = [
        CheckItem(True, "git on PATH", ""),
        CheckItem(False, "source folder src/fx exists", "create src/fx"),
    ]
    code, text = rig.run("stack", "check")
    assert code == 1
    assert "✗ source folder src/fx exists — create src/fx" in text.splitlines()


def test_stack_check_does_not_mark_passing_items_as_failed(rig: Rig) -> None:
    rig.ops.items = [
        CheckItem(True, "git on PATH", ""),
        CheckItem(False, "uv on PATH", "install uv"),
    ]
    _, text = rig.run("stack", "check")
    git_line = next(ln for ln in text.splitlines() if "git on PATH" in ln)
    assert "✗" not in git_line


def test_stack_check_with_no_items_exits_zero(rig: Rig) -> None:
    rig.ops.items = []
    code, _ = rig.run("stack", "check")
    assert code == 0


def test_stack_check_passes_the_part_through(rig: Rig, tmp_path: Path) -> None:
    app = parts_app(tmp_path, "api")
    run_with(build(rig, app), "stack", "check", "--part", "api")
    assert rig.ops.calls == [("check", (app, "api"))]


def test_stack_check_json_lists_every_item_and_still_exits_one_on_failure(
    rig: Rig,
) -> None:
    rig.ops.items = [
        CheckItem(True, "git on PATH", ""),
        CheckItem(False, "uv on PATH", "install uv"),
    ]
    code, text = rig.run("stack", "check", "--json")
    assert code == 1
    assert json.loads(text) == [
        {"ok": True, "item": "git on PATH", "fix": ""},
        {"ok": False, "item": "uv on PATH", "fix": "install uv"},
    ]


# ---------------------------------------------------------------- install


def test_stack_install_installs_the_folder_and_prints_its_name(rig: Rig) -> None:
    code, text = rig.run("stack", "install", "/tmp/stacks/my_stack")
    assert code == 0
    assert ("install", (Path("/tmp/stacks/my_stack"),)) in rig.registry.calls
    assert "my_stack" in text


def test_stack_install_runs_the_pre_install_check_first(rig: Rig) -> None:
    rig.run("stack", "install", "/tmp/stacks/my_stack")
    assert rig.before == [Path("/tmp/stacks/my_stack")]


def test_stack_install_stops_when_the_pre_install_check_fails(rig: Rig) -> None:
    def refuse(path: Path) -> None:
        raise StackError("static check failed")

    parser = argparse.ArgumentParser(prog="bull")
    register(
        parser.add_subparsers(dest="command"),
        lambda: rig.registry,
        lambda: rig.ops,
        lambda: APP,
        lambda: rig.settings,
        before_install=refuse,
    )
    args = parser.parse_args(["stack", "install", "/tmp/stacks/my_stack"])
    with pytest.raises(StackError):
        args.run(args, io.StringIO())
    assert not any(name == "install" for name, _ in rig.registry.calls)


def test_stack_install_works_without_a_pre_install_check() -> None:
    registry = MockStackRegistry()
    parser = argparse.ArgumentParser(prog="bull")
    register(
        parser.add_subparsers(dest="command"),
        lambda: registry,
        lambda: MockStackOps(),
        lambda: APP,
        lambda: FakeSettings({"stack": "python_cli"}),
    )
    args = parser.parse_args(["stack", "install", "/tmp/stacks/other"])
    assert args.run(args, io.StringIO()) == 0
    assert ("install", (Path("/tmp/stacks/other"),)) in registry.calls


# ----------------------------------------------------------- review rounds


def build(
    rig: Rig, app: AppLayout, settings: FakeSettings | None = None
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bull")
    register(
        parser.add_subparsers(dest="command"),
        lambda: rig.registry,
        lambda: rig.ops,
        lambda: app,
        lambda: settings or rig.settings,
    )
    return parser


def run_with(parser: argparse.ArgumentParser, *argv: str) -> int:
    args = parser.parse_args(argv)
    return int(args.run(args, io.StringIO()))


def run_text(parser: argparse.ArgumentParser, *argv: str) -> tuple[int, str]:
    args = parser.parse_args(argv)
    out = io.StringIO()
    code = int(args.run(args, out))
    return code, out.getvalue()


def parts_app(tmp_path: Path, *names: str) -> AppLayout:
    app = sample_layout(tmp_path)
    app.parts_dir.mkdir(parents=True)
    for name in names:
        (app.parts_dir / f"{name}.toml").write_text("format = 1\n", encoding="utf-8")
    return app


def two_part_rig(rig: Rig, tmp_path: Path) -> argparse.ArgumentParser:
    """Parts `api` (stack fixture) and `web` (stack python_cli)."""
    rig.settings = FakeSettings(
        {"stack": "python_cli"},
        {"api": {"stack": "fixture"}, "web": {"stack": "python_cli"}},
    )
    return build(rig, parts_app(tmp_path, "web", "api"))


@pytest.mark.parametrize("leaf", [("rules", "reviewer"), ("setup",)])
def test_stack_rules_and_setup_without_part_name_the_parts_when_parts_exist(
    rig: Rig, tmp_path: Path, leaf: tuple[str, ...]
) -> None:
    app = sample_layout(tmp_path)
    app.parts_dir.mkdir(parents=True)
    for name in ("api", "web"):
        (app.parts_dir / f"{name}.toml").write_text("format = 1\n", encoding="utf-8")
    parser = build(rig, app)
    with pytest.raises(StackError) as caught:
        run_with(parser, "stack", *leaf)
    text = f"{caught.value.message} {caught.value.fix}"
    assert "api" in text
    assert "web" in text
    assert rig.ops.calls == []


@pytest.mark.parametrize("leaf", [("rules", "reviewer"), ("setup",)])
def test_stack_rules_and_setup_without_part_use_the_apps_stack_when_no_parts(
    rig: Rig, tmp_path: Path, leaf: tuple[str, ...]
) -> None:
    app = sample_layout(tmp_path)
    app.parts_dir.mkdir(parents=True)
    assert run_with(build(rig, app), "stack", *leaf) == 0
    ((_, (stack, *_)),) = rig.ops.calls
    assert stack is rig.registry.stacks["python_cli"]


@pytest.mark.parametrize("leaf", [("rules", "reviewer"), ("setup",)])
@pytest.mark.parametrize("stack", ["", None])
def test_stack_rules_and_setup_tell_you_to_select_a_stack_when_none_is_set(
    rig: Rig, leaf: tuple[str, ...], stack: object
) -> None:
    class Unset(FakeSettings):
        def get(self, key, part=None):  # type: ignore[no-untyped-def]
            if key == "stack":
                return stack
            return super().get(key, part)

    parser = build(rig, APP, Unset({}))
    with pytest.raises(StackError) as caught:
        run_with(parser, "stack", *leaf)
    text = f"{caught.value.message} {caught.value.fix}"
    assert "bull stack select" in text
    assert "None" not in text
    assert rig.ops.calls == []


def test_stack_check_text_lines_are_exactly_the_item_lines(rig: Rig) -> None:
    rig.ops.items = [
        CheckItem(True, "git on PATH", ""),
        CheckItem(False, "uv on PATH", "install uv"),
    ]
    _, text = rig.run("stack", "check")
    assert text.splitlines() == ["✓ git on PATH", "✗ uv on PATH — install uv"]


def test_stack_install_propagates_a_non_stack_error_and_installs_nothing(
    rig: Rig,
) -> None:
    def explode(path: Path) -> None:
        raise RuntimeError("self-test crashed")

    parser = argparse.ArgumentParser(prog="bull")
    register(
        parser.add_subparsers(dest="command"),
        lambda: rig.registry,
        lambda: rig.ops,
        lambda: APP,
        lambda: rig.settings,
        before_install=explode,
    )
    args = parser.parse_args(["stack", "install", "/tmp/stacks/my_stack"])
    with pytest.raises(RuntimeError):
        args.run(args, io.StringIO())
    assert not any(name == "install" for name, _ in rig.registry.calls)
    assert "my_stack" not in rig.registry.stacks


# ------------------------------------------- check every part, unknown --part


class PerPartOps(MockStackOps):
    """`check` returns the items set for the part it is asked about."""

    def __init__(self, per_part: dict[str | None, list[CheckItem]]) -> None:
        super().__init__()
        self.per_part = per_part

    def check(self, app: AppLayout, part: str | None = None) -> list[CheckItem]:
        self.calls.append(("check", (app, part)))
        return list(self.per_part[part])


def checks(rig: Rig) -> list[object]:
    return [args[1] for name, args in rig.ops.calls if name == "check"]


def test_stack_check_without_part_checks_every_part_in_sorted_order(
    rig: Rig, tmp_path: Path
) -> None:
    code, _ = run_text(two_part_rig(rig, tmp_path), "stack", "check")
    assert code == 0
    assert checks(rig) == ["api", "web"]


def test_stack_check_without_part_prints_a_heading_before_each_parts_lines(
    rig: Rig, tmp_path: Path
) -> None:
    rig.ops = PerPartOps(
        {
            "api": [CheckItem(True, "uv on PATH", "")],
            "web": [CheckItem(False, "node on PATH", "install node")],
        }
    )
    _, text = run_text(two_part_rig(rig, tmp_path), "stack", "check")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    assert lines == [
        "part api (fixture)",
        "✓ uv on PATH",
        "part web (python_cli)",
        "✗ node on PATH — install node",
    ]


def test_stack_check_without_part_exits_one_if_any_part_fails(
    rig: Rig, tmp_path: Path
) -> None:
    rig.ops = PerPartOps(
        {
            "api": [CheckItem(False, "uv on PATH", "install uv")],
            "web": [CheckItem(True, "node on PATH", "")],
        }
    )
    code, _ = run_text(two_part_rig(rig, tmp_path), "stack", "check")
    assert code == 1


def test_stack_check_without_part_still_checks_later_parts_after_a_failure(
    rig: Rig, tmp_path: Path
) -> None:
    rig.ops = PerPartOps(
        {
            "api": [CheckItem(False, "uv on PATH", "install uv")],
            "web": [CheckItem(True, "node on PATH", "")],
        }
    )
    _, text = run_text(two_part_rig(rig, tmp_path), "stack", "check")
    assert checks(rig) == ["api", "web"]
    assert "✓ node on PATH" in text


def test_stack_check_without_part_exits_zero_when_every_part_passes(
    rig: Rig, tmp_path: Path
) -> None:
    rig.ops = PerPartOps(
        {
            "api": [CheckItem(True, "uv on PATH", "")],
            "web": [CheckItem(True, "node on PATH", "")],
        }
    )
    code, text = run_text(two_part_rig(rig, tmp_path), "stack", "check")
    assert code == 0
    assert "✗" not in text


def test_stack_check_with_one_part_prints_no_heading_and_checks_only_it(
    rig: Rig, tmp_path: Path
) -> None:
    code, text = run_text(
        two_part_rig(rig, tmp_path), "stack", "check", "--part", "web"
    )
    assert code == 0
    assert "part web" not in text
    assert checks(rig) == ["web"]


def test_stack_check_without_part_json_lists_part_stack_and_items(
    rig: Rig, tmp_path: Path
) -> None:
    rig.ops = PerPartOps(
        {
            "api": [CheckItem(True, "uv on PATH", "")],
            "web": [CheckItem(False, "node on PATH", "install node")],
        }
    )
    code, text = run_text(two_part_rig(rig, tmp_path), "stack", "check", "--json")
    assert code == 1
    assert json.loads(text) == [
        {
            "part": "api",
            "stack": "fixture",
            "items": [{"ok": True, "item": "uv on PATH", "fix": ""}],
        },
        {
            "part": "web",
            "stack": "python_cli",
            "items": [{"ok": False, "item": "node on PATH", "fix": "install node"}],
        },
    ]


def test_stack_check_with_one_part_json_is_a_plain_list_of_items(
    rig: Rig, tmp_path: Path
) -> None:
    rig.ops = PerPartOps({"web": [CheckItem(True, "node on PATH", "")]})
    _, text = run_text(
        two_part_rig(rig, tmp_path), "stack", "check", "--part", "web", "--json"
    )
    assert json.loads(text) == [{"ok": True, "item": "node on PATH", "fix": ""}]


def test_stack_check_without_part_in_an_app_without_part_files_has_no_heading(
    rig: Rig,
) -> None:
    code, text = rig.run("stack", "check")
    assert code == 0
    assert "part " not in text
    assert text.splitlines() == ["✓ git on PATH", "✓ source folder src/fx exists"]


@pytest.mark.parametrize(
    "argv",
    [
        ("rules", "reviewer", "--part", "nope"),
        ("setup", "--part", "nope"),
        ("check", "--part", "nope"),
        ("run", "prune", "--part", "nope"),
    ],
)
def test_unknown_part_is_rejected_naming_the_known_parts(
    rig: Rig, tmp_path: Path, argv: tuple[str, ...]
) -> None:
    parser = two_part_rig(rig, tmp_path)
    with pytest.raises(StackError) as caught:
        run_with(parser, "stack", *argv)
    text = f"{caught.value.message} {caught.value.fix}"
    assert "nope" in text
    assert "api" in text
    assert "web" in text
    assert rig.ops.calls == []


@pytest.mark.parametrize(
    "argv",
    [
        ("rules", "reviewer", "--part", "nope"),
        ("setup", "--part", "nope"),
        ("check", "--part", "nope"),
        ("run", "prune", "--part", "nope"),
    ],
)
def test_unknown_part_in_an_app_without_part_files_names_app_as_known(
    rig: Rig, argv: tuple[str, ...]
) -> None:
    with pytest.raises(StackError) as caught:
        rig.run("stack", *argv)
    text = f"{caught.value.message} {caught.value.fix}"
    assert "nope" in text
    assert "app" in text
    assert rig.ops.calls == []


@pytest.mark.parametrize(
    "argv",
    [
        ("rules", "reviewer", "--part", "app"),
        ("setup", "--part", "app"),
        ("check", "--part", "app"),
        ("run", "prune", "--part", "app"),
    ],
)
def test_part_app_is_accepted_in_an_app_without_part_files(
    rig: Rig, argv: tuple[str, ...]
) -> None:
    code, _ = rig.run("stack", *argv)
    assert code == 0
    assert len(rig.ops.calls) == 1
