"""Tests for `bull.Modules.formats.cli` (`bull migrate`).

Shapes chosen here (for the code-writer):
  - `register(commands, formats, app)`; `formats: Callable[[], Formats]` and
    `app: Callable[[], AppLayout]` are zero-argument providers, called only when
    `migrate` runs.
  - `migrate` calls `formats().migrate(app())`, exit code 0.
  - nothing migrated: prints one line, "already format C" (C = `formats().current()`).
  - otherwise prints one line per migrated path (each containing the path's file name)
    and not "already format".
  - errors (FormatTooNew, BullError) propagate out of `run`; nothing is written.
"""

from __future__ import annotations

import argparse
import io
from pathlib import Path

import pytest

from bull.Modules.formats.cli import register
from bull.Modules.formats.Contracts import Formats, FormatTooNew
from bull.Modules.formats.mocks import MockFormats
from bull.Modules.foundation.Contracts import AppLayout, BullError
from bull.Modules.foundation.mocks import sample_layout

APP = sample_layout(Path("/tmp/apps/tally"))


def build(
    formats: Formats,
) -> tuple[argparse.ArgumentParser, list[str]]:
    parser = argparse.ArgumentParser(prog="bull")
    commands = parser.add_subparsers(dest="command")
    provided: list[str] = []

    def formats_provider() -> Formats:
        provided.append("formats")
        return formats

    def app_provider() -> AppLayout:
        provided.append("app")
        return APP

    register(commands, formats_provider, app_provider)
    return parser, provided


def run(formats: Formats, *argv: str) -> tuple[int, str]:
    parser, _ = build(formats)
    args = parser.parse_args(argv)
    out = io.StringIO()
    code = args.run(args, out)
    return code, out.getvalue()


def test_register_does_not_call_the_providers() -> None:
    parser, provided = build(MockFormats())
    parser.parse_args(["migrate"])
    assert provided == []


def test_migrate_says_already_current_when_nothing_changed() -> None:
    code, text = run(MockFormats(), "migrate")
    assert code == 0
    assert text.strip() == "already format 1"


def test_migrate_already_message_uses_the_current_format() -> None:
    _, text = run(MockFormats(current=3), "migrate")
    assert text.strip() == "already format 3"


def test_migrate_calls_formats_migrate_with_the_app() -> None:
    mock = MockFormats()
    run(mock, "migrate")
    assert ("migrate", (APP,)) in mock.calls


def test_migrate_prints_each_migrated_path() -> None:
    mock = MockFormats()
    mock.found = 0
    mock.migrated = [APP.status_file, APP.config_file]
    code, text = run(mock, "migrate")
    assert code == 0
    lines = text.splitlines()
    assert len(lines) == 2
    assert "status.json" in lines[0]
    assert "config.toml" in lines[1]
    assert "already format" not in text


def test_migrate_raises_format_too_new_without_printing() -> None:
    mock = MockFormats()
    mock.found = 2
    parser, _ = build(mock)
    args = parser.parse_args(["migrate"])
    out = io.StringIO()
    with pytest.raises(FormatTooNew):
        args.run(args, out)
    assert out.getvalue() == ""


def test_migrate_propagates_bull_errors() -> None:
    class Failing(MockFormats):
        def migrate(self, app: AppLayout) -> list[Path]:
            raise BullError("no migration from format 1")

    parser, _ = build(Failing())
    args = parser.parse_args(["migrate"])
    out = io.StringIO()
    with pytest.raises(BullError, match="no migration from format 1"):
        args.run(args, out)
    assert out.getvalue() == ""
