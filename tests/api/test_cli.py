"""Tests for `bull.Modules.api.cli`."""

from __future__ import annotations

import argparse
import io
from pathlib import Path

import pytest

from bull.Modules.api.cli import register
from bull.Modules.api.Contracts import ApiCheck, ApprovalNeeded
from bull.Modules.api.mocks import MockApiSnapshots
from bull.Modules.foundation.Contracts import BullError
from bull.Modules.foundation.mocks import sample_layout

APP = sample_layout(Path("/tmp/apps/tally"))
DIFF = "--- stored\n+++ current\n@@ -1 +1 @@\n-pub old\n+pub new\n"
FAILING = ApiCheck(name="Counter", ok=False, stored=True, diff=DIFF)


class _UnchangedSnapshots(MockApiSnapshots):
    def write(
        self, app: object, module: str, approved: str | None = None
    ) -> Path | None:
        self.calls.append(("write", (app, module, approved)))
        return None

    def write_interface(
        self, app: object, name: str, approved: str | None = None
    ) -> Path | None:
        self.calls.append(("write_interface", (app, name, approved)))
        return None


class _RefusingSnapshots(MockApiSnapshots):
    def write(
        self, app: object, module: str, approved: str | None = None
    ) -> Path | None:
        raise ApprovalNeeded("the Counter contract changed", "approve it")


def _run(snapshots: MockApiSnapshots, argv: list[str]) -> tuple[int, str]:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command")
    register(commands, lambda: snapshots, lambda: APP)
    args = parser.parse_args(["api", *argv])
    out = io.StringIO()
    code = args.run(args, out)
    return code, out.getvalue()


def test_api_module_ok_prints_match_and_exits_zero() -> None:
    code, out = _run(MockApiSnapshots(), ["Counter"])
    assert code == 0
    assert "api: Counter matches its snapshot" in out


def test_api_module_checks_the_named_module_in_the_app() -> None:
    snapshots = MockApiSnapshots()
    _run(snapshots, ["Counter"])
    assert ("check", (APP, "Counter")) in snapshots.calls


def test_api_module_not_ok_prints_differs_and_diff_and_exits_one() -> None:
    snapshots = MockApiSnapshots()
    snapshots.result = FAILING
    code, out = _run(snapshots, ["Counter"])
    assert code == 1
    assert "api: Counter differs from its snapshot" in out
    assert DIFF in out


def test_api_module_without_snapshot_exits_one_with_the_hint() -> None:
    snapshots = MockApiSnapshots()
    snapshots.result = ApiCheck(
        "Counter", False, False, "no snapshot: run `bull api Counter --write`"
    )
    code, out = _run(snapshots, ["Counter"])
    assert code == 1
    assert "no snapshot: run `bull api Counter --write`" in out


def test_check_flag_ok_prints_nothing_and_exits_zero() -> None:
    assert _run(MockApiSnapshots(), ["Counter", "--check"]) == (0, "")


def test_check_flag_not_ok_prints_nothing_and_exits_one() -> None:
    snapshots = MockApiSnapshots()
    snapshots.result = FAILING
    assert _run(snapshots, ["Counter", "--check"]) == (1, "")


def test_write_prints_the_written_path_and_exits_zero() -> None:
    snapshots = MockApiSnapshots()
    code, out = _run(snapshots, ["Counter", "--write"])
    assert code == 0
    assert f"wrote {APP.api_dir / 'Counter.md'}" in out
    assert ("write", (APP, "Counter", None)) in snapshots.calls


def test_write_passes_the_approved_note() -> None:
    snapshots = MockApiSnapshots()
    _run(snapshots, ["Counter", "--write", "--approved", "adds a function"])
    assert ("write", (APP, "Counter", "adds a function")) in snapshots.calls


def test_write_when_unchanged_says_so_and_exits_zero() -> None:
    code, out = _run(_UnchangedSnapshots(), ["Counter", "--write"])
    assert code == 0
    assert "api: Counter unchanged" in out
    assert "wrote" not in out


def test_write_lets_approval_needed_propagate() -> None:
    with pytest.raises(ApprovalNeeded):
        _run(_RefusingSnapshots(), ["Counter", "--write"])


def test_approved_without_write_is_a_bull_error() -> None:
    with pytest.raises(BullError):
        _run(MockApiSnapshots(), ["Counter", "--approved", "note"])


def test_interface_ok_prints_match_and_exits_zero() -> None:
    snapshots = MockApiSnapshots()
    code, out = _run(snapshots, ["--interface", "Wire"])
    assert code == 0
    assert "api: Wire matches its snapshot" in out
    assert ("check_interface", (APP, "Wire")) in snapshots.calls


def test_interface_not_ok_prints_differs_and_exits_one() -> None:
    snapshots = MockApiSnapshots()
    snapshots.result = ApiCheck("Wire", False, True, DIFF)
    code, out = _run(snapshots, ["--interface", "Wire"])
    assert code == 1
    assert "api: Wire differs from its snapshot" in out
    assert DIFF in out


def test_interface_check_flag_is_quiet() -> None:
    snapshots = MockApiSnapshots()
    snapshots.result = ApiCheck("Wire", False, True, DIFF)
    assert _run(snapshots, ["--interface", "Wire", "--check"]) == (1, "")


def test_interface_write_prints_the_written_path() -> None:
    snapshots = MockApiSnapshots()
    code, out = _run(
        snapshots, ["--interface", "Wire", "--write", "--approved", "schema"]
    )
    assert code == 0
    assert f"wrote {APP.api_dir / 'interfaces' / 'Wire.md'}" in out
    assert ("write_interface", (APP, "Wire", "schema")) in snapshots.calls


def test_interface_write_when_unchanged_says_so() -> None:
    code, out = _run(_UnchangedSnapshots(), ["--interface", "Wire", "--write"])
    assert code == 0
    assert "api: Wire unchanged" in out


def test_module_and_interface_together_is_a_bull_error() -> None:
    with pytest.raises(BullError):
        _run(MockApiSnapshots(), ["Counter", "--interface", "Wire"])


def test_neither_module_nor_interface_is_a_bull_error() -> None:
    with pytest.raises(BullError):
        _run(MockApiSnapshots(), [])
