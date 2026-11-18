"""The `fixture_cli` console script: parses the command and calls the counter."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from fixture_cli.Modules.counter.counter import FileCounter


def main(argv: Sequence[str] | None = None) -> int:
    """Run `fixture_cli count`: bump the count in the working folder and print it."""
    parser = argparse.ArgumentParser(prog="fixture_cli")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("count", help="add one to the count and print it")
    parser.parse_args(argv)
    print(FileCounter(Path.cwd()).increment())
    return 0
