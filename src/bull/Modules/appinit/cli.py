"""`bull init`, `bull open` and `bull doctor` commands.

Follows the module `cli.py` convention: collaborators arrive as zero-argument providers,
called only when a command runs; each leaf parser sets `run(args, out) -> int`; refusals are
raised (`BullError` and subclasses), never printed here.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

from bull.Modules.appinit.Contracts import AppInit, Doctor, DoctorReport, InitResult
from bull.Modules.stacks.Contracts import CheckItem

_Run = Callable[[argparse.Namespace, TextIO], int]


def register(
    commands: argparse._SubParsersAction[argparse.ArgumentParser],
    *,
    app_init: Callable[[], AppInit],
    doctor: Callable[[], Doctor],
    stack_init: Callable[[], Callable[[Path], InitResult]],
) -> None:
    """Add `init`, `open` and `doctor`.

    `stack_init` provides the `bull init --stack` initializer. Every provider is called only
    when its command runs.
    """
    init = commands.add_parser(
        "init", help="new app, relink, adoption start, or stack repo"
    )
    init.add_argument("path", nargs="?", default=".", type=Path)
    mode = init.add_mutually_exclusive_group()
    mode.add_argument(
        "--adopt", action="store_true", help="bring an existing project under bull"
    )
    mode.add_argument("--stack", action="store_true", help="create a stack repo")
    init.set_defaults(run=_init(app_init, stack_init))

    open_parser = commands.add_parser(
        "open", help="render the plugin and launch the assistant"
    )
    open_parser.add_argument("path", nargs="?", default=".")
    open_parser.add_argument(
        "--print-command", action="store_true", help="print the command, don't run it"
    )
    open_parser.add_argument(
        "extra", nargs="*", help="arguments for the assistant, after `--`"
    )
    open_parser.set_defaults(run=_open(app_init))

    doctor_parser = commands.add_parser("doctor", help="check install and toolchains")
    doctor_parser.add_argument("--json", action="store_true", help="write JSON only")
    doctor_parser.set_defaults(run=_doctor(doctor))


# --- runners


def _init(
    app_init: Callable[[], AppInit],
    stack_init: Callable[[], Callable[[Path], InitResult]],
) -> _Run:
    def run(args: argparse.Namespace, out: TextIO) -> int:
        path: Path = args.path
        if args.stack:
            result = stack_init()(path)
            out.write(f"stack repo created at {result.root}\n")
            return 0
        result = app_init().init(path, adopt=args.adopt)
        out.write(_init_text(result))
        return 0

    return run


def _open(app_init: Callable[[], AppInit]) -> _Run:
    def run(args: argparse.Namespace, out: TextIO) -> int:
        path, extra = _split_open_args(args.path, list(args.extra))
        argv = app_init().open_argv(path, extra)
        if args.print_command:
            out.write(shlex.join(argv) + "\n")
            return 0
        os.execvp(argv[0], argv)
        return 0

    return run


def _doctor(doctor: Callable[[], Doctor]) -> _Run:
    def run(args: argparse.Namespace, out: TextIO) -> int:
        report = doctor().run()
        if args.json:
            out.write(json.dumps(_doctor_json(report), indent=2) + "\n")
        else:
            out.write(_doctor_text(report))
        return 0 if report.ok else 1

    return run


# --- helpers


def _split_open_args(path: str, extra: list[str]) -> tuple[Path, list[str]]:
    """Separate the app path from the assistant's arguments.

    Some argument parser versions keep the `--` separator in `extra`, and with no path given
    the first word after `--` lands in `path` (a path never starts with `-`).
    """
    if path == "--":
        path = "."
    elif path.startswith("-"):
        path, extra = ".", [path, *extra]
    if extra[:1] == ["--"]:
        extra = extra[1:]
    return Path(path), extra


def _init_text(result: InitResult) -> str:
    if result.adopting:
        return f"adoption started at {result.root}\n"
    if result.relinked:
        return f"relinked the bull app at {result.root}\n"
    return f"bull app created at {result.root}\n"


def _item_line(item: CheckItem) -> str:
    line = f"  {'ok' if item.ok else 'missing'}  {item.item}\n"
    if not item.ok and item.fix:
        line += f"        fix: {item.fix}\n"
    return line


def _doctor_text(report: DoctorReport) -> str:
    text = "".join(_item_line(item) for item in report.items)
    for name, items in report.stacks:
        text += f"stack {name} (informational):\n"
        text += "".join(_item_line(item) for item in items) or "  no required tools\n"
    text += "all core checks pass\n" if report.ok else "some core checks fail\n"
    return text


def _item_json(item: CheckItem) -> dict[str, object]:
    return {"item": item.item, "ok": item.ok, "fix": item.fix}


def _doctor_json(report: DoctorReport) -> dict[str, object]:
    return {
        "ok": report.ok,
        "items": [_item_json(item) for item in report.items],
        "stacks": [
            {"name": name, "items": [_item_json(item) for item in items]}
            for name, items in report.stacks
        ],
    }
