"""Journey 10: settings are layered, validated, and edited with ``bull config``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tests.journey.conftest import BullRunner, bull_ok, new_tally_app, write_files


def _status(bull: BullRunner, app: Path) -> dict[str, Any]:
    loaded = json.loads(bull_ok(bull, "status", "--json", cwd=app).stdout)
    assert isinstance(loaded, dict)
    return loaded


def _store_attempts(bull: BullRunner, app: Path) -> int:
    modules = {m["name"]: m for m in _status(bull, app)["modules"]}
    attempts = modules["Store"]["units"][0]["attempts"]
    assert isinstance(attempts, int)
    return attempts


def test_settings_set_in_the_app_and_user_layers_allow_a_fourth_attempt(
    bull: BullRunner, tmp_path: Path, journey_env: dict[str, str], journey_home: Path
) -> None:
    app = new_tally_app(bull, tmp_path, journey_env, stage=5)
    write_files(
        journey_home,
        {".config/bull/config.toml": 'format = 1\n[models]\nreviewer = "opus"\n'},
    )
    bull_ok(bull, "status", "module", "Store", "in_progress", cwd=app)
    bull_ok(bull, "status", "unit", "Store", "1", "tests", cwd=app)

    set_done = bull_ok(bull, "config", "set", "max_attempts", "5", cwd=app)
    assert "max_attempts" in set_done.stdout and "5" in set_done.stdout
    assert "max_attempts = 5" in (app / ".bull" / "config.toml").read_text()

    shown = bull_ok(bull, "config", "show", cwd=app).stdout
    assert "max_attempts = 5 (app)" in shown
    assert "review_mode = combined (bull default)" in shown
    assert "models.reviewer = opus (user)" in shown

    as_json = json.loads(bull_ok(bull, "config", "show", "--json", cwd=app).stdout)
    assert "max_attempts" in json.dumps(as_json)

    # Attempts start at 1; the third retry makes the 4th attempt, allowed under max_attempts 5.
    assert _store_attempts(bull, app) == 1
    for expected in (2, 3, 4):
        done = bull("status", "attempt", "Store", "1", cwd=app)
        assert done.returncode == 0, done.stdout + done.stderr
        assert _store_attempts(bull, app) == expected


def test_a_non_integer_max_attempts_is_refused_naming_the_expected_type(
    bull: BullRunner, tmp_path: Path, journey_env: dict[str, str]
) -> None:
    app = new_tally_app(bull, tmp_path, journey_env, stage=5)
    before = (app / ".bull" / "config.toml").read_text()

    refused = bull("config", "set", "max_attempts", "many", cwd=app)
    assert refused.returncode != 0
    assert "max_attempts must be an integer" in refused.stdout + refused.stderr
    assert (app / ".bull" / "config.toml").read_text() == before


def test_an_unknown_key_in_config_toml_makes_status_fail_naming_file_line_and_key(
    bull: BullRunner, tmp_path: Path, journey_env: dict[str, str]
) -> None:
    app = new_tally_app(bull, tmp_path, journey_env, stage=5)
    config = app / ".bull" / "config.toml"
    config.write_text(config.read_text() + "\nmax_attemps = 4\n", encoding="utf-8")
    line = config.read_text().splitlines().index("max_attemps = 4") + 1

    failed = bull("status", cwd=app)
    assert failed.returncode != 0
    message = failed.stdout + failed.stderr
    assert "config.toml" in message
    assert str(line) in message
    assert "max_attemps" in message
    assert "unknown setting" in message
