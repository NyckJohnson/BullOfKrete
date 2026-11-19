"""Journey 11: an app written by a newer bull is refused, not misread."""

from __future__ import annotations

import json
from pathlib import Path

from tests.journey.conftest import (
    BullRunner,
    bull_ok,
    git_out,
    new_tally_app,
)

UPGRADE = "this app's files are format 2; this bull reads format 1: upgrade bull"


def _make_newer(app: Path) -> str:
    """Rewrite ``.bull/status.json`` with ``format`` 2; return the original text."""
    path = app / ".bull" / "status.json"
    original = path.read_text(encoding="utf-8")
    data = json.loads(original)
    data["format"] = 2
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return original


def test_a_newer_format_stops_every_command_but_doctor_and_version_until_restored(
    bull: BullRunner, tmp_path: Path, journey_env: dict[str, str]
) -> None:
    app = new_tally_app(bull, tmp_path, journey_env, stage=5)
    original = _make_newer(app)

    for args in (
        ("status",),
        ("status", "next"),
        ("config", "show"),
        ("gates", "Store", "--fast"),
        ("api", "Store", "--check"),
        ("feature", "list"),
        ("migrate",),
    ):
        stopped = bull(*args, cwd=app)
        assert stopped.returncode != 0, args
        assert UPGRADE in stopped.stdout + stopped.stderr, args

    version = bull("--version", cwd=app)
    assert version.returncode == 0
    assert version.stdout.strip()
    doctor = bull("doctor", cwd=app)
    assert UPGRADE not in doctor.stdout + doctor.stderr
    assert "uv" in doctor.stdout

    (app / ".bull" / "status.json").write_text(original, encoding="utf-8")
    assert bull("status", cwd=app).returncode == 0
    assert bull("config", "show", cwd=app).returncode == 0


def test_migrate_on_a_current_app_says_already_current_and_commits_nothing(
    bull: BullRunner, tmp_path: Path, journey_env: dict[str, str]
) -> None:
    app = new_tally_app(bull, tmp_path, journey_env, stage=5)
    head = git_out(app, journey_env, "rev-parse", "HEAD")

    done = bull_ok(bull, "migrate", cwd=app)
    assert "already format 1" in done.stdout
    assert git_out(app, journey_env, "rev-parse", "HEAD") == head
    assert git_out(app, journey_env, "status", "--porcelain") == ""
