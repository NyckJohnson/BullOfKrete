"""Tests for `bull.Modules.status.cli` (`bull status ...`).

Shapes chosen here (for the code-writer), following the decisions-log `cli.py` convention:
  - `register(commands, store, refs, progress, usage, memo)`: five zero-argument providers,
    called only when a command runs. Adds a `status` parser; `bull status` alone runs the
    summary. Every leaf sets `run(args, out) -> int`.
  - `status` prints `progress.summary()`; `status --json` writes `progress.as_json()` as JSON.
  - `status next` prints `progress.next_step().text`.
  - `status stage <n>`, `checkpoint <name>`, `init-modules [--replace]` (passes the memo),
    `module <M> <state>`, `unit <M> <n> <state>`, `attempt <M> <n>`, `unblock <M> <n>`,
    `pause <reason>`, `resume`, `wait <M> <what>`, `approve <M> <note>`,
    `refscan <M> --covered --missed --contradicts --not-in-spec`, `plan <label> <item>...`
    or `plan <label> --clear`, `tick <item>` call the store method of that name, return 0.
  - `status ref trunk|base|module <M>|tag <label>` prints the name from `refs`.
  - `status tags [--json]` prints one tag per line; `--json` a list.
  - `status usage-check [--json]` prints `OK|PAUSE|UNKNOWN: <reason>`, always exit 0; `--json`
    writes `{"verdict", "reason", "resets_at"}`.
  - Refusals are raised (`StatusError`), never printed.
"""

from __future__ import annotations

import argparse
import io
import json
from datetime import UTC, datetime
from typing import Any

import pytest

from bull.Modules.foundation.Contracts import BullError
from bull.Modules.memo.mocks import sample_memo
from bull.Modules.status.Contracts import (
    ModuleState,
    StatusError,
    UnitState,
)
from bull.Modules.status.mocks import MockProgress, MockRefs, MockStatusStore
from bull.Modules.usage.Contracts import UsageCheck, UsageVerdict
from bull.Modules.usage.mocks import MockUsage

MEMO = sample_memo()
RESETS = datetime(2026, 11, 7, 15, 0, 0, tzinfo=UTC)


class Rig:
    def __init__(self) -> None:
        self.store = MockStatusStore()
        self.refs = MockRefs()
        self.progress = MockProgress()
        self.usage = MockUsage()
        self.provided: list[str] = []
        # imported here so the file collects while `cli.py` is still a stub
        from bull.Modules.status.cli import register

        self.parser = argparse.ArgumentParser(prog="bull")
        commands = self.parser.add_subparsers(dest="command")
        register(
            commands,
            lambda: self._note("store", self.store),
            lambda: self._note("refs", self.refs),
            lambda: self._note("progress", self.progress),
            lambda: self._note("usage", self.usage),
            lambda: self._note("memo", MEMO),
        )

    def _note(self, name: str, value: Any) -> Any:
        self.provided.append(name)
        return value

    def run(self, *argv: str) -> tuple[int, str]:
        args = self.parser.parse_args(["status", *argv])
        out = io.StringIO()
        code = args.run(args, out)
        return code, out.getvalue()


@pytest.fixture
def rig() -> Rig:
    return Rig()


def called(rig: Rig) -> list[tuple[str, tuple[object, ...]]]:
    return rig.store.calls


# --- registration ------------------------------------------------------------------------


def test_register_does_not_call_any_provider(rig: Rig) -> None:
    rig.parser.parse_args(["status"])
    rig.parser.parse_args(["status", "tags"])
    rig.parser.parse_args(["status", "usage-check"])
    rig.parser.parse_args(["status", "stage", "3"])
    assert rig.provided == []


# --- summary and next --------------------------------------------------------------------


def test_status_prints_the_summary(rig: Rig) -> None:
    code, text = rig.run()
    assert code == 0
    assert rig.progress.summary().strip() in text


