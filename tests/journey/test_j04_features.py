"""Journey 4: features from a file; build one, abandon one."""

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
    new_accepted_tally_app,
    new_legacy_app,
    new_tally_app,
    write_files,
)

IDEAS = """# Ideas

## Reset button
Add a reset button that sets the counter back to zero.

## Dark mode
Show the counter on a dark background.

## Export history
Export every count as a file.
"""

FEATURE_MEMO_LINES = (
    "- Changes (reset-button): Contracts/counter.fx, counter.fx\n"
    "- Contract changes (reset-button): Counter gains a reset operation\n"
)


def _backlog(app: Path) -> dict[str, dict[str, Any]]:
    loaded = json.loads((app / ".bull/backlog.json").read_text())
    return {item["slug"]: item for item in loaded["items"]}


def _status(bull: BullRunner, app: Path) -> dict[str, Any]:
    loaded = json.loads(bull_ok(bull, "status", "--json", cwd=app).stdout)
    assert isinstance(loaded, dict)
    return loaded


def _queue_ideas(
    bull: BullRunner, app: Path, env: dict[str, str], tmp_path: Path
) -> None:
    ideas = tmp_path / "ideas.md"
    ideas.write_text(IDEAS, encoding="utf-8")
    bull_ok(bull, "feature", "import", str(ideas), cwd=app)
    commit_all(app, env, "chore: queue ideas")


