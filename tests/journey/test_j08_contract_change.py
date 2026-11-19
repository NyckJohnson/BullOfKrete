"""Journey 8: a contract change stops the pipeline until the human approves it."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tests.journey.conftest import (
    TALLY_MEMO,
    TALLY_MODULE_WORK,
    TALLY_SKELETON,
    BullRunner,
    build_tally_module,
    bull_ok,
    commit_all,
    git,
    new_accepted_tally_app,
    new_tally_app,
    write_files,
)

COUNTER_CONTRACT = "src/Modules/Counter/Contracts/counter.fx"
CHANGED_CONTRACT = (
    "# counter contract\npub Counter\npub increment\npub reset\nfield value: integer\n"
)
FURTHER_CONTRACT = (
    "# counter contract\npub Counter\npub increment\npub reset\npub undo\n"
    "field value: integer\n"
)
TWO_UNIT_MEMO = TALLY_MEMO.replace(
    "- Files: Contracts/counter.fx, counter.fx",
    "- Files: Contracts/counter.fx, counter.fx | helpers.fx",
)
FEATURE_MEMO_LINES = (
    "- Changes (reset-button): Contracts/counter.fx, counter.fx\n"
    "- Contract changes (reset-button): Counter gains a reset operation\n"
)


def _status(bull: BullRunner, app: Path) -> dict[str, Any]:
    loaded = json.loads(bull_ok(bull, "status", "--json", cwd=app).stdout)
    assert isinstance(loaded, dict)
    return loaded


def _agent_launch(app: Path) -> str:
    """The JSON a provider sends before launching the code-writer subagent."""
    return json.dumps(
        {
            "cwd": str(app),
            "hook_event_name": "PreToolUse",
            "tool_name": "Task",
            "tool_input": {"subagent_type": "code-writer", "prompt": "write unit 2"},
        }
    )


def _counter_in_unit_two(bull: BullRunner, tmp_path: Path, env: dict[str, str]) -> Path:
    """Store done; Counter has two units, unit 1 done and unit 2 waiting for its code."""
    app = new_tally_app(bull, tmp_path, env, stage=2)
    write_files(app, {"docs/outline.md": TWO_UNIT_MEMO})
    commit_all(app, env, "docs: counter in two units")
    bull_ok(bull, "status", "init-modules", "--replace", cwd=app)
    write_files(app, {"fixture.toml": ""})
    bull_ok(bull, "status", "checkpoint", "setup", cwd=app)
    bull_ok(bull, "status", "stage", "3", cwd=app)
    write_files(app, TALLY_SKELETON)
    for module in ("Store", "Counter"):
        bull_ok(bull, "api", module, "--write", cwd=app)
    bull_ok(bull, "status", "checkpoint", "skeleton", cwd=app)
    bull_ok(bull, "status", "stage", "4", cwd=app)
    bull_ok(bull, "status", "checkpoint", "ui-approved", cwd=app)
    bull_ok(bull, "status", "stage", "5", cwd=app)
    commit_all(app, env, "chore: skeleton")
    build_tally_module(bull, app, env, "Store")

    git(app, env, "switch", "-c", "module/Counter", "main")
    bull_ok(bull, "status", "module", "Counter", "in_progress", cwd=app)
    bull_ok(bull, "status", "unit", "Counter", "1", "tests", cwd=app)
    work = TALLY_MODULE_WORK["Counter"]
    write_files(app, {k: v for k, v in work.items() if k.startswith("tests/")})
    commit_all(app, env, "test(Counter): unit 1 tests")
    write_files(app, {k: v for k, v in work.items() if k.startswith("src/")})
    bull_ok(bull, "gates", "Counter", "--fast", cwd=app)
    bull_ok(bull, "status", "unit", "Counter", "1", "code", cwd=app)
    bull_ok(bull, "status", "unit", "Counter", "1", "done", cwd=app)
    commit_all(app, env, "feat(Counter): unit 1")
    bull_ok(bull, "status", "unit", "Counter", "2", "tests", cwd=app)
    commit_all(app, env, "test(Counter): unit 2 tests")
    nxt = bull_ok(bull, "status", "next", cwd=app).stdout
    assert "Counter unit 2" in nxt
    return app


def test_a_contract_change_stops_the_pipeline_until_the_human_approves(
    bull: BullRunner, tmp_path: Path, journey_env: dict[str, str]
) -> None:
    env = journey_env
    app = _counter_in_unit_two(bull, tmp_path, env)
    snapshot = app / "docs" / "api" / "Counter.md"
    stored = snapshot.read_text()

    # The code-writer changes a contract declaration: the api gate fails with a diff.
    write_files(app, {COUNTER_CONTRACT: CHANGED_CONTRACT})
    fast = bull("gates", "Counter", "--fast", cwd=app)
    assert fast.returncode != 0
    assert "✗ api" in fast.stdout
    assert "docs/api/Counter.md" in fast.stdout
    assert "+reset" in fast.stdout
    assert "--- stored" in fast.stdout and "+++ current" in fast.stdout
    assert snapshot.read_text() == stored

    # The orchestrator records the wait: next reports it and agent launches are blocked.
    bull_ok(bull, "status", "wait", "Counter", "contract change", cwd=app)
    waiting = _status(bull, app)["waiting"]
    assert waiting["module"] == "Counter"
    assert waiting["what"] == "contract change"
    nxt = bull_ok(bull, "status", "next", cwd=app).stdout
    assert "waiting for the human to approve the Counter contract change" in nxt
    blocked = bull("hook", "before-agent", cwd=app, stdin=_agent_launch(app))
    assert blocked.returncode == 2
    assert "waiting for the human to approve the Counter contract change" in (
        blocked.stdout + blocked.stderr
    )

    # Dana approves: the decision is logged, the snapshot is written, the gates pass.
    bull_ok(bull, "status", "approve", "Counter", "reset is wanted", cwd=app)
    status = _status(bull, app)
    assert status["waiting"] is None
    assert [a["module"] for a in status["approvals"]] == ["Counter"]
    assert (
        bull("hook", "before-agent", cwd=app, stdin=_agent_launch(app)).returncode == 0
    )
    written = bull_ok(bull, "api", "Counter", "--write", cwd=app)
    assert "wrote" in written.stdout
    assert "reset" in snapshot.read_text()
    assert _status(bull, app)["approvals"] == []
    events = (app / ".bull" / "events.jsonl").read_text()
    assert any(
        json.loads(line)["kind"] == "decision" and "reset is wanted" in line
        for line in events.splitlines()
    )
    passed = bull_ok(bull, "gates", "Counter", "--fast", cwd=app)
    assert "✓ api" in passed.stdout

    # Ends when next names the unit again.
    nxt = bull_ok(bull, "status", "next", cwd=app).stdout
    assert "Counter unit 2" in nxt
    assert "waiting" not in nxt


def test_writing_a_changed_contract_without_an_approval_is_refused(
    bull: BullRunner, tmp_path: Path, journey_env: dict[str, str]
) -> None:
    env = journey_env
    app = _counter_in_unit_two(bull, tmp_path, env)
    snapshot = app / "docs" / "api" / "Counter.md"
    stored = snapshot.read_text()
    write_files(app, {COUNTER_CONTRACT: CHANGED_CONTRACT})

    refused = bull("api", "Counter", "--write", cwd=app)
    assert refused.returncode != 0
    message = refused.stdout + refused.stderr
    assert "Counter contract changed" in message
    assert 'bull status approve Counter "<note>"' in message
    assert snapshot.read_text() == stored
    still = bull("gates", "Counter", "--fast", cwd=app)
    assert still.returncode != 0


def test_a_feature_contract_change_listed_in_the_memo_passes_once_without_approval(
    bull: BullRunner, tmp_path: Path, journey_env: dict[str, str]
) -> None:
    env = journey_env
    app = new_accepted_tally_app(bull, tmp_path, env)
    ideas = tmp_path / "ideas.md"
    ideas.write_text(
        "# Ideas\n\n## Reset button\nAdd a reset button.\n", encoding="utf-8"
    )
    bull_ok(bull, "feature", "import", str(ideas), cwd=app)
    commit_all(app, env, "chore: queue ideas")
    bull_ok(bull, "feature", "start", "reset-button", cwd=app)
    bull_ok(bull, "status", "stage", "2", cwd=app)
    memo_path = app / "docs/outline.md"
    memo = memo_path.read_text()
    marked = memo.replace(
        "- Reference tests: none\n- Contract: pending\n\n## Decisions log",
        FEATURE_MEMO_LINES
        + "- Reference tests: none\n- Contract: pending\n\n## Decisions log",
    )
    assert marked != memo
    memo_path.write_text(marked, encoding="utf-8")
    commit_all(app, env, "docs: reset-button memo")
    bull_ok(bull, "status", "checkpoint", "outline-approved", cwd=app)
    bull_ok(bull, "feature", "plan", cwd=app)
    commit_all(app, env, "chore: plan reset-button")
    bull_ok(bull, "status", "checkpoint", "setup", cwd=app)
    bull_ok(bull, "status", "stage", "3", cwd=app)

    # The listed change writes once with no approval and no waiting.
    write_files(app, {COUNTER_CONTRACT: CHANGED_CONTRACT})
    assert bull("gates", "Counter", "--fast", cwd=app).returncode != 0
    written = bull_ok(bull, "api", "Counter", "--write", cwd=app)
    assert "wrote" in written.stdout
    status = _status(bull, app)
    assert status["feature"]["applied_contracts"] == ["Counter"]
    assert status["approvals"] == [] and status["waiting"] is None
    assert "reset" in (app / "docs/api/Counter.md").read_text()

    # A further change is not covered by the memo any more: it needs an approval.
    write_files(app, {COUNTER_CONTRACT: FURTHER_CONTRACT})
    refused = bull("api", "Counter", "--write", cwd=app)
    assert refused.returncode != 0
    assert "must approve" in refused.stdout + refused.stderr
    assert "undo" not in (app / "docs/api/Counter.md").read_text()
    bull_ok(bull, "status", "approve", "Counter", "undo is wanted too", cwd=app)
    again = bull_ok(bull, "api", "Counter", "--write", cwd=app)
    assert "wrote" in again.stdout
    assert "undo" in (app / "docs/api/Counter.md").read_text()
