"""`bull feature …` commands.

Thin wiring over `Backlog`, `IdeaReader` and `FeatureCycle`: each provider is called only
when a command that needs it runs, and refusals (`BullError`s) are raised for `cli.main`
to report, never printed here.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TextIO

from bull.Modules.features.backlog import new_ideas
from bull.Modules.features.Contracts import (
    Backlog,
    BacklogItem,
    FeatureCycle,
    FeaturePlan,
    Idea,
    IdeaReader,
    ItemState,
)
from bull.Modules.foundation.Contracts import BullError

_Run = Callable[[argparse.Namespace, TextIO], int]


def register(
    commands: argparse._SubParsersAction[argparse.ArgumentParser],
    backlog: Callable[[], Backlog],
    ideas: Callable[[], IdeaReader],
    cycle: Callable[[], FeatureCycle],
) -> None:
    """Add `feature` and its subcommands; providers are called only when one runs."""
    feature = commands.add_parser("feature", help="Backlog and feature cycle")
    leaves = feature.add_subparsers(dest="feature_command", required=True)

    def leaf(name: str, help_: str, run: _Run) -> argparse.ArgumentParser:
        parser = leaves.add_parser(name, help=help_)
        parser.set_defaults(run=run)
        return parser

    def run_add(args: argparse.Namespace, out: TextIO) -> int:
        title, sep, description = args.text.partition(":")
        item = backlog().add(Idea(title.strip(), description.strip()), args.top)
        out.write(f"Added {item.slug}: {item.title}\n")
        return 0

    add = leaf("add", "Queue an idea", run_add)
    add.add_argument("text", help='"<Title>: <description>"')
    add.add_argument("--top", action="store_true", help="Put it first in the queue")

    def run_import(args: argparse.Namespace, out: TextIO) -> int:
        found = ideas().read(_read_ideas_file(Path(args.file)), args.section)
        if args.dry_run:
            new = new_ideas(found, backlog().items(), ideas())
            out.write(f"Would add {len(new)} idea(s):\n")
            out.writelines(f"  {idea.title}\n" for idea in new)
            return 0
        added = backlog().import_ideas(found)
        out.write(f"Added {len(added)} idea(s):\n")
        out.writelines(f"  {item.slug}: {item.title}\n" for item in added)
        return 0

    imp = leaf("import", "Queue the ideas in a Markdown file", run_import)
    imp.add_argument("file")
    imp.add_argument("--section", help="Only the list under this `##` heading")
    imp.add_argument(
        "--dry-run", action="store_true", help="List the new ideas without adding them"
    )

    def run_list(args: argparse.Namespace, out: TextIO) -> int:
        items = backlog().items()
        positions = _queued_positions(items)
        if args.json:
            data = [
                {
                    "position": positions.get(i.slug),
                    "slug": i.slug,
                    "state": i.state.value,
                    "title": i.title,
                }
                for i in items
            ]
            json.dump(data, out, indent=2)
            out.write("\n")
        else:
            out.writelines(
                f"{positions.get(i.slug, '-')!s:>3}  {i.slug}  {i.state.value}  {i.title}\n"
                for i in items
            )
        return 0

    leaf("list", "Show the backlog", run_list).add_argument(
        "--json", action="store_true", help="Print JSON"
    )

    def run_move(args: argparse.Namespace, out: TextIO) -> int:
        backlog().move(args.slug, args.position)
        out.write(f"Moved {args.slug} to {args.position}\n")
        return 0

    move = leaf("move", "Move a queued idea", run_move)
    move.add_argument("slug")
    move.add_argument("position", type=int, help="1-based, among queued ideas")

    def run_drop(args: argparse.Namespace, out: TextIO) -> int:
        backlog().drop(args.slug)
        out.write(f"Dropped {args.slug}\n")
        return 0

    leaf("drop", "Drop a queued idea", run_drop).add_argument("slug")

    def run_start(args: argparse.Namespace, out: TextIO) -> int:
        item = cycle().start(args.slug)
        out.write(f"Started {item.slug}\n")
        return 0

    leaf("start", "Start a queued feature", run_start).add_argument(
        "slug", nargs="?", default=None
    )

    def run_plan(args: argparse.Namespace, out: TextIO) -> int:
        out.write(_plan_text(cycle().plan()))
        return 0

    leaf("plan", "Reopen and add modules from the memo", run_plan)

    def run_accept(args: argparse.Namespace, out: TextIO) -> int:
        out.write(f"Accepted {cycle().accept().slug}\n")
        return 0

    leaf("accept", "Accept the active feature", run_accept)

    def run_abandon(args: argparse.Namespace, out: TextIO) -> int:
        out.write(f"Abandoned {cycle().abandon().slug}\n")
        return 0

    leaf("abandon", "Abandon the active feature", run_abandon)


def _read_ideas_file(path: Path) -> str:
    """The file's text; raises `BullError` when it can't be read."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as e:
        raise BullError(f"{path}: no such file.", "Check the path.") from e
    except (OSError, UnicodeDecodeError) as e:
        raise BullError(f"{path}: can't read it: {e}", "Check the file.") from e


def _queued_positions(items: Sequence[BacklogItem]) -> dict[str, int]:
    """Each queued item's 1-based position among queued items (what `move` takes)."""
    queued = (i for i in items if i.state is ItemState.QUEUED)
    return {i.slug: n for n, i in enumerate(queued, start=1)}


def _plan_text(plan: FeaturePlan) -> str:
    lines: list[str] = []
    for name, units in plan.reopened.items():
        numbers = ", ".join(str(n) for n in units)
        lines.append(f"Reopened {name}: unit {numbers}")
    if plan.new_modules:
        lines.append(f"New modules: {', '.join(plan.new_modules)}")
    if plan.contract_changes:
        lines.append(f"Contract changes: {', '.join(plan.contract_changes)}")
    if not lines:
        lines.append("Nothing to reopen or add.")
    lines.append(f"Skeleton needed: {'yes' if plan.skeleton_needed else 'no'}")
    return "".join(f"{line}\n" for line in lines)
