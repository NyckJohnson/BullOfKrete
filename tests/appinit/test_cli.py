"""Tests for `bull.Modules.appinit.cli` (the 2026-11-08 `register(commands, <providers>)` convention).

Providers assumed (keyword): `app_init`, `doctor` (zero-argument, typed by protocol) and
`stack_init` (zero-argument provider of a `Callable[[Path], InitResult]`, i.e. the live
`LiveAppInit.init_stack`).
"""

from __future__ import annotations

import argparse
import io
import json
import os
import shlex
from pathlib import Path

import pytest

from bull.Modules.appinit.cli import register
from bull.Modules.appinit.Contracts import DoctorReport, InitResult
from bull.Modules.appinit.mocks import MockAppInit, MockDoctor
from bull.Modules.foundation.Contracts import BullError
from bull.Modules.stacks.Contracts import CheckItem


class Harness:
    def __init__(self) -> None:
        self.app_init = MockAppInit()
        self.doctor = MockDoctor()
        self.stack_calls: list[Path] = []
        self.parser = argparse.ArgumentParser(prog="bull")
        commands = self.parser.add_subparsers(dest="command")
        register(
            commands,
            app_init=lambda: self.app_init,
            doctor=lambda: self.doctor,
            stack_init=lambda: self._stack_init,
        )

    def _stack_init(self, path: Path) -> InitResult:
        self.stack_calls.append(path)
        return InitResult(path, created=True, relinked=False, adopting=False)

    def run(self, *argv: str) -> tuple[int, str]:
        args = self.parser.parse_args(list(argv))
        out = io.StringIO()
        code = args.run(args, out)
        return code, out.getvalue()


@pytest.fixture
def h() -> Harness:
    return Harness()


# --- init ------------------------------------------------------------------------------


def test_init_calls_app_init_with_the_path_and_no_adopt(
    h: Harness, tmp_path: Path
) -> None:
    code, _ = h.run("init", str(tmp_path))
    assert code == 0
    assert h.app_init.calls == [("init", (tmp_path, False))]


def test_init_prints_the_app_root(h: Harness, tmp_path: Path) -> None:
    _, out = h.run("init", str(tmp_path))
    assert str(tmp_path) in out


def test_init_adopt_passes_adopt_true(h: Harness, tmp_path: Path) -> None:
    code, _ = h.run("init", str(tmp_path), "--adopt")
    assert code == 0
    assert h.app_init.calls == [("init", (tmp_path, True))]


