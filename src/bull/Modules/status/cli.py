"""`bull status …` commands.

Thin wiring over `StatusStore`, `Refs`, `Progress` and `Usage`: each provider is called only
when a command that needs it runs, and refusals (`StatusError` and other `BullError`s) are
raised for `cli.main` to report, never printed here.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from typing import TextIO

from bull.Modules.memo.Contracts import Memo
from bull.Modules.status.Contracts import (
    ModuleState,
    Progress,
    Refs,
    StatusError,
    StatusStore,
    UnitState,
)
from bull.Modules.status.model import time_to_text
from bull.Modules.usage.Contracts import Usage

_Run = Callable[[argparse.Namespace, TextIO], int]


def register(
    commands: argparse._SubParsersAction[argparse.ArgumentParser],
    store: Callable[[], StatusStore],
    refs: Callable[[], Refs],
    progress: Callable[[], Progress],
    usage: Callable[[], Usage],
    memo: Callable[[], Memo],
) -> None:
    """Add `status` and its subcommands; providers are called only when one runs."""
    status = commands.add_parser("status", help="Pipeline state: summary and changes")
    status.add_argument("--json", action="store_true", help="Print JSON")

    def run_summary(args: argparse.Namespace, out: TextIO) -> int:
        if args.json:
            _write_json(out, progress().as_json())
        else:
            out.write(progress().summary())
        return 0

    status.set_defaults(run=run_summary)
    leaves = status.add_subparsers(dest="status_command")

    def leaf(name: str, help_: str, run: _Run) -> argparse.ArgumentParser:
        parser = leaves.add_parser(name, help=help_)
        parser.set_defaults(run=run)
        return parser

    def run_next(args: argparse.Namespace, out: TextIO) -> int:
        out.write(f"{progress().next_step().text}\n")
        return 0

    leaf("next", "Print the next step", run_next)

    def run_stage(args: argparse.Namespace, out: TextIO) -> int:
        store().set_stage(args.stage)
        return 0

    leaf("stage", "Set the current track's stage", run_stage).add_argument(
        "stage", type=int
    )

    def run_checkpoint(args: argparse.Namespace, out: TextIO) -> int:
        store().checkpoint(args.name)
        return 0

    leaf("checkpoint", "Record a checkpoint", run_checkpoint).add_argument("name")

    def run_init_modules(args: argparse.Namespace, out: TextIO) -> int:
        store().init_modules(memo(), replace=args.replace)
        return 0

    leaf(
        "init-modules", "Create the modules and units from the memo", run_init_modules
    ).add_argument(
        "--replace", action="store_true", help="Replace modules already started"
    )

    def run_module(args: argparse.Namespace, out: TextIO) -> int:
        store().set_module(args.module, ModuleState(args.state))
        return 0

    module = leaf("module", "Set a module's state", run_module)
    module.add_argument("module")
    module.add_argument("state", choices=[s.value for s in ModuleState])

    def run_unit(args: argparse.Namespace, out: TextIO) -> int:
        store().set_unit(args.module, args.number, UnitState(args.state))
        return 0

    unit = leaf("unit", "Set a unit's state", run_unit)
    unit.add_argument("module")
    unit.add_argument("number", type=int)
    unit.add_argument("state", choices=[s.value for s in UnitState])

    def run_attempt(args: argparse.Namespace, out: TextIO) -> int:
        store().attempt(args.module, args.number)
        return 0

    attempt = leaf("attempt", "Count another attempt on a unit", run_attempt)
    attempt.add_argument("module")
    attempt.add_argument("number", type=int)

    def run_unblock(args: argparse.Namespace, out: TextIO) -> int:
        store().unblock(args.module, args.number)
        return 0

    unblock = leaf("unblock", "Unblock a unit", run_unblock)
    unblock.add_argument("module")
    unblock.add_argument("number", type=int)

    def run_pause(args: argparse.Namespace, out: TextIO) -> int:
        store().pause(args.reason)
        return 0

    leaf("pause", "Pause the pipeline", run_pause).add_argument("reason")

    def run_resume(args: argparse.Namespace, out: TextIO) -> int:
        store().resume()
        return 0

    leaf("resume", "Clear a pause", run_resume)

    def run_wait(args: argparse.Namespace, out: TextIO) -> int:
        store().wait(args.module, args.what)
        return 0

    wait = leaf("wait", "Wait for the human to approve a contract change", run_wait)
    wait.add_argument("module")
    wait.add_argument("what")

    def run_approve(args: argparse.Namespace, out: TextIO) -> int:
        store().approve(args.module, args.note)
        return 0

    approve = leaf("approve", "Record the human's approval", run_approve)
    approve.add_argument("module")
    approve.add_argument("note")

    def run_refscan(args: argparse.Namespace, out: TextIO) -> int:
        store().record_scan(
            args.module, args.covered, args.missed, args.contradicts, args.not_in_spec
        )
        return 0

    refscan = leaf("refscan", "Record a reference-test scan", run_refscan)
    refscan.add_argument("module")
    for count in ("--covered", "--missed", "--contradicts", "--not-in-spec"):
        refscan.add_argument(count, type=int, required=True)

    def run_plan(args: argparse.Namespace, out: TextIO) -> int:
        if args.clear:
            store().clear_plan()
        elif not args.items:
            raise StatusError(
                f"plan {args.label} needs at least one item, or --clear to clear it"
            )
        else:
            store().set_plan(args.label, args.items)
        return 0

    plan = leaf("plan", "Set or clear the progress plan", run_plan)
    plan.add_argument("label")
    plan.add_argument("items", nargs="*")
    plan.add_argument("--clear", action="store_true", help="Clear the plan")

    def run_tick(args: argparse.Namespace, out: TextIO) -> int:
        store().tick(args.item)
        return 0

    leaf("tick", "Mark a plan item done", run_tick).add_argument("item")

    _register_ref(leaves, refs)

    def run_tags(args: argparse.Namespace, out: TextIO) -> int:
        names = progress().tags()
        if args.json:
            _write_json(out, names)
        else:
            out.writelines(f"{name}\n" for name in names)
        return 0

    leaf("tags", "List the pipeline's git tags", run_tags).add_argument(
        "--json", action="store_true", help="Print JSON"
    )

    def run_usage_check(args: argparse.Namespace, out: TextIO) -> int:
        check = usage().check()
        if args.json:
            resets = None if check.resets_at is None else time_to_text(check.resets_at)
            _write_json(
                out,
                {
                    "verdict": check.verdict.value,
                    "reason": check.reason,
                    "resets_at": resets,
                },
            )
        else:
            out.write(f"{check.verdict.value}: {check.reason}\n")
        return 0

    leaf(
        "usage-check", "OK, PAUSE or UNKNOWN for plan usage", run_usage_check
    ).add_argument("--json", action="store_true", help="Print JSON")


def _register_ref(
    leaves: argparse._SubParsersAction[argparse.ArgumentParser],
    refs: Callable[[], Refs],
) -> None:
    """`status ref trunk|base|module <M>|tag <label>`."""
    ref = leaves.add_parser("ref", help="Print a branch or tag name")
    kinds = ref.add_subparsers(dest="ref_kind", required=True)

    def run_trunk(args: argparse.Namespace, out: TextIO) -> int:
        out.write(f"{refs().trunk()}\n")
        return 0

    kinds.add_parser("trunk", help="The trunk branch").set_defaults(run=run_trunk)

    def run_base(args: argparse.Namespace, out: TextIO) -> int:
        out.write(f"{refs().base()}\n")
        return 0

    kinds.add_parser("base", help="The branch modules merge into").set_defaults(
        run=run_base
    )

    def run_module(args: argparse.Namespace, out: TextIO) -> int:
        out.write(f"{refs().module_branch(args.module)}\n")
        return 0

    module = kinds.add_parser("module", help="A module's branch")
    module.add_argument("module")
    module.set_defaults(run=run_module)

    def run_tag(args: argparse.Namespace, out: TextIO) -> int:
        out.write(f"{refs().tag(args.label)}\n")
        return 0

    tag = kinds.add_parser("tag", help="A tag name")
    tag.add_argument("label")
    tag.set_defaults(run=run_tag)


def _write_json(out: TextIO, data: object) -> None:
    json.dump(data, out, indent=2)
    out.write("\n")
