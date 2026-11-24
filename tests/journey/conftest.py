"""Shared fixtures and helpers for the end-to-end journey tests.

Every journey runs the installed ``bull`` console script as a real subprocess inside a hermetic
environment: a temporary HOME and XDG_CONFIG_HOME (so the developer's ``~/.config/bull/config.toml``
is never read), a fixed git identity, and an empty global git config.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import pytest

#: Callable type of the ``bull`` fixture: ``bull(*args, cwd=..., stdin=..., env=...)``.
BullRunner = Callable[..., "subprocess.CompletedProcess[str]"]

FAKE_CLAUDE_VERSION = "9.9.9-journey"


def bull_executable() -> str:
    """Path of the installed ``bull`` console script (PATH first, then next to the interpreter)."""
    found = shutil.which("bull")
    if found:
        return found
    candidate = Path(sys.executable).parent / "bull"
    if candidate.exists():
        return str(candidate)
    # Fall back to the venv script next to a resolved interpreter.
    return str(Path(sys.executable).resolve().parent / "bull")


def run_cmd(
    argv: Sequence[str],
    cwd: Path,
    env: Mapping[str, str],
    stdin: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run any command with an argument list in ``cwd``, capturing text output (never raises)."""
    return subprocess.run(
        list(argv),
        cwd=cwd,
        env=dict(env),
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )


def git(
    cwd: Path, env: Mapping[str, str], *args: str, check: bool = True
) -> subprocess.CompletedProcess[str]:
    """Run ``git <args>`` in ``cwd``; raise with the output when ``check`` and it fails."""
    done = run_cmd(["git", *args], cwd, env)
    if check and done.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {done.stdout}{done.stderr}")
    return done


def git_out(cwd: Path, env: Mapping[str, str], *args: str) -> str:
    """Return the stripped stdout of a successful ``git <args>``."""
    return git(cwd, env, *args).stdout.strip()


def commit_all(cwd: Path, env: Mapping[str, str], message: str) -> None:
    """Stage everything and commit with ``message`` (a no-op commit is not created)."""
    git(cwd, env, "add", "-A")
    if git(cwd, env, "status", "--porcelain").stdout.strip():
        git(cwd, env, "commit", "-q", "-m", message)


def write_files(root: Path, files: Mapping[str, str]) -> None:
    """Write ``{relative path: text}`` under ``root``, creating folders."""
    for rel, text in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


