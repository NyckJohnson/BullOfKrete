"""`bull gates …` and `bull coverage <M>`."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from typing import TextIO

from bull.Modules.coverage.Contracts import CoverageTriage
from bull.Modules.foundation.Contracts import AppLayout, BullError
from bull.Modules.gates.Contracts import GateMode, GateRequest, Gates, Verdict
from bull.Modules.gates.report import coverage_json, run_json

_EXIT = {Verdict.PASS: 0, Verdict.FAIL: 1, Verdict.ABORTED: 2}
_USAGE_FIX = (
    "use one of `bull gates <M> [--fast|--coverage-report|--skip-coverage]`, "
    "`--failed`, `--all [--skip-coverage]`, `--after-merge <branch>`, `--journeys`"
)


def register(
    commands: argparse._SubParsersAction[argparse.ArgumentParser],
    gates: Callable[[], Gates],
    app: Callable[[], AppLayout],
    triage: Callable[[], CoverageTriage],
) -> None:
    """Add `bull gates` and `bull coverage`; providers are called only when one runs."""
    _register_gates(commands, gates, app)
    _register_coverage(commands, gates, app, triage)


def _register_gates(
    commands: argparse._SubParsersAction[argparse.ArgumentParser],
    gates: Callable[[], Gates],
    app: Callable[[], AppLayout],
) -> None:
    parser = commands.add_parser("gates", help="Run the gates")
    parser.add_argument("module", nargs="?", help="The module to gate")
    parser.add_argument(
        "--fast", action="store_true", help="Module tests only, no coverage"
    )
    parser.add_argument(
        "--coverage-report",
        action="store_true",
        help="Stop after coverage; print the report",
    )
    parser.add_argument(
        "--skip-coverage",
        action="store_true",
        help="Skip coverage (nothing is recorded)",
    )
    parser.add_argument("--failed", action="store_true", help="Rerun the failed tests")
    parser.add_argument("--all", action="store_true", help="Every part and module")
    parser.add_argument(
        "--after-merge", metavar="BRANCH", help="On the base after merging BRANCH"
    )
    parser.add_argument("--journeys", action="store_true", help="Journey tests only")
    parser.add_argument("--json", action="store_true", help="Print the run as JSON")

    def run(args: argparse.Namespace, out: TextIO) -> int:
        request = _request(args)
        gate_runner = gates()
        result = gate_runner.run(app(), request)
        if args.json:
            out.write(json.dumps(run_json(result), indent=2) + "\n")
        else:
            text = gate_runner.render(result)
            out.write(text if text.endswith("\n") else text + "\n")
        return _EXIT[result.verdict]

    parser.set_defaults(run=run)


def _request(args: argparse.Namespace) -> GateRequest:
    """The gate request the flags name; `BullError` for a combination that makes no sense."""
    chosen = [
        name
        for name, given in (
            ("<M>", args.module is not None),
            ("--failed", args.failed),
            ("--all", args.all),
            ("--after-merge", args.after_merge is not None),
            ("--journeys", args.journeys),
        )
        if given
    ]
    if len(chosen) != 1:
        what = "nothing" if not chosen else " and ".join(chosen)
        raise BullError(f"gates needs exactly one mode, got {what}", _USAGE_FIX)
    if (args.fast or args.coverage_report) and args.module is None:
        raise BullError("--fast and --coverage-report need a module", _USAGE_FIX)
    if args.fast and args.coverage_report:
        raise BullError(
            "--fast and --coverage-report can't be used together", _USAGE_FIX
        )
    if args.skip_coverage and not (
        (args.module is not None and not args.fast and not args.coverage_report)
        or args.all
    ):
        raise BullError("--skip-coverage goes only with `<M>` or `--all`", _USAGE_FIX)
    if args.module is not None:
        mode = (
            GateMode.FAST
            if args.fast
            else GateMode.COVERAGE_REPORT
            if args.coverage_report
            else GateMode.MODULE
        )
        return GateRequest(mode, args.module, skip_coverage=args.skip_coverage)
    if args.all:
        return GateRequest(GateMode.ALL, skip_coverage=args.skip_coverage)
    if args.after_merge is not None:
        return GateRequest(GateMode.AFTER_MERGE, branch=args.after_merge)
    if args.failed:
        return GateRequest(GateMode.FAILED)
    return GateRequest(GateMode.JOURNEYS)


def _register_coverage(
    commands: argparse._SubParsersAction[argparse.ArgumentParser],
    gates: Callable[[], Gates],
    app: Callable[[], AppLayout],
    triage: Callable[[], CoverageTriage],
) -> None:
    parser = commands.add_parser(
        "coverage", help="Coverage triage from the last full gates run"
    )
    parser.add_argument("module", help="The module whose coverage to report")
    parser.add_argument("--json", action="store_true", help="Print the report as JSON")

    def run(args: argparse.Namespace, out: TextIO) -> int:
        report = gates().coverage(app(), args.module)
        if args.json:
            out.write(json.dumps(coverage_json(report), indent=2) + "\n")
        else:
            text = triage().render(report)
            out.write(text if text.endswith("\n") else text + "\n")
        return 0 if report.clean else 1

    parser.set_defaults(run=run)
