"""Journey 12: a rewrite's reference tests must be scanned before a module merges."""

from __future__ import annotations

import json
from pathlib import Path

from tests.journey.conftest import (
    TALLY_MEMO,
    TALLY_MODULE_WORK,
    TALLY_SKELETON,
    BullRunner,
    bull_ok,
    commit_all,
    git,
    new_tally_app,
    write_files,
)

MERGE = "git merge --no-ff module/Store"

REWRITE_MEMO = TALLY_MEMO.replace(
    "- Reference tests: none\n- Contract: pending\n\n### Counter",
    "- Reference tests: v1-tests/test_store.py, v1-tests/test_reset.py\n"
    "- Contract: pending\n\n### Counter",
).replace(
    "## Decisions log",
    "## Unmapped reference tests\n"
    "- v1-tests/test_store.py::test_pickle_format: v1 stored pickles; v2 has no storage.\n\n"
    "## Decisions log",
)


def _call(app: Path, tool: str, tool_input: dict[str, str], agent: str | None) -> str:
    event: dict[str, object] = {
        "cwd": str(app),
        "hook_event_name": "PreToolUse",
        "tool_name": tool,
        "tool_input": tool_input,
    }
    if agent is not None:
        event["agent_type"] = agent
    return json.dumps(event)


def _store_ready_to_merge(
    bull: BullRunner, tmp_path: Path, env: dict[str, str]
) -> Path:
    """A rewrite app whose Store has every unit done and the full gates recorded; on ``main``."""
    app = new_tally_app(bull, tmp_path, env, stage=5)
    write_files(app, TALLY_SKELETON)
    write_files(app, {"docs/outline.md": REWRITE_MEMO})
    bull_ok(bull, "status", "init-modules", "--replace", cwd=app)
    for module in ("Store", "Counter"):
        bull_ok(bull, "api", module, "--write", cwd=app)
    commit_all(app, env, "chore: skeleton and rewrite memo")
    write_files(app, {"reference/v1-tests/test_store.py": "# old test\n"})
    git(app, env, "switch", "-c", "module/Store", "main")
    bull_ok(bull, "status", "module", "Store", "in_progress", cwd=app)
    bull_ok(bull, "status", "unit", "Store", "1", "tests", cwd=app)
    work = TALLY_MODULE_WORK["Store"]
    write_files(app, {k: v for k, v in work.items() if k.startswith("tests/")})
    commit_all(app, env, "test(Store): unit 1 tests")
    write_files(app, {k: v for k, v in work.items() if k.startswith("src/")})
    bull_ok(bull, "gates", "Store", "--fast", cwd=app)
    bull_ok(bull, "status", "unit", "Store", "1", "code", cwd=app)
    bull_ok(bull, "status", "unit", "Store", "1", "done", cwd=app)
    commit_all(app, env, "feat(Store): unit 1")
    return app