def make_fake_claude(directory: Path, version: str = FAKE_CLAUDE_VERSION) -> Path:
    """Create an executable fake ``claude`` that prints a version, inside ``directory``."""
    directory.mkdir(parents=True, exist_ok=True)
    script = directory / "claude"
    script.write_text(f'#!/bin/sh\necho "claude {version}"\n', encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return script


@pytest.fixture
def journey_home(tmp_path: Path) -> Path:
    """A temporary HOME directory for the journey."""
    home = tmp_path / "home"
    home.mkdir()
    return home


@pytest.fixture
def tools_bin(tmp_path: Path) -> Path:
    """A folder holding only symlinks to the real ``uv`` and ``git`` (no ``claude``)."""
    folder = tmp_path / "tools-bin"
    folder.mkdir()
    for tool in ("uv", "git"):
        real = shutil.which(tool)
        assert real, f"{tool} must be installed to run the journeys"
        (folder / tool).symlink_to(real)
    return folder


@pytest.fixture
def journey_env(tmp_path: Path, journey_home: Path, tools_bin: Path) -> dict[str, str]:
    """A hermetic environment: temp HOME/XDG, git identity, empty global git config, fake claude.

    PATH is the tools folder (uv, git), a fake ``claude``, then the system essentials; the
    developer's own ``claude`` is never found.
    """
    fake_bin = tmp_path / "fake-claude-bin"
    make_fake_claude(fake_bin)
    empty_gitconfig = tmp_path / "empty-gitconfig"
    empty_gitconfig.write_text("", encoding="utf-8")
    env = {
        "HOME": str(journey_home),
        "XDG_CONFIG_HOME": str(journey_home / ".config"),
        "GIT_CONFIG_GLOBAL": str(empty_gitconfig),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "Dana Journey",
        "GIT_AUTHOR_EMAIL": "dana@example.invalid",
        "GIT_COMMITTER_NAME": "Dana Journey",
        "GIT_COMMITTER_EMAIL": "dana@example.invalid",
        "PATH": os.pathsep.join([str(tools_bin), str(fake_bin), "/usr/bin", "/bin"]),
        "LANG": "C.UTF-8",
        "NO_COLOR": "1",
    }
    return env


@pytest.fixture
def bull(tmp_path: Path, journey_env: dict[str, str]) -> BullRunner:
    """A runner for the installed ``bull`` script: ``bull(*args, cwd=None, stdin=None, env=None)``.

    ``cwd`` defaults to ``tmp_path``; ``env`` replaces the hermetic environment when given.
    Returns the ``CompletedProcess`` (output as text); it never raises on a non-zero exit.
    """
    exe = bull_executable()

    def run(
        *args: str,
        cwd: Path | None = None,
        stdin: str | None = None,
        env: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return run_cmd(
            [exe, *args],
            cwd or tmp_path,
            env if env is not None else journey_env,
            stdin,
        )

    return run


# --------------------------------------------------------------------------------------------
# The "tally" app used by the build journeys (fixture stack, modules Store and Counter)
# --------------------------------------------------------------------------------------------

TALLY_MEMO = """# Tally outline

## Purpose
A tiny tally for the journeys.

## User journeys
1. **Count** — count up.

## Build order
1. Store (depends on: none)
2. Counter (depends on: Store)

## Modules

### Store
- Purpose: keeps the count.
- Depends on: none
- Files: Contracts/store.fx, store.fx
- Behavior spec:
  - holds a value that starts at zero
- Reference tests: none
- Contract: pending

### Counter
- Purpose: counts up and down.
- Depends on: Store
- Files: Contracts/counter.fx, counter.fx
- Behavior spec:
  - increments and decrements by one
- Reference tests: none
- Contract: pending

## Decisions log
"""

#: What the skeleton-builder agent would write: contracts, stub sources and one smoke test each.
TALLY_SKELETON: dict[str, str] = {
    "src/Modules/Store/Contracts/store.fx": "# store contract\npub Store\nfield value: integer\n",
    "src/Modules/Store/store.fx": "# store\nstart value 0\n",
    "tests/Store/store.test": (
        "# smoke\npass skeleton_smoke\n"
        "covers src/Modules/Store/store.fx:2\ncovers src/Modules/Store/Contracts/store.fx:2-3\n"
    ),
    "src/Modules/Counter/Contracts/counter.fx": (
        "# counter contract\npub Counter\npub increment\nfield value: integer\n"
    ),
    "src/Modules/Counter/counter.fx": "# counter\non increment: value = value + 1\n",
    "tests/Counter/counter.test": (
        "# smoke\npass skeleton_smoke\n"
        "covers src/Modules/Counter/counter.fx:2\ncovers src/Modules/Counter/Contracts/counter.fx:2-4\n"
    ),
    "tests/journey/count.test": "pass journey_smoke\n",
}

#: What the test-writer and code-writer agents would write for each module's only unit.
TALLY_MODULE_WORK: dict[str, dict[str, str]] = {
    "Store": {
        "tests/Store/store.test": (
            "# store behaviors\npass starts_at_zero\ncovers src/Modules/Store/store.fx:2\n"
            "pass can_reset\ncovers src/Modules/Store/store.fx:3\n"
            "covers src/Modules/Store/Contracts/store.fx:2-3\n"
        ),
        "src/Modules/Store/store.fx": "# store\nstart value 0\non reset: value = 0\n",
    },
    "Counter": {
        "tests/Counter/counter.test": (
            "# counter behaviors\npass increments\ncovers src/Modules/Counter/counter.fx:2\n"
            "pass decrements\ncovers src/Modules/Counter/counter.fx:3\n"
            "covers src/Modules/Counter/Contracts/counter.fx:2-4\n"
        ),
        "src/Modules/Counter/counter.fx": (
            "# counter\non increment: value = value + 1\non decrement: value = value - 1\n"
        ),
    },
}


def bull_ok(
    bull: BullRunner, *args: str, cwd: Path
) -> subprocess.CompletedProcess[str]:
    """Run ``bull <args>`` in ``cwd`` and assert it exits 0 (the message shows the output)."""
    done = bull(*args, cwd=cwd)
    assert done.returncode == 0, (
        f"bull {' '.join(args)} -> {done.returncode}\n{done.stdout}{done.stderr}"
    )
    return done


def new_tally_app(
    bull: BullRunner, tmp_path: Path, env: Mapping[str, str], stage: int = 3
) -> Path:
    """Create ``tally`` with the fixture stack, the memo and modules, up to ``stage`` (2, 3 or 5).

    Uses only ``bull`` commands (as the orchestrator would) and commits each step. Stage 3 means
    the ``outline-approved`` and ``setup`` checkpoints are recorded and ``fixture.toml`` exists.
    """
    app = tmp_path / "tally"
    bull_ok(bull, "init", str(app), cwd=tmp_path)
    bull_ok(bull, "stack", "select", "fixture", cwd=app)
    bull_ok(bull, "status", "stage", "1", cwd=app)
    bull_ok(bull, "status", "stage", "2", cwd=app)
    write_files(app, {"docs/outline.md": TALLY_MEMO})
    commit_all(app, env, "docs: outline memo")
    bull_ok(bull, "status", "checkpoint", "outline-approved", cwd=app)
    bull_ok(bull, "status", "init-modules", cwd=app)
    if stage >= 3:
        write_files(app, {"fixture.toml": ""})
        bull_ok(bull, "stack", "check", cwd=app)
        bull_ok(bull, "status", "checkpoint", "setup", cwd=app)
        bull_ok(bull, "status", "stage", "3", cwd=app)
    if (
        stage >= 5
    ):  # checkpoints recorded directly; the skeleton and prototype work is not redone
        bull_ok(bull, "status", "checkpoint", "skeleton", cwd=app)
        bull_ok(bull, "status", "stage", "4", cwd=app)
        bull_ok(bull, "status", "checkpoint", "ui-approved", cwd=app)
        bull_ok(bull, "status", "stage", "5", cwd=app)
    commit_all(app, env, "chore: setup")
    return app


def tag_checkpoint(
    bull: BullRunner, app: Path, env: Mapping[str, str], label: str
) -> None:
    """Create the git tag the pipeline names for ``label`` (``bull status ref tag <label>``)."""
    name = bull_ok(bull, "status", "ref", "tag", label, cwd=app).stdout.strip()
    git(app, env, "tag", name)


def build_tally_module(
    bull: BullRunner, app: Path, env: Mapping[str, str], module: str
) -> None:
    """Build ``module`` of the tally app as the orchestrator would: tests, code, gates, merge, tag.

    Writes the files the test-writer and code-writer agents would, runs the full gates (which
    record the pass the merge guard needs), merges ``module/<module>`` into ``main``, writes the
    API snapshot, marks the module done and tags it.
    """
    branch = f"module/{module}"
    git(app, env, "switch", "-c", branch, "main")
    bull_ok(bull, "status", "module", module, "in_progress", cwd=app)
    bull_ok(bull, "status", "unit", module, "1", "tests", cwd=app)
    work = TALLY_MODULE_WORK[module]
    write_files(app, {k: v for k, v in work.items() if k.startswith("tests/")})
    commit_all(app, env, f"test({module}): unit 1 tests")
    write_files(app, {k: v for k, v in work.items() if k.startswith("src/")})
    bull_ok(bull, "gates", module, "--fast", cwd=app)
    bull_ok(bull, "status", "unit", module, "1", "code", cwd=app)
    bull_ok(bull, "status", "unit", module, "1", "done", cwd=app)
    commit_all(app, env, f"feat({module}): unit 1")
    bull_ok(bull, "gates", module, cwd=app)
    git(app, env, "switch", "main")
    git(app, env, "merge", "--no-ff", "-m", f"Merge {branch}", branch)
    bull_ok(bull, "gates", "--after-merge", branch, cwd=app)
    bull_ok(bull, "api", module, "--write", cwd=app)
    bull_ok(bull, "status", "module", module, "done", cwd=app)
    commit_all(app, env, f"chore: {module} done")
    tag_checkpoint(bull, app, env, f"done/{module}")


def new_accepted_tally_app(
    bull: BullRunner, tmp_path: Path, env: Mapping[str, str]
) -> Path:
    """A tally app with both modules built and ``app-accepted`` recorded and committed on main."""
    app = new_tally_app(bull, tmp_path, env, stage=5)
    write_files(app, TALLY_SKELETON)
    for module in ("Store", "Counter"):
        bull_ok(bull, "api", module, "--write", cwd=app)
    commit_all(app, env, "chore: skeleton")
    bull_ok(bull, "gates", "--all", cwd=app)
    for module in ("Store", "Counter"):
        build_tally_module(bull, app, env, module)
    bull_ok(bull, "gates", "--all", cwd=app)
    bull_ok(bull, "status", "stage", "6", cwd=app)
    bull_ok(bull, "status", "checkpoint", "app-accepted", cwd=app)
    commit_all(app, env, "chore: app accepted")
    tag_checkpoint(bull, app, env, "app-accepted")
    return app


#: A small app built without bull (fixture-stack files, a legacy test and a journey test).
LEGACY_APP_FILES: dict[str, str] = {
    "fixture.toml": "",
    "src/main.fx": "# entry point\nstart value 0\n",
    "src/counter.fx": "# counter\non increment: value = value + 1\n",
    "tests/counter_test.test": "pass increments\ncovers src/counter.fx:2\n",
    "tests/journey/count.test": "pass journey_smoke\n",
}


def new_legacy_app(tmp_path: Path, env: Mapping[str, str]) -> Path:
    """A plain git repo (no bull) with two commits on ``main`` holding ``LEGACY_APP_FILES``."""
    app = tmp_path / "legacy"
    app.mkdir()
    git(app, env, "init", "-q", "-b", "main")
    write_files(app, LEGACY_APP_FILES)
    commit_all(app, env, "the app before bull")
    write_files(app, {"README.md": "A tiny counter.\n"})
    commit_all(app, env, "add readme")
    return app
