"""Tests for `bull.Modules.stacktest.runner` (`LiveStackTester`).

The bull command is a constructor argument, so these tests pass a fake `bull`: a small
script that snapshots the folder it runs in (cwd, git state, watched files), records its
argv, and prints canned `--json` output. No uv, no real toolchain.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from bull.Modules.stacks.Contracts import Requirement, Stack, StackError
from bull.Modules.stacks.mocks import sample_stack
from bull.Modules.stacktest.Contracts import (
    CaseResult,
    CaseVerdict,
    StackTestReport,
)
from bull.Modules.stacktest.runner import LiveStackTester

FAKE_BULL = """\
import json, os, subprocess, sys
from pathlib import Path

log = Path(os.environ["FAKE_BULL_LOG"])
calls = json.loads(log.read_text()) if log.exists() else []


def git(*args):
    done = subprocess.run(["git", *args], capture_output=True, text=True)
    return done.stdout


watch = {}
for name in filter(None, os.environ.get("FAKE_BULL_WATCH", "").split(",")):
    path = Path(name)
    watch[name] = path.read_text() if path.exists() else None
status = Path(".bull/status.json")
calls.append(
    {
        "argv": sys.argv[1:],
        "cwd": os.getcwd(),
        "toplevel": git("rev-parse", "--show-toplevel").strip(),
        "porcelain": git("status", "--porcelain"),
        "log": git("log", "--format=%s").splitlines(),
        "tracked": git("ls-files").splitlines(),
        "status": json.loads(status.read_text()) if status.exists() else None,
        "watch": watch,
    }
)
log.write_text(json.dumps(calls))
responses = json.loads(Path(os.environ["FAKE_BULL_RESPONSES"]).read_text())
response = responses[min(len(calls), len(responses)) - 1]
print(json.dumps(response))
sys.exit(1 if response.get("verdict") != "pass" else 0)
"""

MEMO = """# Memo

## Build order
1. counter (depends on: none)
2. greeter (depends on: counter)

## Modules

### counter
- Depends on: none
- Files: src/counter.fx