def test_init_defaults_to_the_current_folder(
    h: Harness, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    h.run("init")
    ((_, (path, adopt)),) = h.app_init.calls
    assert isinstance(path, Path)
    assert path.resolve() == tmp_path.resolve()
    assert adopt is False


def test_init_stack_uses_the_stack_initializer_not_app_init(
    h: Harness, tmp_path: Path
) -> None:
    code, out = h.run("init", str(tmp_path / "go_cli"), "--stack")
    assert code == 0
    assert h.stack_calls == [tmp_path / "go_cli"]
    assert h.app_init.calls == []
    assert str(tmp_path / "go_cli") in out


def test_init_lets_a_bull_error_propagate(h: Harness, tmp_path: Path) -> None:
    class Refusing(MockAppInit):
        def init(self, path: Path, adopt: bool = False) -> InitResult:
            raise BullError("not empty", "use --adopt")

    h.app_init = Refusing()
    with pytest.raises(BullError):
        h.run("init", str(tmp_path))


# --- open ------------------------------------------------------------------------------


def test_open_print_command_prints_the_argv_and_does_not_exec(
    h: Harness, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    execs: list[object] = []
    monkeypatch.setattr(os, "execvp", lambda *a: execs.append(a))
    code, out = h.run("open", str(tmp_path), "--print-command")
    assert code == 0
    assert shlex.split(out) == [
        "claude",
        "--plugin-dir",
        str(tmp_path / ".bull" / "plugin"),
    ]
    assert execs == []


def test_open_passes_the_path_and_claude_args_after_double_dash(
    h: Harness, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(os, "execvp", lambda *a: None)
    h.run("open", str(tmp_path), "--print-command", "--", "--resume", "x")
    assert h.app_init.calls == [("open_argv", (tmp_path, ("--resume", "x")))]


def test_open_print_command_includes_the_extra_args(h: Harness, tmp_path: Path) -> None:
    _, out = h.run("open", str(tmp_path), "--print-command", "--", "--resume", "x")
    assert shlex.split(out)[-2:] == ["--resume", "x"]


def test_open_without_extra_args_passes_an_empty_list(
    h: Harness, tmp_path: Path
) -> None:
    h.run("open", str(tmp_path), "--print-command")
    assert h.app_init.calls == [("open_argv", (tmp_path, ()))]


def test_open_replaces_the_process_with_the_argv(
    h: Harness, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    execs: list[tuple[object, ...]] = []
    monkeypatch.setattr(os, "execvp", lambda *a: execs.append(a))
    _, out = h.run("open", str(tmp_path), "--", "--resume", "x")
    argv = [
        "claude",
        "--plugin-dir",
        str(tmp_path / ".bull" / "plugin"),
        "--resume",
        "x",
    ]
    assert execs == [("claude", argv)]
    assert out == ""


def test_open_lets_a_bull_error_propagate_without_exec(
    h: Harness, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Refusing(MockAppInit):
        def open_argv(self, path: Path, extra: object) -> list[str]:
            raise BullError("not a bull app", "run bull init")

    execs: list[object] = []
    monkeypatch.setattr(os, "execvp", lambda *a: execs.append(a))
    h.app_init = Refusing()
    with pytest.raises(BullError):
        h.run("open", str(tmp_path))
    assert execs == []


# --- doctor ----------------------------------------------------------------------------


def test_doctor_ok_exits_zero_and_prints_the_items(h: Harness) -> None:
    code, out = h.run("doctor")
    assert code == 0
    assert "python 3.12.4" in out
    assert "git 2.47.0" in out
    assert h.doctor.calls == [("run", ())]


def test_doctor_not_ok_exits_one_and_prints_each_fix(h: Harness) -> None:
    h.doctor.report = DoctorReport(
        items=(
            CheckItem(True, "python 3.12.4", ""),
            CheckItem(False, "uv not found", "install uv: https://docs.astral.sh/uv/"),
            CheckItem(False, "git not found", "install git: https://git-scm.com/"),
        ),
        stacks=(),
    )
    code, out = h.run("doctor")
    assert code == 1
    assert "install uv: https://docs.astral.sh/uv/" in out
    assert "install git: https://git-scm.com/" in out


def test_doctor_with_only_stack_tools_missing_still_exits_zero(h: Harness) -> None:
    code, out = h.run("doctor")
    assert h.doctor.report.stacks[1][1][0].ok is False
    assert code == 0
    assert "go_cli" in out


def test_doctor_json_writes_only_json_with_ok_items_and_stacks(h: Harness) -> None:
    code, out = h.run("doctor", "--json")
    data = json.loads(out)
    assert code == 0
    assert data["ok"] is True
    assert {"item": "uv 0.13.1", "ok": True, "fix": ""} in data["items"]
    assert [s["name"] for s in data["stacks"]] == ["python_cli", "go_cli"]
    go = data["stacks"][1]["items"][0]
    assert go == {"item": "go", "ok": False, "fix": "install Go: https://go.dev/dl/"}


def test_doctor_json_exits_one_when_not_ok(h: Harness) -> None:
    h.doctor.report = DoctorReport(
        items=(CheckItem(False, "git not found", "install git"),), stacks=()
    )
    code, out = h.run("doctor", "--json")
    assert code == 1
    assert json.loads(out)["ok"] is False


# --- open: argument splitting ----------------------------------------------------------


@pytest.mark.parametrize("extra", [("-p", "hi"), ("--model", "x")])
def test_open_without_a_path_sends_args_after_double_dash_to_claude(
    h: Harness, extra: tuple[str, ...]
) -> None:
    _, out = h.run("open", "--print-command", "--", *extra)
    assert h.app_init.calls == [("open_argv", (Path("."), extra))]
    assert shlex.split(out)[-len(extra) :] == list(extra)


def test_open_with_a_path_does_not_pass_the_double_dash_on(
    h: Harness,
) -> None:
    h.run("open", "app", "--print-command", "--", "hi")
    assert h.app_init.calls == [("open_argv", (Path("app"), ("hi",)))]


def test_open_without_a_path_reads_a_doubled_double_dash_as_one_separator(
    h: Harness,
) -> None:
    h.run("open", "--print-command", "--", "--", "x")
    assert h.app_init.calls == [("open_argv", (Path("."), ("x",)))]


def test_open_with_a_path_reads_a_doubled_double_dash_as_one_separator(
    h: Harness,
) -> None:
    h.run("open", "app", "--print-command", "--", "--", "x")
    assert h.app_init.calls == [("open_argv", (Path("app"), ("x",)))]


# --- init: relinked message ------------------------------------------------------------


def test_init_on_an_existing_app_prints_the_relinked_message(
    h: Harness, tmp_path: Path
) -> None:
    class Relinking(MockAppInit):
        def init(self, path: Path, adopt: bool = False) -> InitResult:
            return InitResult(path, created=False, relinked=True, adopting=False)

    h.app_init = Relinking()
    code, out = h.run("init", str(tmp_path))
    assert code == 0
    assert f"relinked the bull app at {tmp_path}" in out
