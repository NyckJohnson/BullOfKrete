"""`bull stacks` and `bull stack select|rules|setup|check|run|install`."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

from bull.Modules.foundation.Contracts import AppLayout
from bull.Modules.settings.Contracts import Settings
from bull.Modules.stacks.Contracts import (
    CheckItem,
    Stack,
    StackError,
    StackOps,
    StackRegistry,
)
from bull.Modules.stacks.select import part_names


def register(
    commands: argparse._SubParsersAction[argparse.ArgumentParser],
    registry: Callable[[], StackRegistry],
    ops: Callable[[], StackOps],
    app: Callable[[], AppLayout],
    settings: Callable[[], Settings],
    before_install: Callable[[Path], None] | None = None,
) -> None:
    """Add `stacks` and `stack <leaf>`; the providers are called only when a command runs.

    `before_install` is called with the folder before the registry installs it; an exception
    from it stops the install.
    """
    stacks = commands.add_parser("stacks", help="List the stacks bull knows")
    stacks.add_argument("--all", action="store_true", help="Include test stacks")
    stacks.add_argument("--json", action="store_true", help="Print JSON")

    def run_stacks(args: argparse.Namespace, out: TextIO) -> int:
        found = registry().all(args.all)
        if args.json:
            json.dump([_stack_json(s) for s in found], out, indent=2)
            out.write("\n")
        else:
            out.writelines(_stack_line(s) + "\n" for s in found)
        return 0

    stacks.set_defaults(run=run_stacks)

    stack = commands.add_parser(
        "stack", help="The app's stack: select, rules, setup, …"
    )
    leaves = stack.add_subparsers(dest="stack_command", required=True)

    def known_part(part: str | None) -> str | None:
        """`part` unchanged if the app has it (`app` when there are no part files)."""
        if part is not None:
            known = part_names(app()) or ["app"]
            if part not in known:
                raise StackError(
                    f"this app has no part `{part}`; its parts: " + ", ".join(known),
                    "pass `--part` with one of: " + ", ".join(known),
                )
        return part

    def part_stack(part: str | None) -> Stack:
        """The stack of `part`; with parts present, a part must be named."""
        known_part(part)
        if part is None:
            names = part_names(app())
            if names:
                raise StackError(
                    "this app has parts; say which part: " + ", ".join(names),
                    "pass `--part <name>`",
                )
        name = settings().get("stack", part)
        if not isinstance(name, str) or not name:
            where = "this app" if part is None else f"part `{part}`"
            raise StackError(
                f"no stack set for {where}",
                "run `bull stack select <name>`"
                if part is None
                else "run `bull stack select <name>`, or set the part's `stack`",
            )
        return registry().get(name)

    select = leaves.add_parser("select", help="Set the one-part app's stack")
    select.add_argument("name")

    def run_select(args: argparse.Namespace, out: TextIO) -> int:
        ops().select(app(), args.name)
        out.write(f"stack set to {args.name}\n")
        return 0

    select.set_defaults(run=run_select)

    rules = leaves.add_parser("rules", help="The stack's rules for an agent")
    rules.add_argument("agent")
    rules.add_argument("--part", help="Use this part's stack")

    def run_rules(args: argparse.Namespace, out: TextIO) -> int:
        _write_text(out, ops().rules(part_stack(args.part), args.agent))
        return 0

    rules.set_defaults(run=run_rules)

    setup = leaves.add_parser("setup", help="The stack's manual setup steps")
    setup.add_argument("--section", help="Only this `## ` section")
    setup.add_argument("--part", help="Use this part's stack")

    def run_setup(args: argparse.Namespace, out: TextIO) -> int:
        _write_text(out, ops().setup_guide(part_stack(args.part), args.section))
        return 0

    setup.set_defaults(run=run_setup)

    check = leaves.add_parser("check", help="Check the toolchain and project setup")
    check.add_argument("--part", help="Check this part")
    check.add_argument("--json", action="store_true", help="Print JSON")

    def run_check(args: argparse.Namespace, out: TextIO) -> int:
        part = known_part(args.part)
        names = part_names(app()) if part is None else []
        if names:
            return check_every_part(names, args.json, out)
        items = ops().check(app(), part)
        if args.json:
            json.dump([_check_json(i) for i in items], out, indent=2)
            out.write("\n")
        else:
            out.writelines(_check_line(i) + "\n" for i in items)
        return 0 if all(i.ok for i in items) else 1

    def check_every_part(names: list[str], as_json: bool, out: TextIO) -> int:
        """Check each part in turn (sorted), even after one fails; exit 1 if any failed."""
        results: list[tuple[str, str, list[CheckItem]]] = []
        for name in names:
            results.append(
                (name, _part_stack_name(settings(), name), ops().check(app(), name))
            )
        if as_json:
            json.dump(
                [
                    {"part": n, "stack": st, "items": [_check_json(i) for i in items]}
                    for n, st, items in results
                ],
                out,
                indent=2,
            )
            out.write("\n")
        else:
            for n, st, items in results:
                out.write(f"part {n} ({st})\n")
                out.writelines(_check_line(i) + "\n" for i in items)
        return 0 if all(i.ok for _, _, items in results for i in items) else 1

    check.set_defaults(run=run_check)

    run = leaves.add_parser("run", help="Run one of the stack's extra commands")
    run.add_argument("name", metavar="command")
    run.add_argument("--part", help="Run it for this part")

    def run_run(args: argparse.Namespace, out: TextIO) -> int:
        return ops().run_command(app(), args.name, known_part(args.part))

    run.set_defaults(run=run_run)

    install = leaves.add_parser("install", help="Install a stack folder for this user")
    install.add_argument("path", type=Path)

    def run_install(args: argparse.Namespace, out: TextIO) -> int:
        path: Path = args.path
        if before_install is not None:
            before_install(path)
        installed = registry().install(path)
        out.write(f"installed {installed.manifest.name}\n")
        return 0

    install.set_defaults(run=run_install)


def _part_stack_name(settings: Settings, part: str) -> str:
    """The part's `stack` setting for a check heading; `no stack set` when it is missing."""
    name = settings.get("stack", part)
    return name if isinstance(name, str) and name else "no stack set"


def _write_text(out: TextIO, text: str) -> None:
    out.write(text if text.endswith("\n") else text + "\n")


def _stack_line(stack: Stack) -> str:
    m = stack.manifest
    line = f"{m.name:<16} {m.kind.value:<8} {m.maturity.value:<13} {m.title}"
    return line if stack.builtin else f"{line}  (installed)"


def _stack_json(stack: Stack) -> dict[str, object]:
    m = stack.manifest
    return {
        "name": m.name,
        "kind": m.kind.value,
        "maturity": m.maturity.value,
        "title": m.title,
        "installed": not stack.builtin,
    }


def _check_line(item: CheckItem) -> str:
    if item.ok:
        return f"✓ {item.item}"
    return f"✗ {item.item} — {item.fix}" if item.fix else f"✗ {item.item}"


def _check_json(item: CheckItem) -> dict[str, object]:
    return {"ok": item.ok, "item": item.item, "fix": item.fix}
