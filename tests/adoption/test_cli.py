"""Tests for `bull.Modules.adoption.cli` (`bull adopt ...` and `bull stack detect`).

Shapes assumed (house style of `features.cli`): `register(commands, adoption, layouts)` adds only
`adopt`; `register_detect(stack_leaves, adoption, layouts)` adds `detect` to the subcommands action
of a `stack` parser owned by stacks.cli (the test makes one). `adoption` is a zero-argument
provider called only when a command runs and `layouts` is a `Layouts`; every leaf sets
`run(args, out) -> int`. The app is `layouts.find(Path.cwd())` (`stack detect` falls back to the
cwd as root outside an app). Refusals are raised as `BullError`.
`legacy` prints `<field>: <path>` lines (fields `files`, `declarations`, `tests`, `memo_files`) or
"Nothing left to replace."; `stack detect` prints `stack: <name> (<confidence>) — <summary>` or
`stack: none`, then `<level>: <item> — <fix>` per issue; exit 1 when blocked.
"""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
from typing import Any

import pytest

from bull.Modules.adoption.Contracts import Adoption, DetectionReport, LegacyLeft
from bull.Modules.adoption.mocks import SAMPLE_DETECTION, MockAdoption
from bull.Modules.foundation.Contracts import BullError
from bull.Modules.foundation.mocks import MockLayouts
from bull.Modules.stacks.Contracts import Issue, IssueLevel


class Rig:
    def __init__(self) -> None:
        self.adoption = MockAdoption()
        self.layouts = MockLayouts()
        self.provided = 0
        # imported here so the file collects while `cli.py` is still a stub
        from bull.Modules.adoption.cli import register, register_detect

        self.parser = argparse.ArgumentParser(prog="bull")
        commands = self.parser.add_subparsers(dest="command")
        register(commands, self._provide, self.layouts)
        # stacks.cli owns `stack`; the test makes its parser and hands over the leaves
        self.commands_after_register = sorted(commands.choices)
        stack = commands.add_parser("stack")
        leaves = stack.add_subparsers(dest="stack_command", required=True)
        register_detect(leaves, self._provide, self.layouts)

    def _provide(self) -> Adoption:
        self.provided += 1
        return self.adoption

    def run(self, *argv: str) -> tuple[int, str]:
        args = self.parser.parse_args(list(argv))
        out = io.StringIO()
        code: int = args.run(args, out)
        return code, out.getvalue()

    def names(self) -> list[str]:
        return [name for name, _ in self.adoption.calls]


@pytest.fixture
def rig() -> Rig:
    return Rig()


BLOCKING = DetectionReport(
    stack="fixture",
    detection=SAMPLE_DETECTION,
    issues=(
        Issue(IssueLevel.BLOCK, "git submodule vendor/lib", "remove the submodule"),
        Issue(IssueLevel.FIX, "uncommitted changes", "commit or stash them"),
        Issue(IssueLevel.NOTE, "active git hook pre-commit", "gates do not run it"),
    ),
)


# --- registration -----------------------------------------------------------------------------


def test_register_does_not_call_the_adoption_provider(rig: Rig) -> None:
    rig.parser.parse_args(["adopt", "start"])
    rig.parser.parse_args(["stack", "detect"])
    assert rig.provided == 0
    assert rig.adoption.calls == []


def test_register_adds_only_adopt_and_no_stack_command(rig: Rig) -> None:
    assert rig.commands_after_register == ["adopt"]


@pytest.mark.parametrize("leaf", ["start", "legacy", "finish", "abandon"])
def test_each_adopt_leaf_is_registered(rig: Rig, leaf: str) -> None:
    args = rig.parser.parse_args(["adopt", leaf])
    assert callable(args.run)


def test_adopt_needs_a_leaf_command(rig: Rig) -> None:
    with pytest.raises(SystemExit):
        rig.parser.parse_args(["adopt"])


# --- adopt start / finish / abandon -----------------------------------------------------------


@pytest.mark.parametrize("leaf", ["start", "finish", "abandon"])
def test_adopt_leaf_calls_the_adoption_with_the_found_app(rig: Rig, leaf: str) -> None:
    code, _ = rig.run("adopt", leaf)
    assert code == 0
    assert rig.adoption.calls == [(leaf, (rig.layouts.found,))]


def test_adopt_finds_the_app_from_the_current_directory(rig: Rig) -> None:
    rig.run("adopt", "start")
    assert ("find", (Path.cwd(),)) in rig.layouts.calls


