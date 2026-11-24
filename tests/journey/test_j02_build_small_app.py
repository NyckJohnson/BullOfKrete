"""Journey 2: build a small app end to end with the fixture stack."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tests.journey.conftest import (
    TALLY_MEMO,
    TALLY_MODULE_WORK,
    TALLY_SKELETON,
    BullRunner,
    bull_ok,
    commit_all,
    git,
    git_out,
    new_tally_app,
    tag_checkpoint,
    write_files,
)


def _status(bull: BullRunner, app: Path) -> dict[str, Any]:
    loaded = json.loads(bull_ok(bull, "status", "--json", cwd=app).stdout)
    assert isinstance(loaded, dict)
    return loaded


def _modules(status: dict[str, Any]) -> list[dict[str, Any]]:
    modules = status["modules"]
    assert isinstance(modules, list)
    return modules


def _unit_states(status: dict[str, Any], module: str) -> list[str]:
    for entry in _modules(status):
        if entry["name"] == module:
            return [str(unit["state"]) for unit in entry["units"]]
    raise AssertionError(f"no module {module}")


def _build_module(
    bull: BullRunner, app: Path, env: dict[str, str], module: str, branch: str
) -> None:
    git(app, env, "switch", "-c", branch, "main")
    bull_ok(bull, "status", "module", module, "in_progress", cwd=app)
    bull_ok(bull, "status", "unit", module, "1", "tests", cwd=app)
    # test-writer's work
    work = TALLY_MODULE_WORK[module]
    write_files(app, {k: v for k, v in work.items() if k.startswith("tests/")})
    commit_all(app, env, f"test({module}): unit 1 tests")
    # code-writer's work, then the fast gates
    write_files(app, {k: v for k, v in work.items() if k.startswith("src/")})
    fast = bull_ok(bull, "gates", module, "--fast", cwd=app)
    assert "tests" in fast.stdout
    bull_ok(bull, "status", "unit", module, "1", "code", cwd=app)
    bull_ok(bull, "status", "unit", module, "1", "done", cwd=app)
    commit_all(app, env, f"feat({module}): unit 1")
    assert _unit_states(_status(bull, app), module) == ["done"]
    # coverage triage report is clean
    report = bull_ok(bull, "gates", module, "--coverage-report", cwd=app)
    assert "coverage clean" in report.stdout
    # the full gates record a pass for the branch head
    head = git_out(app, env, "rev-parse", "HEAD")
    full = bull_ok(bull, "gates", module, cwd=app)
    assert "not recorded" not in full.stdout
    assert (app / ".bull" / "passes" / f"{head}.json").is_file()
    # merge, then the after-merge gates record without rerunning
    git(app, env, "switch", "main")
    git(app, env, "merge", "--no-ff", "-m", f"Merge {branch}", branch)
    merged = bull_ok(bull, "gates", "--after-merge", branch, cwd=app)
    assert "merge holds the gated code" in merged.stdout
    merge_sha = git_out(app, env, "rev-parse", "HEAD")
    assert (app / ".bull" / "passes" / f"{merge_sha}.json").is_file()
    # snapshot, module done, tag
    bull_ok(bull, "api", module, "--write", cwd=app)
    bull_ok(bull, "status", "module", module, "done", cwd=app)
    commit_all(app, env, f"chore: {module} done")
    tag_checkpoint(bull, app, env, f"done/{module}")


def test_build_a_small_app_end_to_end_ends_with_every_unit_done_and_every_tag(
    bull: BullRunner, tmp_path: Path, journey_env: dict[str, str]
) -> None:
    env = journey_env
    app = tmp_path / "tally"
    bull_ok(bull, "init", str(app), cwd=tmp_path)

    # Stage 1 to 6 steps up to the skeleton.
    selected = bull_ok(bull, "stack", "select", "fixture", cwd=app)
    assert "fixture" in selected.stdout
    assert 'stack = "fixture"' in (app / ".bull/config.toml").read_text()
    bull_ok(bull, "status", "stage", "1", cwd=app)
    bull_ok(bull, "status", "stage", "2", cwd=app)
    write_files(app, {"docs/outline.md": TALLY_MEMO})
    commit_all(app, env, "docs: outline memo")
    bull_ok(bull, "status", "checkpoint", "outline-approved", cwd=app)
    tag_checkpoint(bull, app, env, "outline-approved")
    bull_ok(bull, "status", "init-modules", cwd=app)
    status = _status(bull, app)
    modules = _modules(status)
    assert [m["name"] for m in modules] == ["Store", "Counter"]
    assert modules[1]["depends"] == ["Store"]

    # Setup: stack check fails until fixture.toml exists, then passes.
    assert bull("stack", "check", cwd=app).returncode != 0
    write_files(app, {"fixture.toml": ""})
    check = bull_ok(bull, "stack", "check", cwd=app)
    assert "fixture.toml present" in check.stdout
    bull_ok(bull, "status", "checkpoint", "setup", cwd=app)
    commit_all(app, env, "chore: setup")
    tag_checkpoint(bull, app, env, "setup")
    bull_ok(bull, "status", "stage", "3", cwd=app)

    # Skeleton: the skeleton-builder's files, snapshots, gates pass.
    write_files(app, TALLY_SKELETON)
    for module in ("Store", "Counter"):
        bull_ok(bull, "api", module, "--write", cwd=app)
        assert (app / "docs" / "api" / f"{module}.md").is_file()
    commit_all(app, env, "chore: skeleton")
    skeleton_gates = bull_ok(bull, "gates", "--all", cwd=app)
    assert "not recorded" not in skeleton_gates.stdout
    tag_checkpoint(bull, app, env, "skeleton")
    bull_ok(bull, "status", "checkpoint", "skeleton", cwd=app)
    bull_ok(bull, "status", "stage", "4", cwd=app)
    bull_ok(bull, "status", "checkpoint", "ui-approved", cwd=app)
    commit_all(app, env, "chore: ui approved")
    tag_checkpoint(bull, app, env, "ui-approved")
    bull_ok(bull, "status", "stage", "5", cwd=app)
    commit_all(app, env, "chore: stage 5")

    # Stage 5: each module in build order.
    branch = bull_ok(bull, "status", "ref", "module", "Store", cwd=app).stdout.strip()
    assert branch == "module/Store"
    _build_module(bull, app, env, "Store", branch)
    assert bull_ok(bull, "status", "ref", "base", cwd=app).stdout.strip() == "main"
    _build_module(bull, app, env, "Counter", "module/Counter")

    # Stage 6: all gates, then acceptance.
    nxt = bull_ok(bull, "status", "next", cwd=app).stdout
    assert "gates --all" in nxt
    final = bull_ok(bull, "gates", "--all", cwd=app)
    assert "not recorded" not in final.stdout
    bull_ok(bull, "status", "stage", "6", cwd=app)
    bull_ok(bull, "status", "checkpoint", "app-accepted", cwd=app)
    commit_all(app, env, "chore: app accepted")
    tag_checkpoint(bull, app, env, "app-accepted")

    # Ends: every unit done and every checkpoint and module tag listed.
    final_status = _status(bull, app)
    assert final_status["stage"] == 6
    assert final_status["units_done"] == final_status["units_total"] == 2
    assert final_status["checkpoints"] == [
        "outline-approved",
        "setup",
        "skeleton",
        "ui-approved",
        "app-accepted",
    ]
    tags = json.loads(bull_ok(bull, "status", "tags", "--json", cwd=app).stdout)
    for expected in (
        "outline-approved",
        "setup",
        "skeleton",
        "ui-approved",
        "done/Store",
        "done/Counter",
        "app-accepted",
    ):
        assert expected in tags
    # A finished module's tag never shares its branch's name.
    for module in ("Store", "Counter"):
        tag = bull_ok(
            bull, "status", "ref", "tag", f"done/{module}", cwd=app
        ).stdout.strip()
        branch_name = bull_ok(
            bull, "status", "ref", "module", module, cwd=app
        ).stdout.strip()
        assert tag == f"done/{module}"
        assert tag != branch_name
        assert git(app, env, "tag", "--list", tag).stdout.strip() == tag
        assert git(app, env, "tag", "--list", branch_name).stdout.strip() == ""
    assert git_out(app, env, "status", "--porcelain") == ""


def test_starting_a_module_before_its_dependency_is_done_is_refused_naming_it(
    bull: BullRunner, tmp_path: Path, journey_env: dict[str, str]
) -> None:
    app = new_tally_app(bull, tmp_path, journey_env)
    before = (app / ".bull/status.json").read_bytes()
    result = bull("status", "module", "Counter", "in_progress", cwd=app)
    assert result.returncode == 1
    assert "Store" in result.stdout + result.stderr
    assert (app / ".bull/status.json").read_bytes() == before


def test_fourth_attempt_blocks_the_unit_until_it_is_unblocked(
    bull: BullRunner, tmp_path: Path, journey_env: dict[str, str]
) -> None:
    app = new_tally_app(bull, tmp_path, journey_env)
    bull_ok(bull, "status", "module", "Store", "in_progress", cwd=app)
    for state in ("tests", "code", "done"):
        bull_ok(bull, "status", "unit", "Store", "1", state, cwd=app)
    bull_ok(bull, "status", "module", "Store", "done", cwd=app)
    bull_ok(bull, "status", "module", "Counter", "in_progress", cwd=app)
    bull_ok(bull, "status", "unit", "Counter", "1", "tests", cwd=app)

    # Attempts start at 1; two more are allowed, the next one hits the limit of 3.
    bull_ok(bull, "status", "attempt", "Counter", "1", cwd=app)
    bull_ok(bull, "status", "attempt", "Counter", "1", cwd=app)
    refused = bull("status", "attempt", "Counter", "1", cwd=app)
    assert refused.returncode == 1
    assert "blocked after 3 attempts" in refused.stdout + refused.stderr

    status = _status(bull, app)
    assert _unit_states(status, "Counter") == ["blocked"]
    nxt = bull_ok(bull, "status", "next", cwd=app).stdout
    assert "blocked" in nxt
    # A blocked unit takes no state change until unblocked.
    assert bull("status", "unit", "Counter", "1", "code", cwd=app).returncode == 1

    bull_ok(bull, "status", "unblock", "Counter", "1", cwd=app)
    status = _status(bull, app)
    assert _unit_states(status, "Counter") == ["tests"]
    counter = next(m for m in _modules(status) if m["name"] == "Counter")
    assert counter["units"][0]["attempts"] == 1
