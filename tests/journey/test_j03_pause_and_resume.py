"""Journey 3: pause on usage and resume."""

from __future__ import annotations

import json
import time
from pathlib import Path

from tests.journey.conftest import BullRunner, bull_ok, commit_all, git, new_tally_app


def _statusline_json(
    app: Path,
    five_hour: float,
    weekly: float = 20.0,
    context: float | None | str = "absent",
) -> str:
    """The status JSON Claude Code would send to the status line, with rate limits.

    `context` is the context window's used percentage; None sends null, "absent" omits
    the `context_window` key.
    """
    now = int(time.time())
    extra: dict[str, object] = {}
    if context != "absent":
        extra["context_window"] = {"used_percentage": context}
    return json.dumps(
        {
            **extra,
            "cwd": str(app),
            "workspace": {"current_dir": str(app)},
            "model": {"display_name": "Sonnet"},
            "rate_limits": {
                "five_hour": {"used_percentage": five_hour, "resets_at": now + 3600},
                "seven_day": {"used_percentage": weekly, "resets_at": now + 86400},
            },
        }
    )


def _before_agent_json(app: Path) -> str:
    """The PreToolUse JSON Claude Code sends before launching a subagent."""
    return json.dumps(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Task",
            "cwd": str(app),
            "tool_input": {
                "subagent_type": "bull:code-writer",
                "prompt": "write the Counter unit",
            },
        }
    )


def _session_start_json(app: Path) -> str:
    """The SessionStart JSON Claude Code sends when a session opens."""
    return json.dumps(
        {"hook_event_name": "SessionStart", "cwd": str(app), "source": "startup"}
    )


def _mid_build_app(bull: BullRunner, tmp_path: Path, env: dict[str, str]) -> Path:
    """A tally app mid-build: Store done, Counter in progress at unit 1 (tests written)."""
    app = new_tally_app(bull, tmp_path, env, stage=5)
    bull_ok(bull, "status", "module", "Store", "in_progress", cwd=app)
    for state in ("tests", "code", "done"):
        bull_ok(bull, "status", "unit", "Store", "1", state, cwd=app)
    bull_ok(bull, "status", "module", "Store", "done", cwd=app)
    git(app, env, "switch", "-c", "module/Counter")
    bull_ok(bull, "status", "module", "Counter", "in_progress", cwd=app)
    bull_ok(bull, "status", "unit", "Counter", "1", "tests", cwd=app)
    commit_all(app, env, "test(Counter): unit 1 tests")
    return app


def test_pause_on_usage_and_resume_ends_at_the_same_next_unit(
    bull: BullRunner, tmp_path: Path, journey_env: dict[str, str]
) -> None:
    app = _mid_build_app(bull, tmp_path, journey_env)
    next_before = bull_ok(bull, "status", "next", cwd=app).stdout.strip()
    assert "unit 1" in next_before

    # The status line records 5-hour usage at 92%.
    line = bull("statusline", cwd=app, stdin=_statusline_json(app, 92.0, context=38.0))
    assert line.returncode == 0, line.stdout + line.stderr
    assert line.stdout.strip().endswith("ctx 38%"), line.stdout
    usage = json.loads((app / ".bull" / "usage.json").read_text())
    assert usage["five_hour"] == 92.0
    assert usage["weekly"] == 20.0

    # An input with no context figure shows `ctx –`, never the saved 38%.
    for ctx in (None, "absent"):
        bare = bull(
            "statusline", cwd=app, stdin=_statusline_json(app, 92.0, context=ctx)
        )
        assert bare.returncode == 0, bare.stdout + bare.stderr
        assert bare.stdout.strip().endswith("ctx –"), bare.stdout
        assert "38%" not in bare.stdout
    assert json.loads((app / ".bull" / "usage.json").read_text())["five_hour"] == 92.0

    check = bull_ok(bull, "status", "usage-check", cwd=app)
    assert check.stdout.startswith("PAUSE")
    assert "92%" in check.stdout
    as_json = json.loads(
        bull_ok(bull, "status", "usage-check", "--json", cwd=app).stdout
    )
    assert as_json["verdict"] == "PAUSE"
    assert as_json["resets_at"]

    # The next subagent launch is blocked with the same reason.
    blocked = bull("hook", "before-agent", cwd=app, stdin=_before_agent_json(app))
    assert blocked.returncode == 2
    assert "92%" in blocked.stderr

    # Dana commits and pauses.
    commit_all(app, journey_env, "chore: pause (usage)")
    bull_ok(bull, "status", "pause", "usage", cwd=app)
    paused = json.loads((app / ".bull" / "status.json").read_text())["pause"]
    assert paused["reason"] == "usage"
    assert paused["unit"] == "Counter unit 1"
    assert "paused (usage)" in bull_ok(bull, "status", "next", cwd=app).stdout

    # Fresh session: the session-start hook prints the stage, the paused unit and how to resume.
    session = bull("hook", "session-start", cwd=app, stdin=_session_start_json(app))
    assert session.returncode == 0, session.stdout + session.stderr
    assert "stage 5" in session.stdout
    assert "Counter unit 1" in session.stdout
    assert "/bull:resume" in session.stdout

    # Usage is back at 10%.
    assert (
        bull("statusline", cwd=app, stdin=_statusline_json(app, 10.0)).returncode == 0
    )
    ok = bull_ok(bull, "status", "usage-check", cwd=app)
    assert ok.stdout.startswith("OK")
    allowed = bull("hook", "before-agent", cwd=app, stdin=_before_agent_json(app))
    assert allowed.returncode == 0

    bull_ok(bull, "status", "resume", cwd=app)
    assert json.loads((app / ".bull" / "status.json").read_text())["pause"] is None

    # Ends when `bull status next` names the same unit as before the pause.
    assert bull_ok(bull, "status", "next", cwd=app).stdout.strip() == next_before


def test_usage_check_with_no_usage_data_is_unknown_and_agent_launches_are_allowed(
    bull: BullRunner, tmp_path: Path, journey_env: dict[str, str]
) -> None:
    app = new_tally_app(bull, tmp_path, journey_env)
    assert not (app / ".bull" / "usage.json").exists()

    check = bull("status", "usage-check", cwd=app)
    assert check.returncode == 0
    assert check.stdout.startswith("UNKNOWN")
    assert "no usage data" in check.stdout

    launch = bull("hook", "before-agent", cwd=app, stdin=_before_agent_json(app))
    assert launch.returncode == 0, launch.stdout + launch.stderr  # allowed, not blocked
    assert launch.stdout.strip() == ""
    assert "usage unknown" in launch.stderr.lower()  # the warning reaches the user