@pytest.mark.parametrize("leaf", ["start", "finish", "abandon"])
def test_adopt_refusals_are_raised_not_printed(rig: Rig, leaf: str) -> None:
    def refuse(app: Any) -> None:
        raise BullError("refused", "do something")

    setattr(rig.adoption, leaf, refuse)
    with pytest.raises(BullError):
        rig.run("adopt", leaf)


# --- adopt legacy -----------------------------------------------------------------------------


def test_legacy_prints_one_field_path_line_per_entry(rig: Rig) -> None:
    rig.adoption.left = LegacyLeft(
        files=("src/fx/a.fx", "src/fx/b.fx"),
        declarations=("LegacyThing",),
        tests=("tests/a.test",),
        memo_files=("old/c.fx",),
    )
    code, out = rig.run("adopt", "legacy")
    assert code == 0
    assert out.splitlines() == [
        "files: src/fx/a.fx",
        "files: src/fx/b.fx",
        "declarations: LegacyThing",
        "tests: tests/a.test",
        "memo_files: old/c.fx",
    ]
    assert rig.adoption.calls == [("legacy", (rig.layouts.found,))]


def test_legacy_prints_the_default_mock_entries(rig: Rig) -> None:
    _, out = rig.run("adopt", "legacy")
    assert "files: src/fx/counter.fx" in out.splitlines()
    assert "tests: tests/counter.test" in out.splitlines()


def test_legacy_with_nothing_left_says_so(rig: Rig) -> None:
    rig.adoption.left = LegacyLeft((), (), (), ())
    code, out = rig.run("adopt", "legacy")
    assert code == 0
    assert out.strip() == "Nothing left to replace."


def test_legacy_with_entries_does_not_say_nothing_is_left(rig: Rig) -> None:
    _, out = rig.run("adopt", "legacy")
    assert "Nothing left to replace." not in out


def test_legacy_json_prints_the_four_lists(rig: Rig) -> None:
    rig.adoption.left = LegacyLeft(
        files=("src/fx/a.fx",),
        declarations=("LegacyThing",),
        tests=("tests/a.test",),
        memo_files=("old/c.fx",),
    )
    code, out = rig.run("adopt", "legacy", "--json")
    assert code == 0
    assert json.loads(out) == {
        "files": ["src/fx/a.fx"],
        "declarations": ["LegacyThing"],
        "tests": ["tests/a.test"],
        "memo_files": ["old/c.fx"],
    }


def test_legacy_json_with_nothing_left_prints_four_empty_lists(rig: Rig) -> None:
    rig.adoption.left = LegacyLeft((), (), (), ())
    _, out = rig.run("adopt", "legacy", "--json")
    assert json.loads(out) == {
        "files": [],
        "declarations": [],
        "tests": [],
        "memo_files": [],
    }


# --- stack detect -----------------------------------------------------------------------------


def test_detect_calls_the_adoption_with_the_app_root(rig: Rig) -> None:
    rig.run("stack", "detect")
    assert rig.adoption.calls == [("detect", (rig.layouts.found.root,))]  # type: ignore[union-attr]


def test_detect_outside_an_app_uses_the_current_directory(rig: Rig) -> None:
    rig.layouts.found = None
    rig.run("stack", "detect")
    assert rig.adoption.calls == [("detect", (Path.cwd(),))]


def test_detect_prints_the_stack_line_then_the_issues(rig: Rig) -> None:
    code, out = rig.run("stack", "detect")
    lines = out.splitlines()
    assert code == 0
    assert lines[0].startswith("stack: fixture (")
    assert "0.9" in lines[0]
    assert lines[0].endswith(f" — {SAMPLE_DETECTION.summary}")
    assert len(lines) == 2
    assert lines[1].startswith("note: active git hook pre-commit")


def test_detect_prints_each_issue_as_level_item_dash_fix(rig: Rig) -> None:
    rig.adoption.report = BLOCKING
    _, out = rig.run("stack", "detect")
    lines = out.splitlines()
    assert lines[1:] == [
        "block: git submodule vendor/lib — remove the submodule",
        "fix: uncommitted changes — commit or stash them",
        "note: active git hook pre-commit — gates do not run it",
    ]


def test_detect_prints_stack_none_when_nothing_matched(rig: Rig) -> None:
    rig.adoption.report = DetectionReport(
        None,
        None,
        (Issue(IssueLevel.BLOCK, "no stack recognizes this project", "pick one"),),
    )
    code, out = rig.run("stack", "detect")
    lines = out.splitlines()
    assert lines[0] == "stack: none"
    assert lines[1] == "block: no stack recognizes this project — pick one"
    assert code == 1