def test_features_from_a_file_build_one_and_abandon_one(
    bull: BullRunner, tmp_path: Path, journey_env: dict[str, str]
) -> None:
    env = journey_env
    app = new_accepted_tally_app(bull, tmp_path, env)

    # Import: three queued entries, each with a brief.
    ideas = tmp_path / "ideas.md"
    ideas.write_text(IDEAS, encoding="utf-8")
    imported = bull_ok(bull, "feature", "import", str(ideas), cwd=app)
    for slug in ("reset-button", "dark-mode", "export-history"):
        assert slug in imported.stdout
        assert (app / "docs/features" / f"{slug}.md").is_file()
    commit_all(app, env, "chore: queue ideas")
    listing = json.loads(bull_ok(bull, "feature", "list", "--json", cwd=app).stdout)
    assert [(i["position"], i["slug"], i["state"]) for i in listing] == [
        (1, "reset-button", "queued"),
        (2, "dark-mode", "queued"),
        (3, "export-history", "queued"),
    ]
    brief = (app / "docs/features/reset-button.md").read_text()
    assert brief.startswith("# Reset button")
    assert "## Agreed scope" in brief

    # Start: a commit on main, then the feature branch.
    bull_ok(bull, "feature", "start", "reset-button", cwd=app)
    assert git_out(app, env, "branch", "--show-current") == "feature/reset-button/main"
    assert "chore: start feature reset-button" in git_out(
        app, env, "log", "--format=%s", "main"
    )
    assert _backlog(app)["reset-button"]["state"] == "active"
    assert _status(bull, app)["mode"] == "feature"

    # Outline: the memo marks Counter; plan reopens only its unit.
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
    planned = bull_ok(bull, "feature", "plan", cwd=app)
    assert "Reopened Counter: unit 1" in planned.stdout
    assert "Store" not in planned.stdout
    assert "Contract changes: Counter" in planned.stdout
    states = {m["name"]: m["state"] for m in _status(bull, app)["modules"]}
    assert states == {"Store": "done", "Counter": "pending"}
    commit_all(app, env, "chore: plan reset-button")
    bull_ok(bull, "status", "checkpoint", "setup", cwd=app)
    bull_ok(bull, "status", "stage", "3", cwd=app)

    # Skeleton: the contract change applies once, pre-approved.
    write_files(
        app,
        {
            "src/Modules/Counter/Contracts/counter.fx": (
                "# counter contract\npub Counter\npub increment\npub reset\n"
                "field value: integer\n"
            ),
        },
    )
    written = bull_ok(bull, "api", "Counter", "--write", cwd=app)
    assert "wrote" in written.stdout
    assert _status(bull, app)["feature"]["applied_contracts"] == ["Counter"]
    further = {
        "src/Modules/Counter/Contracts/counter.fx": (
            "# counter contract\npub Counter\npub increment\npub reset\npub undo\n"
            "field value: integer\n"
        ),
    }
    write_files(app, further)
    assert bull("api", "Counter", "--write", cwd=app).returncode != 0
    write_files(
        app,
        {
            "src/Modules/Counter/Contracts/counter.fx": (
                "# counter contract\npub Counter\npub increment\npub reset\n"
                "field value: integer\n"
            ),
        },
    )
    bull_ok(bull, "status", "checkpoint", "skeleton", cwd=app)
    bull_ok(bull, "status", "stage", "4", cwd=app)
    bull_ok(bull, "status", "checkpoint", "ui-approved", cwd=app)
    bull_ok(bull, "status", "stage", "5", cwd=app)
    commit_all(app, env, "chore: feature skeleton")

    # Stage 5: the reopened unit runs the loop on the feature's module branch.
    module_branch = bull_ok(bull, "status", "ref", "module", "Counter", cwd=app).stdout
    module_branch = module_branch.strip()
    assert module_branch == "feature/reset-button/module/Counter"
    base = bull_ok(bull, "status", "ref", "base", cwd=app).stdout.strip()
    assert base == "feature/reset-button/main"
    git(app, env, "switch", "-c", module_branch, base)
    bull_ok(bull, "status", "module", "Counter", "in_progress", cwd=app)
    bull_ok(bull, "status", "unit", "Counter", "1", "tests", cwd=app)
    write_files(
        app,
        {
            "tests/Counter/counter.test": (
                "# counter behaviors\npass increments\ncovers src/Modules/Counter/counter.fx:2\n"
                "pass decrements\ncovers src/Modules/Counter/counter.fx:3\n"
                "pass resets\ncovers src/Modules/Counter/counter.fx:4\n"
                "covers src/Modules/Counter/Contracts/counter.fx:2-5\n"
            ),
        },
    )
    commit_all(app, env, "test(Counter): reset tests")
    write_files(
        app,
        {
            "src/Modules/Counter/counter.fx": (
                "# counter\non increment: value = value + 1\non decrement: value = value - 1\n"
                "on reset: value = 0\n"
            ),
        },
    )
    bull_ok(bull, "gates", "Counter", "--fast", cwd=app)
    bull_ok(bull, "status", "unit", "Counter", "1", "code", cwd=app)
    bull_ok(bull, "status", "unit", "Counter", "1", "done", cwd=app)
    commit_all(app, env, "feat(Counter): reset")
    bull_ok(bull, "gates", "Counter", cwd=app)
    git(app, env, "switch", base)
    git(app, env, "merge", "--no-ff", "-m", "Merge Counter", module_branch)
    bull_ok(bull, "gates", "--after-merge", module_branch, cwd=app)
    bull_ok(bull, "api", "Counter", "--write", cwd=app)
    bull_ok(bull, "status", "module", "Counter", "done", cwd=app)
    commit_all(app, env, "chore: Counter done")

    # Verify and accept on the feature track.
    bull_ok(bull, "gates", "--all", cwd=app)
    bull_ok(bull, "status", "stage", "6", cwd=app)
    bull_ok(bull, "status", "checkpoint", "accepted", cwd=app)
    accepted_tag = bull_ok(
        bull, "status", "ref", "tag", "accepted", cwd=app
    ).stdout.strip()
    assert accepted_tag == "feature/reset-button/accepted"
    commit_all(app, env, "chore: feature verified")

    # Meanwhile a fourth idea is queued on main (a separate backlog change).
    git(app, env, "switch", "main")
    bull_ok(bull, "feature", "add", "Sound effects: beep when counting", cwd=app)
    commit_all(app, env, "chore: queue sound-effects")
    git(app, env, "switch", base)
    accepted = bull_ok(bull, "feature", "accept", cwd=app)
    assert "reset-button" in accepted.stdout
    commit_all(app, env, "chore: feature accepted")

    git(app, env, "switch", "main")
    merged = git(
        app, env, "merge", "--no-ff", "-m", "Merge reset-button", base, check=False
    )
    assert merged.returncode == 0, merged.stdout + merged.stderr
    git(app, env, "tag", accepted_tag)
    assert "pub reset" in (app / "src/Modules/Counter/Contracts/counter.fx").read_text()
    backlog = _backlog(app)
    assert backlog["reset-button"]["state"] == "accepted"
    assert backlog["sound-effects"]["state"] == "queued"
    assert _status(bull, app)["feature"] is None
    assert accepted_tag in json.loads(
        bull_ok(bull, "status", "tags", "--json", cwd=app).stdout
    )

    # Start dark-mode, change her mind, abandon on main.
    bull_ok(bull, "feature", "start", "dark-mode", cwd=app)
    assert git_out(app, env, "branch", "--show-current") == "feature/dark-mode/main"
    write_files(
        app, {"src/Modules/Counter/dark.fx": "# dark mode\non dark: theme = 1\n"}
    )
    commit_all(app, env, "feat: dark mode sketch")
    git(app, env, "switch", "main")
    bull_ok(bull, "feature", "abandon", cwd=app)
    assert not (app / "src/Modules/Counter/dark.fx").exists()
    assert "dark" not in git_out(app, env, "ls-files", "src", "tests")
    assert (app / "docs/features/dark-mode.md").is_file()  # the brief is kept
    assert _backlog(app)["dark-mode"]["state"] == "abandoned"
    assert _status(bull, app)["feature"] is None
    kinds = [i["state"] for i in _backlog(app).values()]
    assert kinds.count("abandoned") == 1


