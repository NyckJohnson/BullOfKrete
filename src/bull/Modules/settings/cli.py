"""`bull config show` and `bull config set`."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from typing import TextIO

from bull.Modules.settings.Contracts import Layer, Resolved, Settings, SettingValue


def register(
    commands: argparse._SubParsersAction[argparse.ArgumentParser],
    settings: Callable[[], Settings],
) -> None:
    """Add `config show` and `config set`; `settings` is called only when one runs."""
    config = commands.add_parser("config", help="Show or change settings")
    leaves = config.add_subparsers(dest="config_command", required=True)

    show = leaves.add_parser("show", help="Every setting, its value and its layer")
    show.add_argument("--part", help="Include this part's file and stack")
    show.add_argument("--json", action="store_true", help="Print JSON")

    def run_show(args: argparse.Namespace, out: TextIO) -> int:
        resolved = settings().show(args.part)
        if args.json:
            json.dump([_as_json(r) for r in resolved], out, indent=2)
            out.write("\n")
        else:
            out.writelines(_line(item) + "\n" for item in resolved)
        return 0

    show.set_defaults(run=run_show)

    set_ = leaves.add_parser("set", help="Set a value in the app, user or part file")
    set_.add_argument("key")
    set_.add_argument("value")
    where = set_.add_mutually_exclusive_group()
    where.add_argument("--user", action="store_true", help="Write the user file")
    where.add_argument("--part", help="Write this part's file")

    def run_set(args: argparse.Namespace, out: TextIO) -> int:
        if args.user:
            layer = Layer.USER
        elif args.part is not None:
            layer = Layer.PART
        else:
            layer = Layer.APP
        resolved = settings().set(args.key, args.value, layer, args.part)
        out.write(_line(resolved) + "\n")
        return 0

    set_.set_defaults(run=run_set)


def _text(value: SettingValue) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, tuple):
        return ", ".join(value)
    return str(value)


def _line(resolved: Resolved) -> str:
    return f"{resolved.key} = {_text(resolved.value)} ({resolved.layer.value})"


def _as_json(resolved: Resolved) -> dict[str, object]:
    value = resolved.value
    return {
        "key": resolved.key,
        "value": list(value) if isinstance(value, tuple) else value,
        "layer": resolved.layer.value,
        "source": str(resolved.source) if resolved.source is not None else None,
    }
