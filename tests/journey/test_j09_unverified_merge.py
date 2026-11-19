"""Journey 9: a merge of a branch without a recorded full gate pass is blocked."""

from __future__ import annotations

import json
from pathlib import Path

from tests.journey.conftest import (
    TALLY_MODULE_WORK,
    TALLY_SKELETON,
    BullRunner,
    build_tally_module,
    bull_ok,
    commit_all,
    git,
    git_out,
    new_tally_app,
    run_cmd,
    write_files,
)

MERGE = "git merge --no-ff module/Counter"


def _shell_call(app: Path, command: str) -> str:
    """The JSON a provider sends before running a shell command."""
    return json.dumps(
        {
            "cwd": str(app),
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": command},
        }
    )


def _counter_branch_after_fast_gates(
    bull: BullRunner, tmp_path: Path, env: dict[str, str]
) -> Path:
    """A tally app with ``module/Counter`` fully written and fast-gated, and ``main`` checked out."""
    app = new_tally_app(bull, tmp_path, env, stage=5)
    write_files(app, TALLY_SKELETON)
    for module in ("Store", "Counter"):
        bull_ok(bull, "api", module, "--write", cwd=app)
    commit_all(app, env, "chore: skeleton")
    build_tally_module(bull, app, env, "Store")
    git(app, env, "switch", "-c", "module/Counter", "main")
    bull_ok(bull, "status", "module", "Counter", "in_progress", cwd=app)
    bull_ok(bull, "status", "unit", "Counter", "1", "tests", cwd=app)
    work = TALLY_MODULE_WORK["Counter"]
    write_files(app, {k: v for k, v in work.items() if k.startswith("tests/")})
    commit_all(app, env, "test(Counter): unit 1 tests")
    write_files(app, {k: v for k, v in work.items() if k.startswith("src/")})
    fast = bull_ok(bull, "gates", "Counter", "--fast", cwd=app)
    assert "not recorded" in fast.stdout
    bull_ok(bull, "status", "unit", "Counter", "1", "code", cwd=app)
    bull_ok(bull, "status", "unit", "Counter", "1", "done", cwd=app)
    commit_all(app, env, "feat(Counter): unit 1")
    git(app, env, "switch", "main")
    return app


def test_an_unverified_merge_is_blocked_until_the_full_gates_pass(
    bull: BullRunner, tmp_path: Path, journey_env: dict[str, str]
) -> None:
    env = journey_env
    app = _counter_branch_after_fast_gates(bull, tmp_path, env)
    head = git_out(app, env, "rev-parse", "module/Counter")

    # Only --fast ran: the guard refuses and names the ref and the sha.
    refused = bull("hook", "before-shell", cwd=app, stdin=_shell_call(app, MERGE))
    assert refused.returncode == 2
    message = refused.stdout + refused.stderr
    assert "no recorded full gate pass" in message
    assert "module/Counter" in message
    assert head in message
    assert "bull gates" in message
    assert not (app / ".bull" / "passes" / f"{head}.json").exists()

    # The full gates on a clean tree record the pass; the same merge is then allowed.
    git(app, env, "switch", "module/Counter")
    full = bull_ok(bull, "gates", "Counter", cwd=app)
    assert "not recorded" not in full.stdout
    assert full.stdout.rstrip().endswith("recorded")
    record = json.loads((app / ".bull" / "passes" / f"{head}.json").read_text())
    assert record["sha"] == head
    assert record["branch"] == "module/Counter"
    git(app, env, "switch", "main")
    allowed = bull("hook", "before-shell", cwd=app, stdin=_shell_call(app, MERGE))
    assert allowed.returncode == 0

    # Ends when the merge goes through.
    merged = run_cmd(
        ["git", "merge", "--no-ff", "-m", "Merge Counter", "module/Counter"], app, env
    )
    assert merged.returncode == 0, merged.stdout + merged.stderr
    parents = git_out(app, env, "rev-list", "--parents", "-n", "1", "HEAD").split()
    assert head in parents[1:]
    assert (app / "src/Modules/Counter/counter.fx").is_file()


def test_a_dirty_working_tree_passes_the_gates_without_recording_and_says_why(
    bull: BullRunner, tmp_path: Path, journey_env: dict[str, str]
) -> None:
    env = journey_env
    app = _counter_branch_after_fast_gates(bull, tmp_path, env)
    git(app, env, "switch", "module/Counter")
    write_files(app, {"scratch.txt": "uncommitted\n"})

    dirty = bull_ok(bull, "gates", "Counter", cwd=app)
    assert "not recorded: working tree has changes" in dirty.stdout
    assert "✗" not in dirty.stdout
    head = git_out(app, env, "rev-parse", "module/Counter")
    assert not (app / ".bull" / "passes" / f"{head}.json").exists()

    # The guard still refuses the merge, with the same reason as before.
    git(app, env, "stash", "--include-untracked")
    git(app, env, "switch", "main")
    refused = bull("hook", "before-shell", cwd=app, stdin=_shell_call(app, MERGE))
    assert refused.returncode == 2
    assert "no recorded full gate pass" in refused.stdout + refused.stderr
