"""Journey 1: install and init (docs/outline.md, User journeys, journey 1)."""

from __future__ import annotations

import json
from pathlib import Path

from tests.journey.conftest import FAKE_CLAUDE_VERSION, BullRunner, git_out


def test_install_and_init_ends_at_stage_zero_next_discuss(
    bull: BullRunner, tmp_path: Path, journey_env: dict[str, str]
) -> None:
    # bull doctor: uv, git and claude found with versions; stacks listed.
    doctor = bull("doctor")
    assert doctor.returncode == 0, doctor.stdout + doctor.stderr
    for tool in ("uv", "git"):
        assert f"{tool} found" in doctor.stdout
    assert FAKE_CLAUDE_VERSION in doctor.stdout
    assert "python" in doctor.stdout
    assert "ios" in doctor.stdout
    assert "python_cli" in doctor.stdout

    report = json.loads(bull("doctor", "--json").stdout)
    assert report["ok"] is True
    assert {stack["name"] for stack in report["stacks"]} >= {"ios", "python_cli"}

    # bull init ~/apps/tally creates the whole app.
    app = tmp_path / "apps" / "tally"
    init = bull("init", str(app))
    assert init.returncode == 0, init.stdout + init.stderr
    assert app.is_dir()
    assert git_out(app, journey_env, "branch", "--show-current") == "main"
    for rel in (
        ".bull/config.toml",
        ".bull/status.json",
        ".bull/backlog.json",
        ".gitignore",
        ".claude/settings.json",
        "CLAUDE.md",
    ):
        assert (app / rel).is_file(), rel
    assert "format = 1" in (app / ".bull/config.toml").read_text()
    status_file = json.loads((app / ".bull/status.json").read_text())
    assert status_file["stage"] == 0
    assert status_file["kind"] == "app"
    gitignore = (app / ".gitignore").read_text()
    for line in (
        ".bull/usage.json",
        ".bull/events.jsonl",
        ".bull/passes/",
        ".bull/plugin/",
    ):
        assert line in gitignore
    settings = json.loads((app / ".claude/settings.json").read_text())
    assert settings["statusLine"]["command"] == "bull statusline"
    assert "@.bull/plugin/orchestrator.md" in (app / "CLAUDE.md").read_text()

    # One commit, clean tree, state files tracked.
    assert git_out(app, journey_env, "log", "--format=%s") == "chore: bull init"
    assert git_out(app, journey_env, "status", "--porcelain") == ""
    tracked = git_out(app, journey_env, "ls-files").splitlines()
    assert ".bull/status.json" in tracked
    assert ".bull/usage.json" not in tracked

    # bull open --print-command only prints the claude command line.
    opened = bull("open", str(app), "--print-command")
    assert opened.returncode == 0, opened.stdout + opened.stderr
    line = opened.stdout.strip()
    assert line.startswith("claude")
    assert "--plugin-dir" in line
    plugin_dir = app / ".bull" / "plugin"
    assert str(plugin_dir) in line
    assert (plugin_dir / ".claude-plugin" / "plugin.json").is_file()
    assert (plugin_dir / "orchestrator.md").is_file()
    assert (plugin_dir / "hooks" / "hooks.json").is_file()

    # Ends: bull status says stage 0, next /bull:discuss.
    status = bull("status", cwd=app)
    assert status.returncode == 0, status.stdout + status.stderr
    assert "stage 0" in status.stdout
    assert "/bull:discuss" in status.stdout
    as_json = json.loads(bull("status", "--json", cwd=app).stdout)
    assert as_json["stage"] == 0
    assert "/bull:discuss" in as_json["next"]


def test_init_on_a_non_empty_folder_that_is_not_an_app_refuses_and_mentions_adopt(
    bull: BullRunner, tmp_path: Path
) -> None:
    folder = tmp_path / "existing"
    folder.mkdir()
    (folder / "notes.txt").write_text("mine\n")
    result = bull("init", str(folder))
    assert result.returncode == 1
    assert "--adopt" in result.stdout + result.stderr
    assert not (folder / ".bull").exists()
    assert not (folder / ".git").exists()
    assert (folder / "notes.txt").read_text() == "mine\n"


def test_init_on_an_existing_app_relinks_without_touching_state_files(
    bull: BullRunner, tmp_path: Path, journey_env: dict[str, str]
) -> None:
    app = tmp_path / "tally"
    assert bull("init", str(app)).returncode == 0
    state = {
        rel: (app / rel).read_bytes()
        for rel in (".bull/status.json", ".bull/backlog.json", ".bull/config.toml")
    }

    claude_md = app / "CLAUDE.md"
    claude_md.write_text(claude_md.read_text() + "# my own notes\n")
    settings_path = app / ".claude" / "settings.json"
    settings_path.unlink()

    relink = bull("init", ".", cwd=app)
    assert relink.returncode == 0, relink.stdout + relink.stderr
    assert "relink" in relink.stdout.lower()
    for rel, before in state.items():
        assert (app / rel).read_bytes() == before, rel
    assert settings_path.is_file()
    assert "# my own notes" in claude_md.read_text()
    assert "<!-- bull:begin -->" in claude_md.read_text()
    assert git_out(app, journey_env, "status", "--porcelain") == ""


def test_init_inside_a_subfolder_of_an_app_refuses_before_creating_anything(
    bull: BullRunner, tmp_path: Path
) -> None:
    app = tmp_path / "tally"
    assert bull("init", str(app)).returncode == 0
    (app / "sub").mkdir()
    result = bull("init", "sub/deeper", cwd=app)
    assert result.returncode == 1
    assert "inside the bull app" in result.stdout + result.stderr
    assert "bull init ." in result.stdout + result.stderr
    assert not (app / "sub" / "deeper").exists()
    assert not (app / "sub" / ".bull").exists()


def test_doctor_without_claude_on_path_exits_nonzero_and_names_the_fix(
    bull: BullRunner, tools_bin: Path, journey_env: dict[str, str]
) -> None:
    env = dict(journey_env, PATH=f"{tools_bin}:/usr/bin:/bin")
    result = bull("doctor", env=env)
    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "claude" in output
    assert "install Claude Code" in output
    assert "fix" in output.lower()
    # Core tools that are present still report as found.
    assert "uv found" in output
    assert "git found" in output
