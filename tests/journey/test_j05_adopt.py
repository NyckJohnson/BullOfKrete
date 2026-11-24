"""Journey 5: adopt an existing app, from ``bull init --adopt .`` to ``bull adopt finish``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tests.journey.conftest import (
    BullRunner,
    bull_ok,
    commit_all,
    git,
    git_out,
    new_legacy_app,
    tag_checkpoint,
    write_files,
)

ADOPT_MEMO = """# Legacy counter outline

## Purpose
A small counter built before bull.

## User journeys
1. **Count** — count up.

## Build order
1. Counter (depends on: none)

## Modules

### Counter
- Purpose: counts up.
- Depends on: none
- Files: Contracts/counter.fx, counter.fx
- Legacy files: src/counter.fx
- Legacy tests: tests/counter_test.test
- Callers to repoint: src/main.fx
- Behavior spec:
  - increments by one
- Reference tests: none
- Contract: pending

## Legacy code
- App shell: src/main.fx
- App shell tests: tests/journey/

## Decisions log
"""

MODULE_FILES: dict[str, str] = {
    "src/Modules/Counter/Contracts/counter.fx": (
        "# counter contract\npub Counter\npub increment\n"
    ),
    "src/Modules/Counter/counter.fx": ("# counter\non increment: value = value + 1\n"),
}
MODULE_TESTS: dict[str, str] = {
    "tests/Counter/counter.test": (
        "# counter behaviors\npass increments\n"
        "covers src/Modules/Counter/counter.fx:2\n"
        "covers src/Modules/Counter/Contracts/counter.fx:2-3\n"
    ),
}


def _status(bull: BullRunner, app: Path) -> dict[str, Any]:
    loaded = json.loads(bull_ok(bull, "status", "--json", cwd=app).stdout)
    assert isinstance(loaded, dict)
    return loaded


def _adopt_up_to_switch_over(bull: BullRunner, app: Path, env: dict[str, str]) -> None:
    """Run an adoption that has started to the end of the module's unit 1."""
    # Stage 2: the memo; stage setup: the stack check.
    bull_ok(bull, "status", "stage", "2", cwd=app)
    write_files(app, {"docs/outline.md": ADOPT_MEMO})
    commit_all(app, env, "docs: adoption memo")
    bull_ok(bull, "status", "checkpoint", "outline-approved", cwd=app)
    tag_checkpoint(bull, app, env, "outline-approved")
    bull_ok(bull, "status", "init-modules", cwd=app)
    bull_ok(bull, "stack", "check", cwd=app)
    bull_ok(bull, "status", "checkpoint", "setup", cwd=app)
    tag_checkpoint(bull, app, env, "setup")
    commit_all(app, env, "chore: setup")

    # Stage 3: baseline journeys pass against the app as it is.
    bull_ok(bull, "status", "stage", "3", cwd=app)
    baseline = bull_ok(bull, "gates", "--journeys", cwd=app)
    assert "journeys" in baseline.stdout
    bull_ok(bull, "status", "checkpoint", "baseline", cwd=app)
    commit_all(app, env, "chore: baseline")
    tag_checkpoint(bull, app, env, "baseline")

    # Stage 4: scaffold the module's contract.
    bull_ok(bull, "status", "stage", "4", cwd=app)
    write_files(app, {k: v for k, v in MODULE_FILES.items() if "Contracts" in k})
    write_files(
        app,
        {
            "src/Modules/Counter/counter.fx": "# counter\n",
            "tests/Counter/counter.test": "# empty\n",
        },
    )
    bull_ok(bull, "api", "Counter", "--write", cwd=app)
    commit_all(app, env, "chore: scaffold")
    bull_ok(bull, "status", "checkpoint", "scaffold", cwd=app)
    commit_all(app, env, "chore: scaffold approved")
    tag_checkpoint(bull, app, env, "scaffold")

    # Stage 5: the module, unit 1.
    bull_ok(bull, "status", "stage", "5", cwd=app)
    commit_all(app, env, "chore: stage 5")
    git(app, env, "switch", "-c", "adopt/module/Counter", "adopt/main")
    bull_ok(bull, "status", "module", "Counter", "in_progress", cwd=app)
    bull_ok(bull, "status", "unit", "Counter", "1", "tests", cwd=app)
    write_files(app, MODULE_TESTS)
    commit_all(app, env, "test(Counter): unit 1 tests")
    write_files(app, MODULE_FILES)
    bull_ok(bull, "gates", "Counter", "--fast", cwd=app)
    bull_ok(bull, "status", "unit", "Counter", "1", "code", cwd=app)
    bull_ok(bull, "status", "unit", "Counter", "1", "done", cwd=app)
    commit_all(app, env, "feat(Counter): unit 1")


