"""`bull adopt …` and `bull stack detect`.

Thin wiring over `Adoption`: the provider is called only when a command runs, and refusals
(`BullError`s) are raised for `cli.main` to report, never printed here.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

from bull.Modules.adoption.Contracts import Adoption, DetectionReport
from bull.Modules.adoption.legacy import left_lines
from bull.Modules.foundation.Contracts import AppLayout, BullError, Layouts

_Run = Callable[[argparse.Namespace, TextIO], int]
_Provider = Callable[[], Adoption]
# `--apply` absent: distinct from `--apply` with no name, which parses as None.
_NOT_APPLYING = object()


def register(
    commands: argparse._SubParsersAction[argparse.ArgumentParser],
    adoption: _Provider,
    layouts: Layouts,
) -> None:
    """Add `adopt` and its subcommands; `adoption` is called only when one runs."""
    adopt = commands.add_parser("adopt", help="Adopt an app built outside the pipeline")
    leaves = adopt.add_subparsers(dest="adopt_command", required=True)

    def step(action: Callable[[Adoption, AppLayout], None]) -> _Run:
        def run(args: argparse.Namespace, out: TextIO) -> int:
            action(adoption(), _app(layouts))
            return 0

        return run

    steps: tuple[tuple[str, str, Callable[[Adoption, AppLayout], None]], ...] = (
        ("start", "Start adopting this app on adopt/main", lambda a, app: a.start(app)),
        (
            "finish",
            "Finish the adoption (stage 6, no legacy left)",
            lambda a, app: a.finish(app),
        ),
        (
            "abandon",
            "Abandon the adoption, keeping the trunk",
            lambda a, app: a.abandon(app),
        ),
    )
    for name, text, action in steps:
        leaves.add_parser(name, help=text).set_defaults(run=step(action))

    def run_legacy(args: argparse.Namespace, out: TextIO) -> int:
        left = adoption().legacy(_app(layouts))
        if args.json:
            data = {
                "files": list(left.files),
                "declarations": list(left.declarations),
                "tests": list(left.tests),
                "memo_files": list(left.memo_files),
            }
            out.write(json.dumps(data, indent=2) + "\n")
        elif left.empty:
            out.write("Nothing left to replace.\n")
        else:
            out.writelines(f"{line}\n" for line in left_lines(left))
        return 0

    legacy = leaves.add_parser("legacy", help="List the legacy code left to replace")
    legacy.add_argument("--json", action="store_true", help="Print JSON")
    legacy.set_defaults(run=run_legacy)


def register_detect(
    stack_leaves: argparse._SubParsersAction[argparse.ArgumentParser],
    adoption: _Provider,
    layouts: Layouts,
) -> None:
    """Add `detect` to the `stack` command's subcommands (owned by stacks.cli)."""

    def run(args: argparse.Namespace, out: TextIO) -> int:
        app = layouts.find(Path.cwd())
        root = app.root if app is not None else Path.cwd()
        provided = adoption()
        report = provided.detect(root)
        if args.json:
            out.write(json.dumps(_report_json(report), indent=2) + "\n")
        else:
            out.writelines(f"{line}\n" for line in _report_lines(report))
        applying = args.apply is not _NOT_APPLYING
        if report.blocked:
            if applying:
                sys.stderr.write("blocking issues; nothing applied\n")
            return 1
        if applying:
            if app is None:
                raise BullError(
                    "`--apply` needs a bull app here",
                    "run `bull init` in the app's folder, or cd into a bull app",
                )
            provided.apply(app, report, args.apply)
        return 0

    detect = stack_leaves.add_parser(
        "detect", help="Detect this project's stack and what blocks adopting it"
    )
    detect.add_argument(
        "--apply",
        nargs="?",
        const=None,
        default=_NOT_APPLYING,
        metavar="STACK",
        help="Select STACK, or the detected stack when none is named (and its detected "
        "settings)",
    )
    detect.add_argument("--json", action="store_true", help="Print JSON")
    detect.set_defaults(run=run)


def _app(layouts: Layouts) -> AppLayout:
    app = layouts.find(Path.cwd())
    if app is None:
        raise BullError(
            "not a bull app (no .bull/ folder here or above)",
            "run `bull init` in the app's folder, or cd into a bull app",
        )
    return app


def _report_lines(report: DetectionReport) -> list[str]:
    if report.stack is None or report.detection is None:
        lines = ["stack: none"]
    else:
        d = report.detection
        lines = [f"stack: {report.stack} ({d.confidence}) — {d.summary}"]
    lines.extend(
        f"{issue.level.value}: {issue.item} — {issue.fix}" for issue in report.issues
    )
    return lines


def _report_json(report: DetectionReport) -> dict[str, object]:
    d = report.detection
    return {
        "stack": report.stack,
        "confidence": None if d is None else d.confidence,
        "summary": None if d is None else d.summary,
        "settings": {} if d is None else dict(d.settings),
        "issues": [
            {"level": i.level.value, "item": i.item, "fix": i.fix}
            for i in report.issues
        ],
        "blocked": report.blocked,
    }