def test_reference_test_scan_is_required_before_store_merges(
    bull: BullRunner, tmp_path: Path, journey_env: dict[str, str]
) -> None:
    env = journey_env
    app = _store_ready_to_merge(bull, tmp_path, env)

    # The memo's reference tests mark Store; next names the scan before coverage triage.
    modules = {
        m["name"]: m
        for m in json.loads(bull_ok(bull, "status", "--json", cwd=app).stdout)[
            "modules"
        ]
    }
    assert modules["Store"]["reference_tests"] is True
    assert modules["Store"]["scan"] is None
    nxt = bull_ok(bull, "status", "next", cwd=app).stdout
    assert "reference-test scan for Store" in nxt

    # Gates pass and record, but the merge guard still wants the scan.
    bull_ok(bull, "gates", "Store", cwd=app)
    git(app, env, "switch", "main")
    shell = _call(app, "Bash", {"command": MERGE}, None)
    refused = bull("hook", "before-shell", cwd=app, stdin=shell)
    assert refused.returncode == 2
    assert "record the reference-test scan for Store first" in (
        refused.stdout + refused.stderr
    )

    # Recording the scan on main (where the merge guard reads it) makes the merge
    # allowed, and it goes through.
    recorded = bull(
        "status",
        "refscan",
        "Store",
        "--covered",
        "3",
        "--missed",
        "1",
        "--contradicts",
        "0",
        "--not-in-spec",
        "0",
        cwd=app,
    )
    assert recorded.returncode == 0, recorded.stdout + recorded.stderr
    scan = {
        m["name"]: m
        for m in json.loads(bull_ok(bull, "status", "--json", cwd=app).stdout)[
            "modules"
        ]
    }["Store"]["scan"]
    assert scan["covered"] == 3 and scan["missed"] == 1
    assert scan["contradicts"] == 0 and scan["not_in_spec"] == 0
    commit_all(app, env, "chore: reference-test scan recorded")
    allowed = bull("hook", "before-shell", cwd=app, stdin=shell)
    assert allowed.returncode == 0, allowed.stdout + allowed.stderr
    merged = git(
        app, env, "merge", "--no-ff", "-m", "Merge Store", "module/Store", check=False
    )
    assert merged.returncode == 0, merged.stdout + merged.stderr
    assert (app / "src/Modules/Store/store.fx").is_file()


def test_refscan_without_every_count_is_a_usage_error_and_records_nothing(
    bull: BullRunner, tmp_path: Path, journey_env: dict[str, str]
) -> None:
    app = _store_ready_to_merge(bull, tmp_path, journey_env)
    before = (app / ".bull" / "status.json").read_text()
    partial_runs = (
        ("--covered", "3", "--missed", "1"),
        ("--covered", "3", "--missed", "1", "--contradicts", "0"),
        ("--covered", "3", "--missed", "1", "--not-in-spec", "0"),
    )
    for counts in partial_runs:
        result = bull("status", "refscan", "Store", *counts, cwd=app)
        assert result.returncode == 2, counts
    assert (app / ".bull" / "status.json").read_text() == before
    scan = {
        m["name"]: m
        for m in json.loads(bull_ok(bull, "status", "--json", cwd=app).stdout)[
            "modules"
        ]
    }["Store"]["scan"]
    assert scan is None


def test_agents_that_write_code_are_kept_away_from_the_reference_folder(
    bull: BullRunner, tmp_path: Path, journey_env: dict[str, str]
) -> None:
    app = _store_ready_to_merge(bull, tmp_path, journey_env)
    inside = str(app / "reference" / "v1-tests" / "test_store.py")

    for target in ("bull:test-writer", "bull:code-writer"):
        launch = _call(
            app,
            "Task",
            {"subagent_type": target, "prompt": "port the cases in reference/v1-tests"},
            None,
        )
        blocked = bull("hook", "before-agent", cwd=app, stdin=launch)
        assert blocked.returncode == 2, target
        assert "never give the reference folder" in blocked.stdout + blocked.stderr

        absolute = _call(
            app,
            "Task",
            {"subagent_type": target, "prompt": f"read {app / 'reference'}"},
            None,
        )
        assert bull("hook", "before-agent", cwd=app, stdin=absolute).returncode == 2

        fine = _call(
            app,
            "Task",
            {"subagent_type": target, "prompt": "write the unit from the memo"},
            None,
        )
        assert bull("hook", "before-agent", cwd=app, stdin=fine).returncode == 0

    for agent in ("bull:test-writer", "bull:code-writer"):
        read = _call(app, "Read", {"file_path": inside}, agent)
        blocked = bull("hook", "before-read", cwd=app, stdin=read)
        assert blocked.returncode == 2, agent

    other = _call(app, "Read", {"file_path": inside}, "bull:reviewer")
    assert bull("hook", "before-read", cwd=app, stdin=other).returncode == 0
    inside_src = _call(
        app,
        "Read",
        {"file_path": str(app / "src/Modules/Store/store.fx")},
        "bull:code-writer",
    )
    assert bull("hook", "before-read", cwd=app, stdin=inside_src).returncode == 0