def test_status_json_writes_only_the_json_view(rig: Rig) -> None:
    code, text = rig.run("--json")
    assert code == 0
    assert json.loads(text) == rig.progress.as_json()


def test_status_next_prints_the_next_step(rig: Rig) -> None:
    code, text = rig.run("next")
    assert code == 0
    assert rig.progress.step.text in text


# --- store commands ----------------------------------------------------------------------


def test_stage_sets_the_stage_as_an_int(rig: Rig) -> None:
    code, _ = rig.run("stage", "6")
    assert code == 0
    assert called(rig) == [("set_stage", (6,))]


def test_stage_rejects_a_non_number(rig: Rig) -> None:
    with pytest.raises(SystemExit):
        rig.parser.parse_args(["status", "stage", "five"])


def test_checkpoint_records_the_name(rig: Rig) -> None:
    code, _ = rig.run("checkpoint", "app-accepted")
    assert code == 0
    assert called(rig) == [("checkpoint", ("app-accepted",))]


def test_init_modules_passes_the_memo_and_no_replace(rig: Rig) -> None:
    code, _ = rig.run("init-modules")
    assert code == 0
    assert called(rig) == [
        ("init_modules", (MEMO, False)),
        ("add_modules", (MEMO.modules,)),
    ]


def test_init_modules_replace_flag(rig: Rig) -> None:
    rig.run("init-modules", "--replace")
    assert called(rig)[0] == ("init_modules", (MEMO, True))


@pytest.mark.parametrize("state", [s.value for s in ModuleState])
def test_module_sets_the_state_enum(rig: Rig, state: str) -> None:
    code, _ = rig.run("module", "Counter", state)
    assert code == 0
    assert called(rig) == [("set_module", ("Counter", ModuleState(state)))]


def test_module_rejects_an_unknown_state(rig: Rig) -> None:
    with pytest.raises(SystemExit):
        rig.parser.parse_args(["status", "module", "Counter", "finished"])


@pytest.mark.parametrize("state", [s.value for s in UnitState])
def test_unit_sets_number_and_state(rig: Rig, state: str) -> None:
    code, _ = rig.run("unit", "Counter", "2", state)
    assert code == 0
    assert called(rig) == [("set_unit", ("Counter", 2, UnitState(state)))]


def test_unit_rejects_an_unknown_state(rig: Rig) -> None:
    with pytest.raises(SystemExit):
        rig.parser.parse_args(["status", "unit", "Counter", "1", "nope"])


def test_attempt_calls_the_store_with_an_int_unit(rig: Rig) -> None:
    code, _ = rig.run("attempt", "Counter", "1")
    assert code == 0
    assert called(rig) == [("attempt", ("Counter", 1))]


def test_unblock_calls_the_store(rig: Rig) -> None:
    code, _ = rig.run("unblock", "Counter", "1")
    assert code == 0
    assert called(rig) == [("unblock", ("Counter", 1))]


def test_pause_passes_the_reason(rig: Rig) -> None:
    code, _ = rig.run("pause", "usage at 90%")
    assert code == 0
    assert called(rig) == [("pause", ("usage at 90%",))]


def test_resume_calls_the_store(rig: Rig) -> None:
    code, _ = rig.run("resume")
    assert code == 0
    assert called(rig) == [("resume", ())]


def test_wait_passes_module_and_what(rig: Rig) -> None:
    code, _ = rig.run("wait", "Counter", "contract change")
    assert code == 0
    assert called(rig) == [("wait", ("Counter", "contract change"))]


def test_approve_passes_module_and_note(rig: Rig) -> None:
    code, _ = rig.run("approve", "Counter", "ok by human")
    assert code == 0
    assert called(rig) == [("approve", ("Counter", "ok by human"))]


