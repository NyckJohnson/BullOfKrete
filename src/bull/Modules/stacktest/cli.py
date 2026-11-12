"""`bull stack test`."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

from bull.Modules.stacks.Contracts import Stack, StackError, StackRegistry
from bull.Modules.stacktest.Contracts import StackTester, StackTestReport


def register(
    stack_leaves: argparse._SubParsersAction[argparse.ArgumentParser],
    tester: Callable[[], StackTester],
    registry: Callable[[], StackRegistry],
) -> None:
    """Add `test` to the `stack` command's subcommands (owned by stacks.cli)."""

    def run(args: argparse.Namespace, out: TextIO) -> int:
        """Raises StackError for `--static` with `--case`, or an unknown stack."""
        if args.static and args.case is not None:
            raise StackError("`--static` and `--case` cannot be used together")
        stack = _load(registry(), args.stack)
        provided = tester()
        report = (
            provided.static(stack) if args.static else provided.run(stack, args.case)
        )
        if args.json:
            out.write(json.dumps(_report_json(report), indent=2, sort_keys=True) + "\n")
        else:
            out.write(provided.render(report))
        return 0 if report.ok else 1

    parser = stack_leaves.add_parser(
        "test",
        help="Self-test a stack: its static shape, or its cases against its fixture",
    )
    parser.add_argument(
        "stack", metavar="NAME|PATH", help="A stack name or a stack folder"
    )
    parser.add_argument(
        "--static", action="store_true", help="Only check the folder's shape"
    )
    parser.add_argument("--case", metavar="ID", default=None, help="Run only this case")
    parser.add_argument("--json", action="store_true", help="Print the report as JSON")
    parser.set_defaults(run=run)


def _is_path(argument: str) -> bool:
    """A path has a separator or names an existing folder; anything else is a name."""
    separators = {os.sep, "/"} | ({os.altsep} if os.altsep else set())
    return any(sep in argument for sep in separators) or Path(argument).is_dir()


def _load(registry: StackRegistry, argument: str) -> Stack:
    if _is_path(argument):
        return registry.load_path(Path(argument))
    return registry.get(argument)


def _report_json(report: StackTestReport) -> dict[str, object]:
    return {
        "stack": report.stack,
        "static": report.static,
        "problems": list(report.problems),
        "cases": [
            {
                "id": result.id,
                "verdict": result.verdict.value,
                "expected": result.expected,
                "got": result.got,
            }
            for result in report.cases
        ],
    }
