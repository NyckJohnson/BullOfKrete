"""Tests for `bull.Modules.stacktest.cli` (`bull stack test`).

Assumed shape (not fixed by the memo): `register(stack_leaves, tester, registry)` adds `test`
to the `stack` command's subcommands (owned by stacks.cli, as adoption's `register_detect`
does), both collaborators as zero-argument providers.
"""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

import pytest

from bull.Modules.stacks.Contracts import StackError
from bull.Modules.stacks.mocks import MockStackRegistry
from bull.Modules.stacktest import cli
from bull.Modules.stacktest.Contracts import CaseResult, CaseVerdict, StackTestReport
from bull.Modules.stacktest.mocks import MockStackTester


def _run(
    tester: MockStackTester,
    registry: MockStackRegistry,
    argv: list[str],
) -> tuple[int, str]:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command")
    stack = commands.add_parser("stack")
    leaves = stack.add_subparsers(dest="stack_command")
    cli.register(leaves, lambda: tester, lambda: registry)
    args = parser.parse_args(["stack", "test", *argv])
    out = io.StringIO()
    code = args.run(args, out)
    return code, out.getvalue()


def _failing(name: str = "fixture", static: bool = False) -> StackTestReport:
    return StackTestReport(
        name,
        static,
        ("rules.md missing",) if static else (),
        ()
        if static
        else (
            CaseResult("clean", CaseVerdict.PASS, "pass", "pass"),
            CaseResult("fast", CaseVerdict.FAIL, "pass", "fail"),
        ),
    )


@pytest.fixture(autouse=True)
def _cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_providers_are_not_called_while_registering() -> None:
    def boom() -> object:
        raise AssertionError("called while registering")

    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command")
    leaves = commands.add_parser("stack").add_subparsers(dest="stack_command")
    cli.register(leaves, boom, boom)  # type: ignore[arg-type]
    parser.parse_args(["stack", "test", "fixture"])


def test_a_name_loads_the_stack_through_get_and_runs_the_cases() -> None:
    tester, registry = MockStackTester(), MockStackRegistry()
    code, out = _run(tester, registry, ["fixture"])
    assert code == 0
    assert ("get", ("fixture",)) in registry.calls
    assert not [c for c in registry.calls if c[0] == "load_path"]
    run = [c for c in tester.calls if c[0] == "run"]
    assert len(run) == 1
    assert run[0][1][0] is registry.stacks["fixture"]
    assert run[0][1][1] is None
    assert out


def test_a_path_loads_the_stack_through_load_path(tmp_path: Path) -> None:
    folder = tmp_path / "mystack"
    folder.mkdir()
    tester, registry = MockStackTester(), MockStackRegistry()
    code, _ = _run(tester, registry, [str(folder)])
    assert code == 0
    assert ("load_path", (folder,)) in registry.calls
    assert not [c for c in registry.calls if c[0] == "get"]
    assert [c for c in tester.calls if c[0] == "run"]


def test_a_relative_path_with_a_separator_loads_through_load_path(
    tmp_path: Path,
) -> None:
    (tmp_path / "stacks" / "mystack").mkdir(parents=True)
    tester, registry = MockStackTester(), MockStackRegistry()
    _run(tester, registry, ["stacks/mystack"])
    assert [c for c in registry.calls if c[0] == "load_path"]
    assert not [c for c in registry.calls if c[0] == "get"]


def test_static_runs_the_static_check_and_not_the_cases() -> None:
    tester, registry = MockStackTester(), MockStackRegistry()
    code, _ = _run(tester, registry, ["fixture", "--static"])
    assert code == 0
    assert [c for c in tester.calls if c[0] == "static"]
    assert not [c for c in tester.calls if c[0] == "run"]


def test_case_passes_the_case_id_to_run() -> None:
    tester, registry = MockStackTester(), MockStackRegistry()
    _run(tester, registry, ["fixture", "--case", "clean"])
    run = [c for c in tester.calls if c[0] == "run"]
    assert run[0][1][1] == "clean"


def test_output_is_the_rendered_report() -> None:
    tester, registry = MockStackTester(), MockStackRegistry()
    _, out = _run(tester, registry, ["fixture"])
    report = tester.run(registry.stacks["fixture"], None)
    assert tester.render(report) in out


def test_static_output_is_the_rendered_report() -> None:
    tester, registry = MockStackTester(), MockStackRegistry()
    _, out = _run(tester, registry, ["fixture", "--static"])
    assert tester.render(tester.static(registry.stacks["fixture"])) in out


def test_exit_is_1_when_a_case_fails() -> None:
    tester, registry = MockStackTester(), MockStackRegistry()
    tester.report = _failing()
    code, out = _run(tester, registry, ["fixture"])
    assert code == 1
    assert "fast" in out


def test_exit_is_1_when_a_case_was_not_run() -> None:
    tester, registry = MockStackTester(), MockStackRegistry()
    tester.report = StackTestReport(
        "fixture",
        False,
        (),
        (CaseResult("clean", CaseVerdict.NOT_RUN, "", "missing uv"),),
    )
    code, _ = _run(tester, registry, ["fixture"])
    assert code == 1


def test_exit_is_1_when_the_static_check_has_problems() -> None:
    tester, registry = MockStackTester(), MockStackRegistry()
    tester.report = _failing(static=True)
    code, out = _run(tester, registry, ["fixture", "--static"])
    assert code == 1
    assert "rules.md missing" in out


def test_exit_is_0_when_the_report_is_ok() -> None:
    tester, registry = MockStackTester(), MockStackRegistry()
    code, _ = _run(tester, registry, ["fixture"])
    assert code == 0


def test_json_emits_the_report_as_json_only() -> None:
    tester, registry = MockStackTester(), MockStackRegistry()
    tester.report = _failing()
    code, out = _run(tester, registry, ["fixture", "--json"])
    data = json.loads(out)
    assert code == 1
    assert data["stack"] == "fixture"
    assert data["static"] is False
    assert data["problems"] == []
    assert [(c["id"], c["verdict"]) for c in data["cases"]] == [
        ("clean", "pass"),
        ("fast", "fail"),
    ]
    assert data["cases"][1]["expected"] == "pass"
    assert data["cases"][1]["got"] == "fail"


def test_json_with_static_carries_the_problems() -> None:
    tester, registry = MockStackTester(), MockStackRegistry()
    tester.report = _failing(static=True)
    _, out = _run(tester, registry, ["fixture", "--static", "--json"])
    data = json.loads(out)
    assert data["static"] is True
    assert data["problems"] == ["rules.md missing"]


def test_json_exit_is_0_when_ok() -> None:
    tester, registry = MockStackTester(), MockStackRegistry()
    code, out = _run(tester, registry, ["fixture", "--json"])
    assert code == 0
    assert json.loads(out)["stack"] == "fixture"


def test_an_unknown_stack_name_raises_the_registrys_stack_error() -> None:
    tester, registry = MockStackTester(), MockStackRegistry()
    with pytest.raises(StackError):
        _run(tester, registry, ["nope"])
    assert not [c for c in tester.calls if c[0] in ("run", "static")]


def test_static_with_case_raises_stack_error() -> None:
    tester, registry = MockStackTester(), MockStackRegistry()
    with pytest.raises(StackError):
        _run(tester, registry, ["fixture", "--static", "--case", "clean"])
    assert not [c for c in tester.calls if c[0] in ("run", "static")]