def test_refscan_passes_the_four_counts(rig: Rig) -> None:
    code, _ = rig.run(
        "refscan", "Store", "--covered", "5", "--missed", "2",
        "--contradicts", "1", "--not-in-spec", "3",
    )  # fmt: skip
    assert code == 0
    assert called(rig) == [("record_scan", ("Store", 5, 2, 1, 3))]


def test_refscan_requires_all_counts(rig: Rig) -> None:
    with pytest.raises(SystemExit):
        rig.parser.parse_args(["status", "refscan", "Store", "--covered", "5"])


def test_plan_sets_label_and_items(rig: Rig) -> None:
    code, _ = rig.run("plan", "verify", "login", "export", "share")
    assert code == 0
    assert called(rig) == [("set_plan", ("verify", ("login", "export", "share")))]


def test_plan_clear_clears_the_plan(rig: Rig) -> None:
    code, _ = rig.run("plan", "verify", "--clear")
    assert code == 0
    assert called(rig) == [("clear_plan", ())]


def test_tick_passes_the_item(rig: Rig) -> None:
    code, _ = rig.run("tick", "login")
    assert code == 0
    assert called(rig) == [("tick", ("login",))]


# --- ref ---------------------------------------------------------------------------------


def test_ref_trunk_prints_the_trunk(rig: Rig) -> None:
    code, text = rig.run("ref", "trunk")
    assert code == 0
    assert text.strip() == "main"
    assert rig.refs.calls == [("trunk", ())]


def test_ref_base_prints_the_base(rig: Rig) -> None:
    rig.refs = MockRefs(prefix="feature/dark/")
    code, text = rig.run("ref", "base")
    assert code == 0
    assert text.strip() == "feature/dark/main"


def test_ref_module_prints_the_module_branch(rig: Rig) -> None:
    code, text = rig.run("ref", "module", "Counter")
    assert code == 0
    assert text.strip() == "module/Counter"
    assert rig.refs.calls == [("module_branch", ("Counter",))]


def test_ref_tag_prints_the_tag_name(rig: Rig) -> None:
    rig.refs = MockRefs(prefix="adopt/")
    code, text = rig.run("ref", "tag", "baseline")
    assert code == 0
    assert text.strip() == "adopt/baseline"


def test_ref_tag_adopted_stays_unprefixed(rig: Rig) -> None:
    rig.refs = MockRefs(prefix="adopt/")
    _, text = rig.run("ref", "tag", "adopted")
    assert text.strip() == "adopted"


def test_ref_rejects_an_unknown_kind() -> None:
    rig = Rig()
    with pytest.raises(SystemExit):
        rig.parser.parse_args(["status", "ref", "branch"])


# --- tags --------------------------------------------------------------------------------


def test_tags_prints_one_per_line(rig: Rig) -> None:
    code, text = rig.run("tags")
    assert code == 0
    assert text.split() == rig.progress.tags()


def test_tags_json_is_a_list(rig: Rig) -> None:
    code, text = rig.run("tags", "--json")
    assert code == 0
    assert json.loads(text) == rig.progress.tags()


def test_tags_json_empty_is_an_empty_list(rig: Rig) -> None:
    rig.progress.tag_names = []
    _, text = rig.run("tags", "--json")
    assert json.loads(text) == []


# --- usage-check -------------------------------------------------------------------------


def test_usage_check_ok_prints_verdict_and_reason(rig: Rig) -> None:
    code, text = rig.run("usage-check")
    assert code == 0
    assert text.strip() == f"OK: {rig.usage.check().reason}"


def test_usage_check_pause_prints_pause_and_exits_zero(rig: Rig) -> None:
    rig.usage.result = UsageCheck(UsageVerdict.PAUSE, "5-hour usage 90% ≥ 85%", RESETS)
    code, text = rig.run("usage-check")
    assert code == 0
    assert text.strip().startswith("PAUSE: ")
    assert "5-hour usage 90% ≥ 85%" in text


