"""`bull part add|list|check`."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from typing import TextIO

from bull.Modules.foundation.Contracts import AppLayout
from bull.Modules.parts.Contracts import Parts


def register(
    commands: argparse._SubParsersAction[argparse.ArgumentParser],
    parts: Callable[[], Parts],
    app: Callable[[], AppLayout],
) -> None:
    """Add `part add`, `part list` and `part check`; providers are called only when one runs."""
    part = commands.add_parser("part", help="Add, list or check the app's parts")
    leaves = part.add_subparsers(dest="part_command", required=True)

    add = leaves.add_parser("add", help="Add a part: a folder with its own stack")
    add.add_argument("name")
    add.add_argument("stack")
    add.add_argument("--dir", help="The part's folder (default: its name)")

    def run_add(args: argparse.Namespace, out: TextIO) -> int:
        added = parts().add(app(), args.name, args.stack, args.dir)
        out.write(f"added part {added.name} ({added.stack}) in {added.dir}\n")
        return 0

    add.set_defaults(run=run_add)

    list_ = leaves.add_parser("list", help="Every part: name, stack and folder")
    list_.add_argument("--json", action="store_true", help="Print JSON")

    def run_list(args: argparse.Namespace, out: TextIO) -> int:
        found = parts().all(app())
        if args.json:
            rows = [{"name": p.name, "stack": p.stack, "dir": p.dir} for p in found]
            json.dump(rows, out, indent=2)
            out.write("\n")
        else:
            out.writelines(f"{p.name}  {p.stack}  {p.dir}\n" for p in found)
        return 0

    list_.set_defaults(run=run_list)

    check = leaves.add_parser(
        "check", help="Report overlapping, unknown or missing parts"
    )

    def run_check(args: argparse.Namespace, out: TextIO) -> int:
        problems = parts().check(app())
        out.writelines(f"{problem}\n" for problem in problems)
        return 1 if problems else 0

    check.set_defaults(run=run_check)
