"""`bull api …` commands."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from typing import TextIO

from bull.Modules.api.Contracts import ApiSnapshots
from bull.Modules.foundation.Contracts import AppLayout, BullError


def register(
    commands: argparse._SubParsersAction[argparse.ArgumentParser],
    snapshots: Callable[[], ApiSnapshots],
    app: Callable[[], AppLayout],
) -> None:
    """Add `bull api <M>` and `bull api --interface <Name>`; providers are called only when it runs."""
    api = commands.add_parser("api", help="Check or write contract snapshots")
    api.add_argument("module", nargs="?", help="The module whose contract to check")
    api.add_argument("--interface", metavar="NAME", help="An interface from the memo")
    api.add_argument(
        "--check", action="store_true", help="Print nothing; exit 1 when not ok"
    )
    api.add_argument(
        "--write", action="store_true", help="Write the snapshot (approval rules apply)"
    )
    api.add_argument("--approved", metavar="NOTE", help="The human's approval note")

    def run(args: argparse.Namespace, out: TextIO) -> int:
        if (args.module is None) == (args.interface is None):
            raise BullError(
                "give exactly one of a module or --interface <Name>",
                "e.g. `bull api Counter` or `bull api --interface Wire`",
            )
        if args.approved is not None and not args.write:
            raise BullError("--approved needs --write", "add --write")
        if args.check and args.write:
            raise BullError("--check and --write can't be used together")
        name: str = args.module if args.module is not None else args.interface
        is_interface = args.interface is not None
        layout = app()
        api_snapshots = snapshots()
        if args.write:
            written = (
                api_snapshots.write_interface(layout, name, args.approved)
                if is_interface
                else api_snapshots.write(layout, name, args.approved)
            )
            if written is None:
                out.write(f"api: {name} unchanged\n")
            else:
                out.write(f"wrote {written}\n")
            return 0
        check = (
            api_snapshots.check_interface(layout, name)
            if is_interface
            else api_snapshots.check(layout, name)
        )
        if args.check:
            return 0 if check.ok else 1
        if check.ok:
            out.write(f"api: {name} matches its snapshot\n")
            return 0
        out.write(f"api: {name} differs from its snapshot\n")
        out.write(check.diff if check.diff.endswith("\n") else check.diff + "\n")
        return 1

    api.set_defaults(run=run)