def test_usage_check_unknown_prints_unknown_and_exits_zero(rig: Rig) -> None:
    rig.usage.sample = None
    code, text = rig.run("usage-check")
    assert code == 0
    assert text.strip() == "UNKNOWN: no usage data yet"


def test_usage_check_json_gives_the_fields(rig: Rig) -> None:
    rig.usage.result = UsageCheck(UsageVerdict.PAUSE, "too high", RESETS)
    code, text = rig.run("usage-check", "--json")
    assert code == 0
    data = json.loads(text)
    assert data["verdict"].lower() == "pause"
    assert data["reason"] == "too high"
    assert data["resets_at"].startswith("2026-11-07T15:00")


def test_usage_check_json_has_null_resets_at_when_none(rig: Rig) -> None:
    code, text = rig.run("usage-check", "--json")
    assert code == 0
    data = json.loads(text)
    assert data["verdict"].lower() == "ok"
    assert data["resets_at"] is None


def test_usage_check_json_exit_zero_for_unknown(rig: Rig) -> None:
    rig.usage.sample = None
    code, text = rig.run("usage-check", "--json")
    assert code == 0
    assert json.loads(text)["verdict"].lower() == "unknown"


# --- providers are lazy ------------------------------------------------------------------


def test_a_store_command_only_asks_for_what_it_needs(rig: Rig) -> None:
    rig.run("stage", "3")
    assert "store" in rig.provided
    assert "usage" not in rig.provided
    assert "memo" not in rig.provided


def test_usage_check_only_asks_for_usage(rig: Rig) -> None:
    rig.run("usage-check")
    assert rig.provided
    assert set(rig.provided) == {"usage"}


# --- refusals propagate ------------------------------------------------------------------

REFUSABLE: list[tuple[str, list[str]]] = [
    ("set_stage", ["stage", "4"]),
    ("checkpoint", ["checkpoint", "skeleton"]),
    ("init_modules", ["init-modules"]),
    ("set_module", ["module", "Counter", "done"]),
    ("set_unit", ["unit", "Counter", "1", "done"]),
    ("attempt", ["attempt", "Counter", "1"]),
    ("unblock", ["unblock", "Counter", "1"]),
    ("pause", ["pause", "why"]),
    ("resume", ["resume"]),
    ("wait", ["wait", "Counter", "x"]),
    ("approve", ["approve", "Counter", "x"]),
    ("record_scan", ["refscan", "Store", "--covered", "1", "--missed", "0",
                     "--contradicts", "0", "--not-in-spec", "0"]),
    ("set_plan", ["plan", "p", "a"]),
    ("clear_plan", ["plan", "p", "--clear"]),
    ("tick", ["tick", "a"]),
]  # fmt: skip


@pytest.mark.parametrize(("method", "argv"), REFUSABLE)
def test_a_refusal_is_raised_not_printed(
    rig: Rig, method: str, argv: list[str]
) -> None:
    def refuse(*_args: object, **_kwargs: object) -> None:
        raise StatusError("refused for a reason")

    setattr(rig.store, method, refuse)
    args = rig.parser.parse_args(["status", *argv])
    out = io.StringIO()
    with pytest.raises(BullError, match="refused for a reason"):
        args.run(args, out)
    assert out.getvalue() == ""


def test_summary_refusal_propagates(rig: Rig) -> None:
    def refuse() -> str:
        raise StatusError("this is a stack repo")

    rig.progress.summary = refuse  # type: ignore[method-assign]
    args = rig.parser.parse_args(["status"])
    with pytest.raises(StatusError, match="stack repo"):
        args.run(args, io.StringIO())


def test_store_load_refusal_propagates_from_next(rig: Rig) -> None:
    def refuse() -> Any:
        raise StatusError("not a bull app (no .bull/status.json)")

    rig.progress.next_step = refuse  # type: ignore[method-assign]
    args = rig.parser.parse_args(["status", "next"])
    with pytest.raises(StatusError, match="not a bull app"):
        args.run(args, io.StringIO())