def test_starting_a_second_feature_while_one_is_active_is_refused(
    bull: BullRunner, tmp_path: Path, journey_env: dict[str, str]
) -> None:
    env = journey_env
    app = new_accepted_tally_app(bull, tmp_path, env)
    _queue_ideas(bull, app, env, tmp_path)
    bull_ok(bull, "feature", "start", "reset-button", cwd=app)
    git(app, env, "switch", "main")

    refused = bull("feature", "start", "dark-mode", cwd=app)
    assert refused.returncode == 1
    assert "reset-button" in refused.stdout + refused.stderr
    assert _backlog(app)["dark-mode"]["state"] == "queued"
    assert (
        git(
            app, env, "rev-parse", "--verify", "feature/dark-mode/main", check=False
        ).returncode
        != 0
    )
    assert _status(bull, app)["feature"]["slug"] == "reset-button"


def test_starting_a_feature_before_the_app_is_accepted_is_refused(
    bull: BullRunner, tmp_path: Path, journey_env: dict[str, str]
) -> None:
    env = journey_env
    app = new_tally_app(bull, tmp_path, env, stage=5)
    bull_ok(bull, "feature", "add", "Reset button: set the counter to zero", cwd=app)
    commit_all(app, env, "chore: queue reset-button")

    refused = bull("feature", "start", "reset-button", cwd=app)
    assert refused.returncode == 1
    assert "accepted" in refused.stdout + refused.stderr
    assert git_out(app, env, "branch", "--show-current") == "main"
    assert _backlog(app)["reset-button"]["state"] == "queued"
    assert _status(bull, app)["feature"] is None


def test_starting_a_feature_during_an_adoption_is_refused_but_queuing_works(
    bull: BullRunner, tmp_path: Path, journey_env: dict[str, str]
) -> None:
    env = journey_env
    app = new_legacy_app(tmp_path, env)
    bull_ok(bull, "init", "--adopt", ".", cwd=app)
    assert _status(bull, app)["adoption"] is not None

    bull_ok(bull, "feature", "add", "Reset button: set the counter to zero", cwd=app)
    commit_all(app, env, "chore: queue reset-button")
    refused = bull("feature", "start", "reset-button", cwd=app)
    assert refused.returncode == 1
    assert "adoption" in refused.stdout + refused.stderr
    assert git_out(app, env, "branch", "--show-current") == "adopt/main"
    assert _backlog(app)["reset-button"]["state"] == "queued"
    assert _status(bull, app)["feature"] is None