def test_detect_exits_zero_with_no_blocking_issue(rig: Rig) -> None:
    rig.adoption.report = DetectionReport(
        "fixture",
        SAMPLE_DETECTION,
        (Issue(IssueLevel.FIX, "uncommitted changes", "commit or stash them"),),
    )
    code, _ = rig.run("stack", "detect")
    assert code == 0


def test_detect_exits_one_when_blocked(rig: Rig) -> None:
    rig.adoption.report = BLOCKING
    code, _ = rig.run("stack", "detect")
    assert code == 1


def test_detect_without_apply_never_applies(rig: Rig) -> None:
    rig.run("stack", "detect")
    assert "apply" not in rig.names()


# --- stack detect --json ----------------------------------------------------------------------


def test_detect_json_prints_the_report_fields(rig: Rig) -> None:
    code, out = rig.run("stack", "detect", "--json")
    assert code == 0
    assert json.loads(out) == {
        "stack": "fixture",
        "confidence": 0.9,
        "summary": SAMPLE_DETECTION.summary,
        "settings": {"source_dir": "src/fx", "test_dir": "tests"},
        "issues": [{"level": "note", "item": "active git hook pre-commit", "fix": ""}],
        "blocked": False,
    }


def test_detect_json_lists_issue_levels_items_and_fixes(rig: Rig) -> None:
    rig.adoption.report = BLOCKING
    _, out = rig.run("stack", "detect", "--json")
    data = json.loads(out)
    assert data["issues"] == [
        {
            "level": "block",
            "item": "git submodule vendor/lib",
            "fix": "remove the submodule",
        },
        {"level": "fix", "item": "uncommitted changes", "fix": "commit or stash them"},
        {
            "level": "note",
            "item": "active git hook pre-commit",
            "fix": "gates do not run it",
        },
    ]
    assert data["blocked"] is True


def test_detect_json_exits_one_when_blocked(rig: Rig) -> None:
    rig.adoption.report = BLOCKING
    code, _ = rig.run("stack", "detect", "--json")
    assert code == 1


def test_detect_json_without_a_stack_reports_null_stack(rig: Rig) -> None:
    rig.adoption.report = DetectionReport(
        None,
        None,
        (Issue(IssueLevel.BLOCK, "no stack recognizes this project", "pick one"),),
    )
    code, out = rig.run("stack", "detect", "--json")
    data = json.loads(out)
    assert data["stack"] is None
    assert data["blocked"] is True
    assert code == 1


# --- stack detect --apply ---------------------------------------------------------------------


def test_apply_calls_apply_after_detecting_with_the_chosen_stack(rig: Rig) -> None:
    code, _ = rig.run("stack", "detect", "--apply", "python_cli")
    assert code == 0
    assert rig.adoption.calls == [
        ("detect", (rig.layouts.found.root,)),  # type: ignore[union-attr]
        ("apply", (rig.layouts.found, rig.adoption.report, "python_cli")),
    ]


def test_apply_still_prints_the_report(rig: Rig) -> None:
    _, out = rig.run("stack", "detect", "--apply", "fixture")
    assert out.splitlines()[0].startswith("stack: fixture (")


def test_apply_is_skipped_when_the_report_is_blocked(rig: Rig) -> None:
    rig.adoption.report = BLOCKING
    code, out = rig.run("stack", "detect", "--apply", "fixture")
    assert code == 1
    assert "apply" not in rig.names()
    assert "block: git submodule vendor/lib" in out


def test_apply_without_a_name_applies_the_detected_stack(rig: Rig) -> None:
    code, _ = rig.run("stack", "detect", "--apply")
    assert code == 0
    assert rig.adoption.calls == [
        ("detect", (rig.layouts.found.root,)),  # type: ignore[union-attr]
        ("apply", (rig.layouts.found, rig.adoption.report, None)),
    ]


def test_apply_without_a_name_still_prints_the_report(rig: Rig) -> None:
    _, out = rig.run("stack", "detect", "--apply")
    assert out.splitlines()[0].startswith("stack: fixture (")


def test_blocked_apply_says_so_on_stderr(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    rig.adoption.report = BLOCKING
    code, _ = rig.run("stack", "detect", "--apply", "fixture")
    assert code == 1
    assert "blocking issues; nothing applied" in capsys.readouterr().err


def test_blocked_apply_without_a_name_does_not_apply(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    rig.adoption.report = BLOCKING
    code, out = rig.run("stack", "detect", "--apply")
    assert code == 1
    assert "apply" not in rig.names()
    assert "blocking issues; nothing applied" in capsys.readouterr().err
    assert "blocking issues" not in out


def test_unblocked_apply_writes_nothing_to_stderr(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    rig.run("stack", "detect", "--apply")
    assert capsys.readouterr().err == ""
