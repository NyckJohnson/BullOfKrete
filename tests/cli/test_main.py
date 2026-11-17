"""Tests for `bull.Modules.cli.main`: dispatch, the preamble, error output and exit codes."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

import pytest

import bull
from bull.Modules.cli.help import render_help
from bull.Modules.cli.main import main
from bull.Modules.formats.mocks import MockFormats
from bull.Modules.foundation.Contracts import BullError, Layouts
from bull.Modules.foundation.mocks import MockLayouts, sample_layout
from bull.Modules.settings.Contracts import (
    ConfigError,
    ConfigProblem,
    Settings,
    SettingsLoader,
    StackLayer,
)
from bull.Modules.settings.mocks import MockSettingsLoader

_Run = Callable[[argparse.Namespace, TextIO], int]


class _Registered:
    """The commands a fake composition root adds, and what ran."""

    def __init__(self) -> None:
        self.ran: list[tuple[str, argparse.Namespace]] = []
        self.runs: dict[str, _Run] = {}

    def add(self, name: str, run: _Run | None = None) -> None:
        def default(args: argparse.Namespace, out: TextIO) -> int:
            return 0

        self.runs[name] = run or default


@dataclass
class _Wiring:
    """What `main` needs of the composition root (the seam `main(argv, wiring=…)`)."""

    layouts: Layouts
    formats: MockFormats
    settings_loader: SettingsLoader
    commands: _Registered
    stack_layer: Callable[[str], StackLayer] = field(
        default=lambda name: StackLayer((), {})
    )

    def register_commands(
        self, commands: argparse._SubParsersAction[argparse.ArgumentParser]
    ) -> None:
        for name, run in self.commands.runs.items():
            parser = commands.add_parser(name)
            parser.add_argument("rest", nargs="*")
            parser.add_argument("--json", action="store_true")
            parser.set_defaults(run=self._recording(name, run))

    def _recording(self, name: str, run: _Run) -> _Run:
        def wrapped(args: argparse.Namespace, out: TextIO) -> int:
            self.commands.ran.append((name, args))
            return run(args, out)

        return wrapped


class _FailingSettings(SettingsLoader):
    def __init__(self, error: Exception) -> None:
        self.error = error

    def load(self, app: object, stack_layer: Callable[[str], StackLayer]) -> Settings:
        raise self.error


def _make(
    names: tuple[str, ...] = ("status",),
    *,
    in_app: bool = True,
    loader: SettingsLoader | None = None,
) -> _Wiring:
    layouts = MockLayouts()
    if not in_app:
        layouts.found = None
    registered = _Registered()
    for name in names:
        registered.add(name)
    return _Wiring(
        layouts=layouts,
        formats=MockFormats(),
        settings_loader=loader or MockSettingsLoader(),
        commands=registered,
    )


def _calls(wiring: _Wiring, name: str) -> list[tuple[str, tuple[object, ...]]]:
    return [c for c in wiring.formats.calls if c[0] == name]


def test_main_dispatches_to_the_command_and_returns_its_exit_code(
    capsys: pytest.CaptureFixture[str],
) -> None:
    wiring = _make()

    def run(args: argparse.Namespace, out: TextIO) -> int:
        out.write("hello\n")
        return 3

    wiring.commands.runs["status"] = run

    code = main(["status"], wiring=wiring)

    assert code == 3
    assert capsys.readouterr().out == "hello\n"


def test_main_passes_the_command_arguments_to_the_command() -> None:
    wiring = _make()

    main(["status", "next", "--json"], wiring=wiring)

    ((name, args),) = wiring.commands.ran
    assert name == "status"
    assert args.rest == ["next"]
    assert args.json is True


def test_main_dispatches_only_the_named_command() -> None:
    wiring = _make(("status", "gates"))

    main(["gates"], wiring=wiring)

    assert [name for name, _ in wiring.commands.ran] == ["gates"]


# --- help and version -------------------------------------------------------------------


def test_main_without_arguments_prints_the_command_list(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main([], wiring=_make())

    assert code == 0
    assert capsys.readouterr().out.strip() == render_help().strip()


def test_main_help_prints_the_command_list(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main(["help"], wiring=_make())

    assert code == 0
    assert capsys.readouterr().out.strip() == render_help().strip()


def test_main_version_prints_the_version(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--version"], wiring=_make())

    assert code == 0
    assert bull.__version__ in capsys.readouterr().out


@pytest.mark.parametrize("argv", [[], ["help"], ["--version"]])
def test_help_and_version_do_not_check_formats_or_load_settings(
    argv: list[str],
) -> None:
    wiring = _make()

    main(argv, wiring=wiring)

    assert _calls(wiring, "check") == []
    assert wiring.settings_loader.calls == []  # type: ignore[attr-defined]


# --- the preamble -----------------------------------------------------------------------


def test_a_command_in_an_app_first_checks_formats_and_loads_settings() -> None:
    wiring = _make()

    main(["status"], wiring=wiring)

    assert _calls(wiring, "check") == [("check", (sample_layout(),))]
    loads = wiring.settings_loader.calls  # type: ignore[attr-defined]
    assert len(loads) == 1
    assert loads[0][1][0] == sample_layout()
    assert [name for name, _ in wiring.commands.ran] == ["status"]


@pytest.mark.parametrize("command", ["init", "doctor", "hook", "statusline", "migrate"])
def test_exempt_commands_skip_the_formats_check_and_settings(command: str) -> None:
    wiring = _make((command,))

    code = main([command], wiring=wiring)

    assert code == 0
    assert _calls(wiring, "check") == []
    assert wiring.settings_loader.calls == []  # type: ignore[attr-defined]
    assert [name for name, _ in wiring.commands.ran] == [command]


def test_a_command_outside_an_app_runs_without_the_formats_check() -> None:
    wiring = _make(in_app=False)

    code = main(["status"], wiring=wiring)

    assert code == 0
    assert _calls(wiring, "check") == []
    assert [name for name, _ in wiring.commands.ran] == ["status"]


def test_the_app_is_looked_up_from_the_current_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    wiring = _make()

    main(["status"], wiring=wiring)

    finds = [c for c in wiring.layouts.calls if c[0] == "find"]  # type: ignore[attr-defined]
    assert finds
    assert Path(str(finds[0][1][0])).resolve() == tmp_path.resolve()


def test_a_formats_failure_stops_the_command_with_the_error_and_exit_1(
    capsys: pytest.CaptureFixture[str],
) -> None:
    wiring = _make()
    wiring.formats.found = 0

    code = main(["status"], wiring=wiring)

    captured = capsys.readouterr()
    assert code == 1
    assert captured.err.startswith("bull: ")
    assert "  fix: bull migrate" in captured.err
    assert captured.out == ""
    assert wiring.commands.ran == []


def test_a_config_error_prints_file_line_key_message_lines_and_exits_1(
    capsys: pytest.CaptureFixture[str],
) -> None:
    error = ConfigError("settings are invalid")
    error.problems = [
        ConfigProblem(
            Path("/tmp/apps/tally/.bull/config.toml"),
            3,
            "pause_5h",
            "must be an integer",
        ),
        ConfigProblem(
            Path("/tmp/home/.config/bull/config.toml"), 7, "claude.model", "unknown key"
        ),
    ]
    wiring = _make(loader=_FailingSettings(error))

    code = main(["status"], wiring=wiring)

    captured = capsys.readouterr()
    assert code == 1
    lines = captured.err.splitlines()
    assert "/tmp/apps/tally/.bull/config.toml:3: pause_5h: must be an integer" in lines
    assert "/tmp/home/.config/bull/config.toml:7: claude.model: unknown key" in lines
    assert captured.out == ""
    assert wiring.commands.ran == []


# --- errors -----------------------------------------------------------------------------


def test_a_bull_error_prints_message_and_fix_on_stderr_and_exits_1(
    capsys: pytest.CaptureFixture[str],
) -> None:
    wiring = _make()

    def run(args: argparse.Namespace, out: TextIO) -> int:
        raise BullError("the thing broke", "do the other thing")

    wiring.commands.runs["status"] = run

    code = main(["status"], wiring=wiring)

    captured = capsys.readouterr()
    assert code == 1
    assert captured.err == "bull: the thing broke\n  fix: do the other thing\n"
    assert captured.out == ""


def test_any_other_exception_prints_a_summary_and_please_report_this_and_exits_70(
    capsys: pytest.CaptureFixture[str],
) -> None:
    wiring = _make()

    def run(args: argparse.Namespace, out: TextIO) -> int:
        raise RuntimeError("kaboom")

    wiring.commands.runs["status"] = run

    code = main(["status"], wiring=wiring)

    captured = capsys.readouterr()
    assert code == 70
    assert "kaboom" in captured.err
    assert "please report this" in captured.err
    assert "Traceback" not in captured.err
    assert captured.out == ""


# --- hooks and the status line never fail the session -----------------------------------


@pytest.mark.parametrize("error", [BullError("denied", "fix it"), RuntimeError("boom")])
def test_a_failing_hook_command_exits_0_with_details_on_stderr(
    error: Exception, capsys: pytest.CaptureFixture[str]
) -> None:
    wiring = _make(("hook",))

    def run(args: argparse.Namespace, out: TextIO) -> int:
        raise error

    wiring.commands.runs["hook"] = run

    code = main(["hook", "before-shell"], wiring=wiring)

    captured = capsys.readouterr()
    assert code == 0
    assert captured.out == ""
    assert str(error) in captured.err


@pytest.mark.parametrize("error", [BullError("denied", "fix it"), RuntimeError("boom")])
def test_a_failing_statusline_command_prints_a_plain_line_and_exits_0(
    error: Exception, capsys: pytest.CaptureFixture[str]
) -> None:
    wiring = _make(("statusline",))

    def run(args: argparse.Namespace, out: TextIO) -> int:
        raise error

    wiring.commands.runs["statusline"] = run

    code = main(["statusline"], wiring=wiring)

    captured = capsys.readouterr()
    assert code == 0
    assert captured.out == "bull\n"
    assert str(error) in captured.err


# --- --json -----------------------------------------------------------------------------


def test_json_output_is_the_only_thing_on_stdout(
    capsys: pytest.CaptureFixture[str],
) -> None:
    wiring = _make()

    def run(args: argparse.Namespace, out: TextIO) -> int:
        out.write(json.dumps({"ok": True}) + "\n")
        return 0

    wiring.commands.runs["status"] = run

    code = main(["status", "--json"], wiring=wiring)

    captured = capsys.readouterr()
    assert code == 0
    assert json.loads(captured.out) == {"ok": True}


def test_json_output_stays_clean_when_the_command_is_refused(
    capsys: pytest.CaptureFixture[str],
) -> None:
    wiring = _make()
    wiring.formats.found = 0

    code = main(["status", "--json"], wiring=wiring)

    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    assert captured.err != ""


# --- hook and statusline never fail the session ------------------------------------------

_HOOK_NAMES = [
    "session-start",
    "before-agent",
    "before-shell",
    "before-edit",
    "before-read",
    "agent-end",
]


@dataclass
class _BrokenTable(_Wiring):
    """A composition root whose command table cannot be built."""

    def register_commands(
        self, commands: argparse._SubParsersAction[argparse.ArgumentParser]
    ) -> None:
        raise RuntimeError("table exploded")


@dataclass
class _RealisticTable(_Wiring):
    """Registers `hook` (a fixed set of kinds) and `statusline`, like the real table."""

    def register_commands(
        self, commands: argparse._SubParsersAction[argparse.ArgumentParser]
    ) -> None:
        hook = commands.add_parser("hook")
        hook.add_argument("kind", choices=_HOOK_NAMES)
        hook.set_defaults(run=lambda args, out: 0)
        line = commands.add_parser("statusline")
        line.set_defaults(run=lambda args, out: 0)


def _broken() -> _BrokenTable:
    return _BrokenTable(
        layouts=MockLayouts(),
        formats=MockFormats(),
        settings_loader=MockSettingsLoader(),
        commands=_Registered(),
    )


def _realistic() -> _RealisticTable:
    return _RealisticTable(
        layouts=MockLayouts(),
        formats=MockFormats(),
        settings_loader=MockSettingsLoader(),
        commands=_Registered(),
    )


@pytest.mark.parametrize("kind", _HOOK_NAMES)
def test_a_hook_exits_zero_with_empty_stdout_when_the_command_table_cannot_be_built(
    kind: str, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["hook", kind], wiring=_broken())

    captured = capsys.readouterr()
    assert code == 0
    assert captured.out == ""
    assert "table exploded" in captured.err


def test_statusline_prints_a_plain_line_when_the_command_table_cannot_be_built(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main(["statusline"], wiring=_broken())

    captured = capsys.readouterr()
    assert code == 0
    assert captured.out == "bull\n"
    assert "table exploded" in captured.err


def test_a_hook_exits_zero_with_empty_stdout_when_the_wiring_cannot_be_built(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def failing() -> object:
        raise RuntimeError("wiring exploded")

    monkeypatch.setattr("bull.Modules.cli.main.get_wiring", failing)

    code = main(["hook", "before-shell"])

    captured = capsys.readouterr()
    assert code == 0
    assert captured.out == ""
    assert "wiring exploded" in captured.err


def test_statusline_prints_a_plain_line_when_the_wiring_cannot_be_built(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def failing() -> object:
        raise RuntimeError("wiring exploded")

    monkeypatch.setattr("bull.Modules.cli.main.get_wiring", failing)

    code = main(["statusline"])

    captured = capsys.readouterr()
    assert code == 0
    assert captured.out == "bull\n"
    assert "wiring exploded" in captured.err


@pytest.mark.parametrize("argv", [["hook", "bad-kind"], ["hook"]])
def test_a_hook_whose_arguments_do_not_parse_allows_instead_of_exiting_two(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(argv, wiring=_realistic())

    captured = capsys.readouterr()
    assert code == 0
    assert captured.out == ""
    assert captured.err != ""


def test_statusline_whose_arguments_do_not_parse_still_prints_a_plain_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main(["statusline", "--bogus"], wiring=_realistic())

    assert code == 0
    assert capsys.readouterr().out == "bull\n"


def test_other_commands_still_exit_two_when_their_arguments_do_not_parse() -> None:
    assert main(["status", "--bogus"], wiring=_realistic()) == 2


def test_a_parent_command_without_a_subcommand_prints_help_on_stderr_and_exits_2(
    capsys: pytest.CaptureFixture[str],
) -> None:
    class _ParentWiring(_Wiring):
        def register_commands(
            self, commands: argparse._SubParsersAction[argparse.ArgumentParser]
        ) -> None:
            commands.add_parser("group")  # no `run`: needs a subcommand

    base = _make()
    wiring = _ParentWiring(
        layouts=base.layouts,
        formats=base.formats,
        settings_loader=base.settings_loader,
        commands=base.commands,
    )

    code = main(["group"], wiring=wiring)

    captured = capsys.readouterr()
    assert code == 2
    assert captured.err == render_help()
    assert captured.out == ""


def test_a_config_error_with_problems_and_a_fix_prints_the_fix_after_the_problems(
    capsys: pytest.CaptureFixture[str],
) -> None:
    error = ConfigError("settings are invalid", "edit the file")
    error.problems = [ConfigProblem(Path("/tmp/c.toml"), 3, "pause_5h", "bad")]

    code = main(["status"], wiring=_make(loader=_FailingSettings(error)))

    lines = capsys.readouterr().err.splitlines()
    assert code == 1
    assert lines == [
        "bull: settings are invalid",
        "/tmp/c.toml:3: pause_5h: bad",
        "  fix: edit the file",
    ]


def test_argparse_exit_with_a_string_message_prints_it_and_returns_1(
    capsys: pytest.CaptureFixture[str],
) -> None:
    class _ExitWiring(_Wiring):
        def register_commands(
            self, commands: argparse._SubParsersAction[argparse.ArgumentParser]
        ) -> None:
            parser = commands.add_parser("status")

            class _Action(argparse.Action):
                def __call__(self, parser, namespace, values, option_string=None):  # type: ignore[no-untyped-def]
                    raise SystemExit("custom stop message")

            parser.add_argument("--stop", nargs=0, action=_Action)

    base = _make()
    wiring = _ExitWiring(
        layouts=base.layouts,
        formats=base.formats,
        settings_loader=base.settings_loader,
        commands=base.commands,
    )

    code = main(["status", "--stop"], wiring=wiring)

    assert code == 1
    assert capsys.readouterr().err == "custom stop message\n"


def test_argparse_exit_without_a_code_returns_0() -> None:
    class _ExitWiring(_Wiring):
        def register_commands(
            self, commands: argparse._SubParsersAction[argparse.ArgumentParser]
        ) -> None:
            parser = commands.add_parser("status")

            class _Action(argparse.Action):
                def __call__(self, parser, namespace, values, option_string=None):  # type: ignore[no-untyped-def]
                    raise SystemExit

            parser.add_argument("--stop", nargs=0, action=_Action)

    base = _make()
    wiring = _ExitWiring(
        layouts=base.layouts,
        formats=base.formats,
        settings_loader=base.settings_loader,
        commands=base.commands,
    )

    assert main(["status", "--stop"], wiring=wiring) == 0
