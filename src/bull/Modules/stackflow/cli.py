"""Stack repo commands: `bull status …` in a stack repo and `bull stack install`'s check.

Follows the module `cli.py` convention: collaborators arrive as zero-argument providers,
called only when a command runs; each leaf parser sets `run(args, out) -> int`; refusals are
raised (`BullError` and subclasses), never printed here.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

from bull.Modules.foundation.Contracts import BullError
from bull.Modules.stackflow.Contracts import StackRepoStatus, StackWorkflow
from bull.Modules.stackflow.install import check_static
from bull.Modules.stacks.Contracts import StackRegistry
from bull.Modules.stacktest.Contracts import StackTester

_DESIGN_TEMPLATE = Path(__file__).parent / "template" / "DESIGN.md"

_Run = Callable[[argparse.Namespace, TextIO], int]


def register_status(
    commands: argparse._SubParsersAction[argparse.ArgumentParser],
    workflow: Callable[[], StackWorkflow],
    root: Callable[[], Path],
) -> None:
    """Add a stack repo's `status [--json]`, `status next|stage|checkpoint|ref`.

    `workflow` and `root` (the stack repo's folder) are called only when a command runs.
    """
    status = commands.add_parser("status", help="the stack repo's workflow state")
    status.add_argument("--json", action="store_true", help="write JSON only")
    status.set_defaults(run=_show(workflow, root))
    actions = status.add_subparsers(dest="action")

    next_parser = actions.add_parser("next", help="what to do next")
    next_parser.set_defaults(run=_next(workflow, root))

    stage = actions.add_parser("stage", help="move to a stage (1 to 6)")
    stage.add_argument("stage", type=int)
    stage.set_defaults(run=_stage(workflow, root))

    checkpoint = actions.add_parser("checkpoint", help="record a checkpoint")
    checkpoint.add_argument("name")
    checkpoint.set_defaults(run=_checkpoint(workflow, root))

    ref = actions.add_parser(
        "ref", help="the branch or tag name for a stage or checkpoint"
    )
    ref.add_argument("kind", choices=("branch", "tag"))
    ref.add_argument("name")
    ref.set_defaults(run=_ref(workflow))


def before_install(
    tester: Callable[[], StackTester], registry: Callable[[], StackRegistry]
) -> Callable[[Path], None]:
    """The check `bull stack install` runs first: `check_static` on the folder.

    The providers are called only when the returned check runs; it raises `StackError`
    listing every problem when the static self-test fails.
    """

    def check(path: Path) -> None:
        check_static(tester(), registry(), path)

    return check


def design_template() -> str:
    """The stack repo's `DESIGN.md` template, for `bull template design`.

    Raises:
        BullError: the template file is missing from bull's installation.
    """
    try:
        return _DESIGN_TEMPLATE.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise BullError(
            "the stack template file DESIGN.md is missing from bull's installation",
            "reinstall bull",
        ) from error


# --- runners


def _show(workflow: Callable[[], StackWorkflow], root: Callable[[], Path]) -> _Run:
    def run(args: argparse.Namespace, out: TextIO) -> int:
        status = workflow().load(root())
        if args.json:
            out.write(json.dumps(_as_json(status), indent=2) + "\n")
        else:
            out.write(_render(status))
        return 0

    return run


def _next(workflow: Callable[[], StackWorkflow], root: Callable[[], Path]) -> _Run:
    def run(args: argparse.Namespace, out: TextIO) -> int:
        out.write(workflow().next_step(root()) + "\n")
        return 0

    return run


def _stage(workflow: Callable[[], StackWorkflow], root: Callable[[], Path]) -> _Run:
    def run(args: argparse.Namespace, out: TextIO) -> int:
        status = workflow().set_stage(root(), args.stage)
        out.write(f"stage: {_stage_text(status)}\n")
        return 0

    return run


def _checkpoint(
    workflow: Callable[[], StackWorkflow], root: Callable[[], Path]
) -> _Run:
    def run(args: argparse.Namespace, out: TextIO) -> int:
        status = workflow().checkpoint(root(), args.name)
        out.write(f"checkpoints: {_checkpoints_text(status)}\n")
        return 0

    return run


def _ref(workflow: Callable[[], StackWorkflow]) -> _Run:
    def run(args: argparse.Namespace, out: TextIO) -> int:
        out.write(workflow().ref(args.kind, args.name) + "\n")
        return 0

    return run


# --- formatting


def _stage_name(status: StackRepoStatus) -> str:
    return status.stage.name.lower().replace("_", "-")


def _stage_text(status: StackRepoStatus) -> str:
    return f"{int(status.stage)} ({_stage_name(status)})"


def _checkpoints_text(status: StackRepoStatus) -> str:
    return ", ".join(status.checkpoints) or "none"


def _render(status: StackRepoStatus) -> str:
    lines = [
        f"stack: {status.name}",
        f"stage: {_stage_text(status)}",
        f"checkpoints: {_checkpoints_text(status)}",
        f"static pass: {status.static_pass or 'none'}",
        f"test pass: {status.test_pass or 'none'}",
    ]
    return "".join(f"{line}\n" for line in lines)


def _as_json(status: StackRepoStatus) -> dict[str, object]:
    return {
        "format": status.format,
        "name": status.name,
        "stage": int(status.stage),
        "stage_name": _stage_name(status),
        "checkpoints": list(status.checkpoints),
        "static_pass": status.static_pass,
        "test_pass": status.test_pass,
    }
