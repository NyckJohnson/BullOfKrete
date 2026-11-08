"""`bull template <name>`."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from typing import TextIO

from bull.Modules.memo.Contracts import Templates


def register(
    commands: argparse._SubParsersAction[argparse.ArgumentParser],
    templates: Callable[[], Templates],
) -> None:
    """Add `template <name>`; `templates` is called only when the command runs."""
    template = commands.add_parser("template", help="Print a template")
    # No `choices`: other modules may provide more template names.
    template.add_argument("name", help="The template's name, e.g. outline or backlog")

    def run(args: argparse.Namespace, out: TextIO) -> int:
        out.write(templates().text(args.name))
        return 0

    template.set_defaults(run=run)