### greeter
- Depends on: counter
- Files: src/greeter.fx
"""

BASE_FILES = {
    "app/docs/outline.md": MEMO,
    "app/src/a.fx": "alpha\n",
    "app/tests/counter/a.test": "pass one\n",
}


def case(
    id: str,
    run: list[str] | None = None,
    expect: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "id": id,
        "run": run or ["gates", "counter"],
        "expect": expect or {"verdict": "pass"},
        **extra,
    }


def gates_json(
    verdict: str = "pass",
    *,
    failing: tuple[str, list[str]] | None = None,
    tests_run: int = 1,
    recorded: bool = False,
) -> dict[str, Any]:
    steps: list[dict[str, Any]] = [
        {"gate": "build", "part": "", "verdict": "pass", "labels": []}
    ]
    if failing is not None:
        steps.append(
            {
                "gate": failing[0],
                "part": "",
                "verdict": "fail",
                "labels": failing[1],
            }
        )
    return {
        "verdict": verdict,
        "steps": steps,
        "tests_run": tests_run,
        "failed_ids": {},
        "coverage": [],
        "recorded": recorded,
        "note": "",
    }


class Harness:
    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.tmp = tmp_path
        self.home = tmp_path / "mystack"
        self.log = tmp_path / "calls.json"
        self.responses = tmp_path / "responses.json"
        script = tmp_path / "fake_bull.py"
        script.write_text(FAKE_BULL)
        self.tester = LiveStackTester((sys.executable, str(script)))
        gitconfig = tmp_path / "gitconfig"
        gitconfig.write_text("")
        for key, value in {
            "FAKE_BULL_LOG": self.log,
            "FAKE_BULL_RESPONSES": self.responses,
            "GIT_CONFIG_GLOBAL": gitconfig,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.com",
        }.items():
            monkeypatch.setenv(key, str(value))
        monkeypatch.setenv("FAKE_BULL_WATCH", "")
        self.monkeypatch = monkeypatch
        self.responses.write_text(json.dumps([gates_json()]))

    def stack(
        self,
        cases: list[dict[str, Any]],
        *,
        layout: dict[str, str] | None = None,
        files: dict[str, str] | None = None,
        requires: tuple[str, ...] = ("git",),
    ) -> Stack:
        self.home.mkdir(exist_ok=True)
        (self.home / "cases.json").write_text(
            json.dumps(
                {
                    "format": 1,
                    "layout": layout or {"app/": "."},
                    "settings": {"source_dir": "src", "test_dir": "tests"},
                    "cases": cases,
                }
            )
        )
        for name, text in (BASE_FILES if files is None else files).items():
            path = self.home / "fixture" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        base = sample_stack("mystack")
        manifest = replace(
            base.manifest,
            requires=tuple(Requirement(tool, "install it") for tool in requires),
        )
        return replace(base, home=self.home, manifest=manifest)

    def respond(self, *responses: dict[str, Any]) -> None:
        self.responses.write_text(json.dumps(list(responses)))

    def watch(self, *paths: str) -> None:
        self.monkeypatch.setenv("FAKE_BULL_WATCH", ",".join(paths))

    def calls(self) -> list[dict[str, Any]]:
        if not self.log.exists():
            return []
        calls: list[dict[str, Any]] = json.loads(self.log.read_text())
        return calls

    def run(
        self, stack: Stack, case_id: str | None = None
    ) -> tuple[StackTestReport, list[dict[str, Any]]]:
        report = self.tester.run(stack, case_id)
        return report, self.calls()


@pytest.fixture
def h(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Harness:
    return Harness(tmp_path, monkeypatch)


def _text(result: CaseResult) -> str:
    return f"{result.expected} {result.got}"


# --- the app folder each case runs in -----------------------------------------


def test_run_passes_a_case_whose_expectation_matches(h: Harness) -> None:
    stack = h.stack([case("clean", expect={"verdict": "pass"})])
    report, calls = h.run(stack)
    assert [(r.id, r.verdict) for r in report.cases] == [("clean", CaseVerdict.PASS)]
    assert report.ok
    assert len(calls) == 1


def test_run_report_names_the_stack_and_is_not_static(h: Harness) -> None:
    report, _ = h.run(h.stack([case("clean")]))
    assert report.stack == "mystack"
    assert report.static is False
    assert report.problems == ()


def test_run_passes_the_run_arguments_to_bull_and_adds_json_for_gates(
    h: Harness,
) -> None:
    _, calls = h.run(h.stack([case("clean", run=["gates", "counter", "--fast"])]))
    argv = calls[0]["argv"]
    assert argv[:3] == ["gates", "counter", "--fast"]
    assert "--json" in argv


def test_run_runs_bull_in_a_git_repo_with_committed_bull_state(h: Harness) -> None:
    _, calls = h.run(h.stack([case("clean")]))
    call = calls[0]
    assert os.path.realpath(call["toplevel"]) == os.path.realpath(call["cwd"])
    assert ".bull/status.json" in call["tracked"]
    assert call["porcelain"] == ""
    assert len(call["log"]) >= 1


def test_run_writes_status_at_stage_5_with_the_fixture_memo_modules(
    h: Harness,
) -> None:
    _, calls = h.run(h.stack([case("clean")]))
    status = calls[0]["status"]
    assert status["stage"] == 5
    assert [m["name"] for m in status["modules"]] == ["counter", "greeter"]


def test_run_copies_the_fixture_into_the_folder_by_layout(h: Harness) -> None:
    h.watch("src/a.fx", "tests/counter/a.test", "docs/outline.md")
    _, calls = h.run(h.stack([case("clean")]))
    watch = calls[0]["watch"]
    assert watch["src/a.fx"] == "alpha\n"
    assert watch["tests/counter/a.test"] == "pass one\n"
    assert watch["docs/outline.md"] == MEMO
    assert ".bull/status.json" in calls[0]["tracked"]
    assert "src/a.fx" in calls[0]["tracked"]


def test_run_layout_can_map_a_fixture_folder_to_a_subfolder(h: Harness) -> None:
    h.watch("part/src/a.fx")
    stack = h.stack([case("clean")], layout={"app/": "part"})
    _, calls = h.run(stack)
    assert calls[0]["watch"]["part/src/a.fx"] == "alpha\n"


def test_run_leaves_the_stacks_own_fixture_unchanged(h: Harness) -> None:
    stack = h.stack(
        [case("c", change={"replace": {"src/a.fx": "changed\n"}})],
    )
    h.run(stack)
    assert (h.home / "fixture" / "app" / "src" / "a.fx").read_text() == "alpha\n"


def test_run_starts_every_case_in_a_fresh_folder(h: Harness) -> None:
    stack = h.stack(
        [
            case("first", change={"add": {"src/new.fx": "x\n"}}),
            case("second"),
        ]
    )
    h.watch("src/new.fx")
    _, calls = h.run(stack)
    assert calls[0]["cwd"] != calls[1]["cwd"]
    assert calls[0]["watch"]["src/new.fx"] == "x\n"
    assert calls[1]["watch"]["src/new.fx"] is None


def test_run_removes_the_temp_folders_afterwards(h: Harness) -> None:
    stack = h.stack([case("one"), case("two", then=case("ignored"))])
    _, calls = h.run(stack)
    assert calls
    for call in calls:
        assert not Path(call["cwd"]).exists()


# --- change -------------------------------------------------------------------


def test_run_applies_add_replace_and_delete_and_commits_them(h: Harness) -> None:
    h.watch("src/new.fx", "src/a.fx", "tests/counter/a.test")
    stack = h.stack(
        [
            case(
                "c",
                change={
                    "add": {"src/new.fx": "fresh\n"},
                    "replace": {"src/a.fx": "beta\n"},
                    "delete": ["tests/counter/a.test"],
                },
            )
        ]
    )
    _, calls = h.run(stack)
    call = calls[0]
    assert call["watch"] == {
        "src/new.fx": "fresh\n",
        "src/a.fx": "beta\n",
        "tests/counter/a.test": None,
    }
    assert call["porcelain"] == ""
    assert len(call["log"]) >= 2


def test_run_without_change_makes_no_extra_commit(h: Harness) -> None:
    stack = h.stack(
        [case("plain"), case("changed", change={"add": {"src/n.fx": "x\n"}})]
    )
    _, calls = h.run(stack)
    assert len(calls[1]["log"]) == len(calls[0]["log"]) + 1


def test_run_leaves_a_dirty_case_uncommitted(h: Harness) -> None:
    h.watch("src/a.fx")
    stack = h.stack([case("d", change={"replace": {"src/a.fx": "beta\n"}}, dirty=True)])
    _, calls = h.run(stack)
    call = calls[0]
    assert call["watch"]["src/a.fx"] == "beta\n"
    assert "src/a.fx" in call["porcelain"]


def test_run_dirty_added_file_stays_uncommitted(h: Harness) -> None:
    stack = h.stack([case("d", change={"add": {"src/n.fx": "x\n"}}, dirty=True)])
    _, calls = h.run(stack)
    assert "src/n.fx" in calls[0]["porcelain"]
    assert "src/n.fx" not in calls[0]["tracked"]


@pytest.mark.parametrize(
    "change",
    [
        {"replace": {"src/missing.fx": "x\n"}},
        {"delete": ["src/missing.fx"]},
    ],
)
def test_run_fails_a_case_whose_change_does_not_apply(
    h: Harness, change: dict[str, Any]
) -> None:
    report, calls = h.run(h.stack([case("bad", change=change)]))
    assert [r.verdict for r in report.cases] == [CaseVerdict.FAIL]
    assert "change does not apply" in _text(report.cases[0])
    assert calls == []
    assert not report.ok


def test_run_a_bad_change_does_not_stop_the_next_case(h: Harness) -> None:
    stack = h.stack(
        [case("bad", change={"delete": ["nope.fx"]}), case("good")],
    )
    report, calls = h.run(stack)
    assert [(r.id, r.verdict) for r in report.cases] == [
        ("bad", CaseVerdict.FAIL),
        ("good", CaseVerdict.PASS),
    ]
    assert len(calls) == 1


# --- expect -------------------------------------------------------------------

FAILING = gates_json("fail", failing=("tests", ["one", "two"]), tests_run=3)


@pytest.mark.parametrize(
    ("expect", "response", "verdict"),
    [
        ({"verdict": "pass"}, gates_json("pass"), CaseVerdict.PASS),
        ({"verdict": "pass"}, FAILING, CaseVerdict.FAIL),
        ({"verdict": "fail"}, FAILING, CaseVerdict.PASS),
        ({"verdict": "fail"}, gates_json("pass"), CaseVerdict.FAIL),
        ({"verdict": "fail", "gate": "tests"}, FAILING, CaseVerdict.PASS),
        ({"verdict": "fail", "gate": "lint"}, FAILING, CaseVerdict.FAIL),
        ({"verdict": "fail", "output": "two"}, FAILING, CaseVerdict.PASS),
        ({"verdict": "fail", "output": "three"}, FAILING, CaseVerdict.FAIL),
        (
            {"verdict": "pass", "recorded": True},
            gates_json(recorded=True),
            CaseVerdict.PASS,
        ),
        (
            {"verdict": "pass", "recorded": True},
            gates_json(recorded=False),
            CaseVerdict.FAIL,
        ),
        (
            {"verdict": "pass", "recorded": False},
            gates_json(recorded=False),
            CaseVerdict.PASS,
        ),
        (
            {"verdict": "pass", "recorded": False},
            gates_json(recorded=True),
            CaseVerdict.FAIL,
        ),
        ({"verdict": "fail", "ran": 3}, FAILING, CaseVerdict.PASS),
        ({"verdict": "fail", "ran": 1}, FAILING, CaseVerdict.FAIL),
        ({"verdict": "pass", "ran": 0}, gates_json(tests_run=0), CaseVerdict.PASS),
    ],
)
def test_run_compares_each_expect_key(
    h: Harness,
    expect: dict[str, Any],
    response: dict[str, Any],
    verdict: CaseVerdict,
) -> None:
    h.respond(response)
    report, _ = h.run(h.stack([case("c", expect=expect)]))
    assert report.cases[0].verdict is verdict
    assert report.ok is (verdict is CaseVerdict.PASS)


def test_run_fails_when_any_one_expect_key_mismatches(h: Harness) -> None:
    h.respond(FAILING)
    expect = {"verdict": "fail", "gate": "tests", "output": "one", "ran": 99}
    report, _ = h.run(h.stack([case("c", expect=expect)]))
    assert report.cases[0].verdict is CaseVerdict.FAIL


def test_run_failure_reports_expected_and_got_text(h: Harness) -> None:
    h.respond(gates_json("pass"))
    report, _ = h.run(h.stack([case("c", expect={"verdict": "fail"})]))
    result = report.cases[0]
    assert "fail" in result.expected
    assert "pass" in result.got


def test_run_failure_names_the_mismatching_value(h: Harness) -> None:
    h.respond(FAILING)
    report, _ = h.run(h.stack([case("c", expect={"verdict": "fail", "ran": 99})]))
    result = report.cases[0]
    assert "99" in result.expected
    assert "3" in result.got


# --- then ---------------------------------------------------------------------


def test_run_then_runs_in_the_same_folder_after_the_case(h: Harness) -> None:
    h.respond(FAILING, gates_json("fail", failing=("tests", ["one"]), tests_run=1))
    stack = h.stack(
        [
            case(
                "failing-test",
                expect={"verdict": "fail", "gate": "tests"},
                then={
                    "run": ["gates", "--failed"],
                    "expect": {"verdict": "fail", "ran": 1},
                },
            )
        ]
    )
    report, calls = h.run(stack)
    assert [(r.id, r.verdict) for r in report.cases] == [
        ("failing-test", CaseVerdict.PASS),
        ("failing-test/then", CaseVerdict.PASS),
    ]
    assert len(calls) == 2
    assert calls[0]["cwd"] == calls[1]["cwd"]
    assert calls[1]["argv"][:2] == ["gates", "--failed"]
    assert "--json" in calls[1]["argv"]


def test_run_then_result_is_judged_against_its_own_expect(h: Harness) -> None:
    h.respond(gates_json("pass"), gates_json("pass"))
    stack = h.stack(
        [
            case(
                "p",
                then={"run": ["gates", "--failed"], "expect": {"verdict": "fail"}},
            )
        ]
    )
    report, _ = h.run(stack)
    assert [(r.id, r.verdict) for r in report.cases] == [
        ("p", CaseVerdict.PASS),
        ("p/then", CaseVerdict.FAIL),
    ]


def test_run_then_sees_the_changes_of_its_case(h: Harness) -> None:
    h.watch("src/n.fx")
    stack = h.stack(
        [
            case(
                "p",
                change={"add": {"src/n.fx": "x\n"}},
                then={"run": ["gates", "--failed"], "expect": {"verdict": "pass"}},
            )
        ]
    )
    _, calls = h.run(stack)
    assert calls[1]["watch"]["src/n.fx"] == "x\n"


# --- selecting a case ---------------------------------------------------------


def test_run_with_a_case_id_runs_only_that_case(h: Harness) -> None:
    stack = h.stack([case("a"), case("b"), case("c")])
    report, calls = h.run(stack, "b")
    assert [r.id for r in report.cases] == ["b"]
    assert len(calls) == 1


def test_run_with_a_case_id_also_runs_its_then(h: Harness) -> None:
    stack = h.stack(
        [
            case("a"),
            case(
                "b",
                then={"run": ["gates", "--failed"], "expect": {"verdict": "pass"}},
            ),
        ]
    )
    report, _ = h.run(stack, "b")
    assert [r.id for r in report.cases] == ["b", "b/then"]


# --- not run ------------------------------------------------------------------


def test_run_marks_every_case_not_run_when_a_required_tool_is_missing(
    h: Harness,
) -> None:
    stack = h.stack(
        [case("a"), case("b")], requires=("git", "no-such-tool-for-bull-tests")
    )
    report, calls = h.run(stack)
    assert [(r.id, r.verdict) for r in report.cases] == [
        ("a", CaseVerdict.NOT_RUN),
        ("b", CaseVerdict.NOT_RUN),
    ]
    assert all("missing no-such-tool-for-bull-tests" in _text(r) for r in report.cases)
    assert calls == []
    assert not report.ok


def test_run_marks_every_case_not_run_when_a_layout_fixture_file_is_missing(
    h: Harness,
) -> None:
    stack = h.stack([case("a"), case("b")], layout={"nowhere/": "."})
    report, calls = h.run(stack)
    assert [r.verdict for r in report.cases] == [CaseVerdict.NOT_RUN] * 2
    assert calls == []
    assert not report.ok


# --- wiring -------------------------------------------------------------------


def test_load_cases_reads_the_stacks_cases_json(h: Harness) -> None:
    stack = h.stack([case("a"), case("b", change={"delete": ["x"]})])
    cases = h.tester.load_cases(stack)
    assert [c.id for c in cases] == ["a", "b"]
    assert cases[1].change["delete"] == ("x",)


def test_load_cases_malformed_cases_json_raises_stack_error(h: Harness) -> None:
    stack = h.stack([case("a")])
    (h.home / "cases.json").write_text("{nope")
    with pytest.raises(StackError):
        h.tester.load_cases(stack)


def test_static_returns_a_static_report_with_problems_for_a_broken_stack(
    h: Harness,
) -> None:
    stack = h.stack([case("a")])
    report = h.tester.static(stack)
    assert report.static is True
    assert report.stack == "mystack"
    assert report.cases == ()
    assert report.problems
    assert not report.ok


# --- render -------------------------------------------------------------------


def _report(
    *results: CaseResult, problems: tuple[str, ...] = (), static: bool = False
) -> StackTestReport:
    return StackTestReport("mystack", static, problems, results)


def test_render_lists_each_case_with_its_verdict(h: Harness) -> None:
    text = h.tester.render(
        _report(
            CaseResult("clean", CaseVerdict.PASS, "pass", "pass"),
            CaseResult("fast", CaseVerdict.FAIL, "pass", "fail"),
            CaseResult("lint", CaseVerdict.NOT_RUN, "", "missing uv"),
        )
    )
    assert "mystack" in text
    for word in ("clean", "fast", "lint", "pass", "fail", "not run"):
        assert word in text
    assert text.endswith("\n")


def test_render_shows_expected_and_got_for_a_failed_case(h: Harness) -> None:
    text = h.tester.render(
        _report(CaseResult("fast", CaseVerdict.FAIL, "EXPECTED-X", "GOT-Y"))
    )
    assert "EXPECTED-X" in text
    assert "GOT-Y" in text


def test_render_shows_not_run_reason(h: Harness) -> None:
    text = h.tester.render(
        _report(CaseResult("lint", CaseVerdict.NOT_RUN, "", "missing uv"))
    )
    assert "missing uv" in text


def test_render_shows_every_problem(h: Harness) -> None:
    text = h.tester.render(
        _report(problems=("rules.md: no `## common`", "setup.md missing"), static=True)
    )
    assert "rules.md: no `## common`" in text
    assert "setup.md missing" in text
