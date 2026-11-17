"""`bull`'s entry point: dispatches a command and returns its exit code."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from bull import __version__
from bull.Modules.cli.help import render_help
from bull.Modules.cli.wiring import Wiring, describe_error, get_wiring
from bull.Modules.foundation.Contracts import BullError
from bull.Modules.settings.Contracts import ConfigError, ConfigProblem

# Commands that run without the formats check and settings load (help and --version are
# answered before parsing).
_EXEMPT = frozenset({"init", "doctor", "help", "hook", "statusline", "migrate"})
_HELP = frozenset({"help", "-h", "--help"})

# Exit codes: a reported error, and a bull bug (EX_SOFTWARE).
_ERROR = 1
_INTERNAL = 70


def main(argv: Sequence[str] | None = None, *, wiring: Wiring | None = None) -> int:
    """Run the `bull` command line `argv` (default: `sys.argv[1:]`); return the exit code.

    No arguments or `help` prints the command list; `--version` the version. Inside an app,
    every command but `init`, `doctor`, `hook`, `statusline` and `migrate` first checks file
    formats and loads settings. A `BullError` prints `bull: <message>` and `  fix: <fix>` on
    stderr (exit 1); any other exception a one-line summary (exit 70). `hook` and `statusline`
    never fail the session: they exit 0 (the status line printing `bull`), details on stderr.
    `wiring` replaces the real composition root (tests).
    """
    words = list(sys.argv[1:] if argv is None else argv)
    if not words or words[0] in _HELP:
        sys.stdout.write(render_help())
        return 0
    if words[0] == "--version":
        sys.stdout.write(f"bull {__version__}\n")
        return 0

    command: str | None = None
    try:
        built = wiring if wiring is not None else get_wiring()
        parser = argparse.ArgumentParser(prog="bull", description="See `bull help`.")
        parser.add_argument(
            "--version", action="version", version=f"bull {__version__}"
        )
        commands = parser.add_subparsers(dest="command", metavar="<command>")
        built.register_commands(commands)
        try:
            args = parser.parse_args(words)
        except SystemExit as stop:  # argparse: --help (0) or a usage error (2)
            return _exit_code(stop.code)
        command = args.command
        run = getattr(args, "run", None)
        if run is None:
            sys.stderr.write(render_help())
            return 2
        if command not in _EXEMPT:
            _preamble(built)
        code: int = run(args, sys.stdout)
        return code
    except Exception as error:  # noqa: BLE001 - every failure is reported; none escapes as a traceback
        return _failed(command, error)


def _preamble(wiring: Wiring) -> None:
    """Inside an app: check its file formats, then load (and so validate) its settings."""
    app = wiring.layouts.find(Path.cwd())
    if app is None:
        return
    wiring.formats.check(app)
    wiring.settings_loader.load(app, wiring.stack_layer)


def _failed(command: str | None, error: Exception) -> int:
    """Report `error` on stderr and return the exit code for it."""
    if command == "hook":
        sys.stderr.write(
            f"bull hook: allowed after an error: {describe_error(error)}\n"
        )
        return 0
    if command == "statusline":
        sys.stdout.write("bull\n")
        sys.stderr.write(f"bull statusline: {describe_error(error)}\n")
        return 0
    if isinstance(error, ConfigError):
        problems: list[ConfigProblem] = getattr(error, "problems", None) or []
        if problems:
            sys.stderr.write(f"bull: {error.message}\n")
            for problem in problems:
                sys.stderr.write(
                    f"{problem.file}:{problem.line}: {problem.key}: {problem.message}\n"
                )
            if error.fix:
                sys.stderr.write(f"  fix: {error.fix}\n")
            return _ERROR
    if isinstance(error, BullError):
        sys.stderr.write(f"bull: {error.message}\n")
        if error.fix:
            sys.stderr.write(f"  fix: {error.fix}\n")
        return _ERROR
    sys.stderr.write(
        f"bull: unexpected error: {type(error).__name__}: {error} (please report this)\n"
    )
    return _INTERNAL


def _exit_code(code: str | int | None) -> int:
    """`SystemExit.code` as an exit status."""
    if code is None:
        return 0
    if isinstance(code, int):
        return code
    sys.stderr.write(f"{code}\n")
    return _ERROR
