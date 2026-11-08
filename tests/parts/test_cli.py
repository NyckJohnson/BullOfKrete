"""Tests for `bull.Modules.parts.cli` (`bull part add|list|check`).

Shapes chosen here (for the code-writer):
  - `register(commands, parts, app)`: `commands` is the argparse subparsers action; `parts`
    is a `Callable[[], Parts]` and `app` a `Callable[[], AppLayout]`, both called only when
    a command runs. Adds a `part` parser with leaves `add`, `list`, `check`; each leaf sets
    `run(args, out) -> int`.
  - `part add <name> <stack> [--dir <folder>]` calls `parts.add(app, name, stack, dir)`
    (`dir=None` when not given), prints a line naming the part, returns 0.
  - `part list [--json]` prints one line per part with name, stack and dir; `--json` writes
    only a list of `{"name", "stack", "dir"}` objects to `out`.
  - `part check` prints one line per problem and returns 1 when there are any, else 0.
  - Errors are raised (BullError), not printed.
"""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

import pytest

from bull.Modules.foundation.Contracts import BullError
from bull.Modules.foundation.mocks import sample_layout
from bull.Modules.parts.cli import register
from bull.Modules.parts.mocks import MockParts

APP = sample_layout(Path("/tmp/apps/tally"))


class Rig:
    def __init__(self) -> None:
        self.parts = MockParts()
        self.provided: list[str] = []
        self.parser = argparse.ArgumentParser(prog="bull")
        commands = self.parser.add_subparsers(dest="command")
        register(
            commands,
            lambda: self._note("parts", self.parts),
            lambda: self._note("app", APP),
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
    rig.parser.parse_args(["part", "list"])
    rig.parser.parse_args(["part", "check"])
    assert rig.provided == []


def test_part_add_passes_name_stack_and_no_dir(rig: Rig) -> None:
    code, text = rig.run("part", "add", "web", "fixture")
    assert code == 0
    assert "web" in text
    assert rig.parts.calls == [("add", (APP, "web", "fixture", None))]


def test_part_add_passes_the_dir_option(rig: Rig) -> None:
    rig.run("part", "add", "web", "fixture", "--dir", "sites/w")
    assert rig.parts.calls == [("add", (APP, "web", "fixture", "sites/w"))]


def test_part_add_requires_name_and_stack(rig: Rig) -> None:
    with pytest.raises(SystemExit):
        rig.parser.parse_args(["part", "add", "web"])


def test_part_add_lets_errors_through(rig: Rig) -> None:
    def boom(*_: object, **__: object) -> None:
        raise BullError("bad name")

    rig.parts.add = boom  # type: ignore[method-assign,assignment]
    with pytest.raises(BullError):
        rig.run("part", "add", "Web", "fixture")


def test_part_list_prints_name_stack_and_dir(rig: Rig) -> None:
    rig.run("part", "add", "web", "fixture", "--dir", "sites/w")
    code, text = rig.run("part", "list")
    assert code == 0
    (line,) = [ln for ln in text.splitlines() if "web" in ln]
    assert "fixture" in line
    assert "sites/w" in line
    assert any("app" in ln for ln in text.splitlines())


def test_part_list_json_is_only_the_list_of_parts(rig: Rig) -> None:
    rig.run("part", "add", "web", "fixture", "--dir", "sites/w")
    code, text = rig.run("part", "list", "--json")
    assert code == 0
    data = json.loads(text)
    assert [d["name"] for d in data] == ["app", "web"]
    assert data[1]["stack"] == "fixture"
    assert data[1]["dir"] == "sites/w"


def test_part_list_json_with_no_parts_is_an_empty_list(rig: Rig) -> None:
    rig.parts.parts = []
    code, text = rig.run("part", "list", "--json")
    assert code == 0
    assert json.loads(text) == []


def test_part_check_is_silent_success_without_problems(rig: Rig) -> None:
    code, _ = rig.run("part", "check")
    assert code == 0
    assert ("check", (APP,)) in rig.parts.calls


def test_part_check_prints_each_problem_and_exits_one(rig: Rig) -> None:
    rig.parts.problems = ["api overlaps web", "web: unknown stack `zzz`"]
    code, text = rig.run("part", "check")
    assert code == 1
    assert "api overlaps web" in text
    assert "web: unknown stack `zzz`" in text