def _switch_over(
    bull: BullRunner, app: Path, env: dict[str, str], delete_legacy: bool
) -> None:
    """The module's switch-over unit, then merge into ``adopt/main`` and the final stage."""
    nxt = bull_ok(bull, "status", "next", cwd=app).stdout
    assert "switch-over" in nxt
    bull_ok(bull, "status", "unit", "Counter", "2", "tests", cwd=app)
    # code-writer: repoint callers, delete replaced legacy code; test-writer: delete old tests.
    write_files(app, {"src/main.fx": "# entry point\nuse Counter\n"})
    if delete_legacy:
        (app / "src/counter.fx").unlink()
        (app / "tests/counter_test.test").unlink()
    bull_ok(bull, "gates", "Counter", "--fast", cwd=app)
    bull_ok(bull, "status", "unit", "Counter", "2", "code", cwd=app)
    bull_ok(bull, "status", "unit", "Counter", "2", "done", cwd=app)
    commit_all(app, env, "feat(Counter): switch-over")
    report = bull_ok(bull, "gates", "Counter", "--coverage-report", cwd=app)
    assert "coverage clean" in report.stdout
    full = bull_ok(bull, "gates", "Counter", cwd=app)
    assert "journeys" in full.stdout
    git(app, env, "switch", "adopt/main")
    git(app, env, "merge", "--no-ff", "-m", "Merge Counter", "adopt/module/Counter")
    bull_ok(bull, "gates", "--after-merge", "adopt/module/Counter", cwd=app)
    bull_ok(bull, "api", "Counter", "--write", cwd=app)
    bull_ok(bull, "status", "module", "Counter", "done", cwd=app)
    commit_all(app, env, "chore: Counter adopted")
    tag_checkpoint(bull, app, env, "done/Counter")

    # Stage 6.
    bull_ok(bull, "gates", "--all", cwd=app)
    bull_ok(bull, "status", "stage", "6", cwd=app)
    commit_all(app, env, "chore: stage 6")


def test_adopt_an_existing_app_ends_as_an_ordinary_accepted_app(
    bull: BullRunner, tmp_path: Path, journey_env: dict[str, str]
) -> None:
    env = journey_env
    app = new_legacy_app(tmp_path, env)
    original = git_out(app, env, "rev-parse", "main")

    # Detection, config, commit and the switch to adopt/main.
    detect = bull_ok(bull, "stack", "detect", cwd=app)
    assert "stack: fixture" in detect.stdout
    started = bull_ok(bull, "init", "--adopt", ".", cwd=app)
    assert "fixture" in started.stdout
    config = (app / ".bull/config.toml").read_text()
    assert 'stack = "fixture"' in config
    assert git_out(app, env, "branch", "--show-current") == "adopt/main"
    subjects = git_out(app, env, "log", "--format=%s", "main").splitlines()
    assert "chore: start adoption" in subjects
    assert "chore: bull init" in subjects
    assert "add readme" in subjects  # the app's own history is kept
    git(app, env, "merge-base", "--is-ancestor", original, "main")
    assert git_out(app, env, "status", "--porcelain") == ""
    status = _status(bull, app)
    assert status["adoption"] == {"stage": 1, "checkpoints": []}
    assert status["mode"] == "adopt"

    # The legacy check names what still has to be replaced.
    left = bull_ok(bull, "adopt", "legacy", "--json", cwd=app)
    assert "src/counter.fx" in left.stdout

    _adopt_up_to_switch_over(bull, app, env)
    _switch_over(bull, app, env, delete_legacy=True)

    legacy = bull_ok(bull, "adopt", "legacy", cwd=app)
    assert "Nothing left to replace" in legacy.stdout
    bull_ok(bull, "adopt", "finish", cwd=app)
    assert git_out(app, env, "log", "-1", "--format=%s") == "chore: adoption finished"
    tag_checkpoint(bull, app, env, "adopted")

    final = _status(bull, app)
    assert final["adoption"] is None
    assert final["mode"] == "app"
    assert final["stage"] == 6
    assert "app-accepted" in final["checkpoints"]
    assert [m["state"] for m in final["modules"]] == ["done"]
    tags = json.loads(bull_ok(bull, "status", "tags", "--json", cwd=app).stdout)
    for expected in (
        "adopt/baseline",
        "adopt/scaffold",
        "adopt/done/Counter",
        "adopted",
    ):
        assert expected in tags
    assert not (app / "src/counter.fx").exists()
    assert git_out(app, env, "status", "--porcelain") == ""


def test_adopt_finish_is_refused_while_a_listed_legacy_file_still_exists(
    bull: BullRunner, tmp_path: Path, journey_env: dict[str, str]
) -> None:
    env = journey_env
    app = new_legacy_app(tmp_path, env)
    bull_ok(bull, "init", "--adopt", ".", cwd=app)
    _adopt_up_to_switch_over(bull, app, env)
    _switch_over(bull, app, env, delete_legacy=False)
    before = (app / ".bull/status.json").read_bytes()

    refused = bull("adopt", "finish", cwd=app)
    assert refused.returncode == 1
    assert "src/counter.fx" in refused.stdout + refused.stderr
    assert (app / ".bull/status.json").read_bytes() == before
    assert _status(bull, app)["adoption"] is not None

    # Once the file is removed the adoption can finish.
    (app / "src/counter.fx").unlink()
    (app / "tests/counter_test.test").unlink()
    commit_all(app, env, "chore: remove legacy files")
    bull_ok(bull, "adopt", "finish", cwd=app)
    assert _status(bull, app)["adoption"] is None
