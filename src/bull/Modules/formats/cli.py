"""`bull migrate`."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from typing import TextIO

from bull.Modules.formats.Contracts import Formats
from bull.Modules.foundation.Contracts import AppLayout


def register(
    commands: argparse._SubParsersAction[argparse.ArgumentParser],
    formats: Callable[[], Formats],
    app: Callable[[], AppLayout],
) -> None:
    """Add `migrate`; `formats` and `app` are called only when it runs."""
    migrate = commands.add_parser(
        "migrate", help="Upgrade the app's files to the current format"
    )

    def run_migrate(args: argparse.Namespace, out: TextIO) -> int:
        current = formats()
        changed = current.migrate(app())
        if not changed:
            out.write(f"already format {current.current()}\n")
        else:
            out.writelines(f"migrated {path}\n" for path in changed)
        return 0

    migrate.set_defaults(run=run_migrate)
