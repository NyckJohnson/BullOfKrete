"""Journey 6: add a stack through the stack workflow (a toolchain-free ``go_cli``)."""

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
    run_cmd,
    tag_checkpoint,
    write_files,
)

STACK_TOML = """format = 1

[stack]
name = "go_cli"
title = "Go command-line tool"
description = "A Go command-line tool (the journey fakes the toolchain)."
language = "gx"
kind = "tool"
maturity = "experimental"
source_glob = "*.gx"
test_glob = ["*.test"]
comment = "#"
scaffold = ["src", "tests"]
gitignore = ["bin/"]
agents = ["skeleton-builder", "test-writer", "code-writer", "reviewer", "coverage-analyst"]

[[stack.requires]]
tool = "{tool}"
hint = "install {tool}"

[settings.source_dir]
type = "str"
default = "src/gx"
description = "Folder holding the sources."

[settings.test_dir]
type = "str"
default = "tests"
description = "Folder holding the tests."

[settings."coverage.exclude"]
default = []

[gates]
preflight = ["{{python}}", "{{stack_dir}}/gates.py", "preflight"]
setup = ["{{python}}", "{{stack_dir}}/gates.py", "setup"]
build_test = ["{{python}}", "{{stack_dir}}/gates.py", "build-test"]
build_test_fast = ["{{python}}", "{{stack_dir}}/gates.py", "build-test-fast", "{{module}}"]
lint = ["{{python}}", "{{stack_dir}}/gates.py", "lint", "{{module}}"]
rerun_failed = ["{{python}}", "{{stack_dir}}/gates.py", "rerun", "{{failed_ids}}"]
"""

RULES_MD = """## common
- Sources are `*.gx`; tests are `tests/<module>/*.test`.

## outline
- Name modules in lowercase.

## skeleton-builder
- Write contracts as `pub <name>` lines.

## test-writer
- One `pass <name>` or `fail <name>` line per behavior.

## code-writer
- Keep every code line covered by a test.

## reviewer
- Check that nothing outside the module is touched.

## coverage-analyst
- Classify uncovered lines as missed, exempt or not-in-spec.
"""

SETUP_MD = """# Setup for go_cli

1. Put a `go.mod` file at the project root.

## For a feature
Nothing new to set up.
"""

READERS_PY = '''"""Readers for the journey's fake go_cli stack."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from bull.Modules.stacks.Contracts import CheckItem, CoverageData, TestRun


def contract_declarations(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip().startswith("pub ")]


def test_results(results: Path) -> TestRun | None:
    try:
        data = json.loads((results / "tests.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return TestRun(count=int(data["count"]), failed=tuple(data["failed"]))


def uncovered(part_root: Path, sources: Sequence[Path], results: Path) -> CoverageData:
    try:
        data = json.loads((results / "coverage.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    missing: dict[Path, tuple[int, ...]] = {}
    no_data: list[Path] = []
    root = part_root.resolve()
    for source in sources:
        try:
            rel = source.resolve().relative_to(root).as_posix()
        except ValueError:
            rel = source.as_posix()
        lines = source.read_text(encoding="utf-8").splitlines()
        code = [n for n, text in enumerate(lines, 1) if text.strip() and not text.strip().startswith("#")]
        if not code:
            no_data.append(source)
            continue
        covered = set(data.get(rel, []))
        left = tuple(n for n in code if n not in covered)
        if left:
            missing[source] = left
            missing[Path(rel)] = left
    return CoverageData(uncovered=missing, no_data=tuple(no_data))


def check(part_root: Path, settings: Mapping[str, object], adopting: bool) -> list[CheckItem]:
    present = (part_root / "go.mod").is_file()
    return [CheckItem(ok=present, item="go.mod present", fix="create go.mod at the project root")]
'''

#: The real gate code: runs the stack's own fixture language with no toolchain.
GATES_PY = '''"""Gate steps for the journey's fake go_cli stack (no Go toolchain needed)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("BULL_PART_ROOT", "."))
RESULTS = Path(os.environ.get("BULL_RESULTS", "results"))
SETTINGS = json.loads(os.environ.get("BULL_SETTINGS", "{}"))
SRC = ROOT / str(SETTINGS.get("source_dir", "src/gx"))
TESTS = ROOT / str(SETTINGS.get("test_dir", "tests"))


def sources() -> list[Path]:
    return sorted(SRC.rglob("*.gx")) if SRC.is_dir() else []


def tests(module: str | None) -> list[Path]:
    base = TESTS / module if module else TESTS
    return sorted(base.rglob("*.test")) if base.is_dir() else []


def verdicts(path: Path) -> dict[str, bool]:
    found: dict[str, bool] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        word, _, name = line.strip().partition(" ")
        if word in ("pass", "fail"):
            found[f"{path.relative_to(TESTS).as_posix()}::{name}"] = word == "pass"
    return found


def run(files: list[Path], only: list[str] | None = None) -> int:
    results: dict[str, bool] = {}
    covered: dict[str, set[int]] = {}
    for path in files:
        results.update(verdicts(path))
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("covers "):
                target, _, spans = line[len("covers "):].partition(":")
                for span in spans.split(","):
                    low, _, high = span.partition("-")
                    covered.setdefault(target, set()).update(range(int(low), int(high or low) + 1))
    if only is not None:
        results = {k: v for k, v in results.items() if k in only}
    RESULTS.mkdir(parents=True, exist_ok=True)
    failed = [name for name, ok in results.items() if not ok]
    (RESULTS / "tests.json").write_text(json.dumps({"count": len(results), "failed": failed}))
    (RESULTS / "coverage.json").write_text(json.dumps({k: sorted(v) for k, v in covered.items()}))
    return len(failed)


def scan(marker: str, label: str, files: list[Path]) -> int:
    status = 0
    for path in files:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if marker in line:
                print(f"bull-fail: {label} {path.relative_to(ROOT).as_posix()}:{number}")
                status = 1
    return status


def main(argv: list[str]) -> int:
    step = argv[0]
    if step == "preflight":
        return 0
    if step == "setup":
        if not (ROOT / "go.mod").is_file():
            print("bull-fail: go.mod missing")
            return 1
        return 0
    if step == "build-test":
        run(tests(None))
        return scan("WARN", "warning", sources())
    if step == "build-test-fast":
        run(tests(argv[1]))
        return scan("WARN", "warning", sources())
    if step == "lint":
        return scan("LINT", "lint", sources())
    if step == "rerun":
        return 1 if run(tests(None), only=argv[1:]) else 0
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
'''

#: A broken gate: every step passes and every test and line counts as fine.
PASS_EVERYTHING_GATES_PY = '''"""A gate that passes everything, whatever the tests say."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if argv[0] in ("build-test", "build-test-fast", "rerun"):
        root = Path(os.environ["BULL_PART_ROOT"])
        results = Path(os.environ["BULL_RESULTS"])
        results.mkdir(parents=True, exist_ok=True)
        (results / "tests.json").write_text(json.dumps({"count": 1, "failed": []}))
        everything = {
            path.relative_to(root).as_posix(): list(range(1, 200))
            for path in root.rglob("*.gx")
        }
        (results / "coverage.json").write_text(json.dumps(everything))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
'''

FIXTURE_MEMO = """# Fixture outline

## Purpose
A tiny counter for the stack's self-test.

## User journeys
1. **Count** — count up.

## Build order
1. counter (depends on: none)

## Modules

### counter
- Purpose: counts up and down.
- Depends on: none
- Files: Contracts/counter.gx, counter.gx
- Behavior spec:
  - increments and decrements by one
- Reference tests: none
- Contract: pending

## Decisions log
"""

CONTRACT_GX = "# counter contract\npub Counter\npub increment\n"
COUNTER_GX = (
    "# counter\non increment: value = value + 1\non decrement: value = value - 1\n"
)
TEST_A = (
    "pass one\npass two\n"
    "covers src/gx/Modules/counter/counter.gx:2-3\n"
    "covers src/gx/Modules/counter/Contracts/counter.gx:2-3\n"
)
APP_FILES: dict[str, str] = {
    "docs/outline.md": FIXTURE_MEMO,
    "go.mod": "module fixture\n",
    "src/gx/Modules/counter/Contracts/counter.gx": CONTRACT_GX,
    "src/gx/Modules/counter/counter.gx": COUNTER_GX,
    "tests/counter/a.test": TEST_A,
}

_SRC = "src/gx/Modules/counter/counter.gx"
CASES: dict[str, Any] = {
    "format": 1,
    "layout": {"app/": "."},
    "settings": {"source_dir": "src/gx", "test_dir": "tests"},
    "cases": [
        {
            "id": "clean",
            "run": ["gates", "counter"],
            "expect": {"verdict": "pass", "recorded": True},
        },
        {
            "id": "fast",
            "run": ["gates", "counter", "--fast"],
            "expect": {"verdict": "pass", "recorded": False},
        },
        {
            "id": "no-tests",
            "change": {"delete": ["tests/counter/a.test"]},
            "run": ["gates", "counter"],
            "expect": {"verdict": "fail", "gate": "tests", "output": "no tests"},
        },
        {
            "id": "failing-test",
            "change": {"replace": {"tests/counter/a.test": "fail one\n"}},
            "run": ["gates", "counter"],
            "expect": {"verdict": "fail", "gate": "tests", "output": "one"},
            "then": {
                "run": ["gates", "--failed"],
                "expect": {"verdict": "fail", "ran": 1},
            },
        },
        {
            "id": "build-warning",
            "change": {
                "replace": {
                    _SRC: "# counter\non increment: value = value + 1 WARN\non decrement: value = value - 1\n"
                }
            },
            "run": ["gates", "counter"],
            "expect": {"verdict": "fail", "gate": "build", "output": "warning"},
        },
        {
            "id": "lint",
            "change": {
                "replace": {
                    _SRC: "# counter\non increment: value = value + 1 LINT\non decrement: value = value - 1\n"
                }
            },
            "run": ["gates", "counter"],
            "expect": {"verdict": "fail", "gate": "lint", "output": "lint"},
        },
        {
            "id": "contract-change",
            "change": {
                "replace": {
                    "src/gx/Modules/counter/Contracts/counter.gx": "# counter contract\npub Counter\npub reset\n"
                }
            },
            "run": ["gates", "counter"],
            "expect": {"verdict": "fail", "gate": "api"},
        },
        {
            "id": "uncovered",
            "change": {"add": {_SRC: COUNTER_GX + "on reset: value = 0\n"}},
            "run": ["gates", "counter"],
            "expect": {"verdict": "fail", "gate": "coverage"},
        },
        {
            "id": "exemption",
            "change": {
                "add": {
                    _SRC: COUNTER_GX
                    + "on reset: value = 0 # coverage-exempt: trivial\n"
                }
            },
            "run": ["gates", "counter"],
            "expect": {"verdict": "pass"},
        },
        {
            "id": "setup-broken",
            "change": {"delete": ["go.mod"]},
            "run": ["gates", "counter"],
            "expect": {"verdict": "fail", "gate": "setup", "output": "go.mod"},
        },
    ],
}


def _status_file(stack: Path) -> dict[str, Any]:
    loaded = json.loads((stack / ".bull/status.json").read_text())
    assert isinstance(loaded, dict)
    return loaded


def _scratch_env(env: dict[str, str], home: Path) -> dict[str, str]:
    """The journey environment with another HOME (so installing there leaves ours alone)."""
    home.mkdir(parents=True, exist_ok=True)
    return {**env, "HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config")}


def _snapshot_for_fixture(
    bull: BullRunner, stack: Path, tmp_path: Path, env: dict[str, str]
) -> str:
    """Generate the fixture app's ``docs/api/counter.md`` with ``bull api`` (in a scratch HOME)."""
    scratch_env = _scratch_env(env, tmp_path / "scratch-home")
    scratch = tmp_path / "scratch-app"
    bull_ok_env(bull, scratch_env, "stack", "install", str(stack), cwd=tmp_path)
    bull_ok_env(bull, scratch_env, "init", str(scratch), cwd=tmp_path)
    bull_ok_env(bull, scratch_env, "stack", "select", "go_cli", cwd=scratch)
    write_files(scratch, APP_FILES)
    bull_ok_env(bull, scratch_env, "api", "counter", "--write", cwd=scratch)
    return (scratch / "docs/api/counter.md").read_text(encoding="utf-8")


def bull_ok_env(bull: BullRunner, env: dict[str, str], *args: str, cwd: Path) -> None:
    done = bull(*args, cwd=cwd, env=env)
    assert done.returncode == 0, f"bull {' '.join(args)}\n{done.stdout}{done.stderr}"


def _build_stack_to_gate_code(
    bull: BullRunner,
    tmp_path: Path,
    env: dict[str, str],
    gates: str = GATES_PY,
    tool: str = "git",
    initialize: bool = True,
    here: str | None = None,
) -> Path:
    """Run the stack workflow up to the written gate code (stage 4), as the agents would."""
    stack = tmp_path / "stacks" / "go_cli"
    where = here or str(stack)  # how the self-test names the stack: "." or its path
    if initialize:
        stack.parent.mkdir()
        bull_ok(bull, "init", "--stack", str(stack), cwd=tmp_path)

    # Stage 1: the design, then checkpoint design-approved.
    write_files(stack, {"DESIGN.md": "# go_cli stack: design\n\nGo, a plain CLI.\n"})
    commit_all(stack, env, "docs: design")
    bull_ok(bull, "status", "checkpoint", "design-approved", cwd=stack)
    commit_all(stack, env, "chore: design approved")
    tag_checkpoint(bull, stack, env, "design-approved")

    # Stage 2: scaffold the stack's files.
    bull_ok(bull, "status", "stage", "2", cwd=stack)
    write_files(
        stack,
        {
            "stack.toml": STACK_TOML.format(tool=tool),
            "rules.md": RULES_MD,
            "setup.md": SETUP_MD,
            "readers.py": READERS_PY,
        },
    )
    commit_all(stack, env, "feat: scaffold the stack")

    # Stage 3: the fixture app and cases.json.
    bull_ok(bull, "status", "stage", "3", cwd=stack)
    write_files(stack, {f"fixture/app/{k}": v for k, v in APP_FILES.items()})
    write_files(stack, {"cases.json": json.dumps(CASES, indent=2) + "\n"})
    commit_all(stack, env, "feat: fixture and cases")
    bull_ok(bull, "stack", "test", where, "--static", cwd=stack)
    snapshot = _snapshot_for_fixture(bull, stack, tmp_path, env)
    write_files(stack, {"fixture/app/docs/api/counter.md": snapshot})
    commit_all(stack, env, "feat: contract snapshot for the fixture")
    static = bull_ok(bull, "stack", "test", where, "--static", cwd=stack)
    assert (
        "problem" not in static.stdout.lower() or "0 problem" in static.stdout.lower()
    )
    assert (stack / ".bull/passes").is_dir()

    # Stage 4: the gate code.
    bull_ok(bull, "status", "stage", "4", cwd=stack)
    write_files(stack, {"gates.py": gates})
    toml = (stack / "stack.toml").read_text()
    assert "gates.py" in toml
    commit_all(stack, env, "feat: gate code")
    return stack


def _add_a_stack(
    bull: BullRunner,
    tmp_path: Path,
    env: dict[str, str],
    literal: bool,
) -> None:
    """The whole journey. ``literal`` follows the memo to the letter: ``stack test .``, and the
    full self-test before ``stack install``; otherwise the stack is named by path and installed
    before its full self-test."""
    here = "." if literal else None
    stack = tmp_path / "stacks" / "go_cli"
    stack.parent.mkdir()

    # init --stack: placeholders, DESIGN.md, status at stage 1, a commit.
    created = bull_ok(bull, "init", "--stack", str(stack), cwd=tmp_path)
    assert "go_cli" in created.stdout
    assert "TODO" in (stack / "stack.toml").read_text()
    assert (stack / "DESIGN.md").read_text().startswith("# go_cli stack: design")
    assert (stack / "cases.json").is_file()
    status = _status_file(stack)
    assert (status["kind"], status["name"], status["stage"]) == ("stack", "go_cli", 1)
    assert git_out(stack, env, "branch", "--show-current") == "main"
    assert git_out(stack, env, "status", "--porcelain") == ""
    nxt = bull_ok(bull, "status", "next", cwd=stack).stdout
    assert "design" in nxt
    # Stage rules: no scaffold before the design is approved.
    assert bull("status", "stage", "2", cwd=stack).returncode != 0
    # The app commands refuse in a stack repo.
    assert bull("gates", "--all", cwd=stack).returncode != 0

    # Build the stack up to the gate code.
    _build_stack_to_gate_code(bull, tmp_path, env, initialize=False, here=here)
    if not literal:
        bull_ok(bull, "stack", "install", str(stack), cwd=tmp_path)
    assert _status_file(stack)["checkpoints"] == ["design-approved"]
    assert "stack/design-approved" in git_out(stack, env, "tag")

    # Stage 5 is refused until the full self-test has passed.
    assert bull("status", "stage", "5", cwd=stack).returncode != 0

    # Not installable before... static passes already; the full test runs every case.
    full = bull_ok(bull, "stack", "test", here or str(stack), cwd=stack)
    for case in (c["id"] for c in CASES["cases"]):
        assert case in full.stdout
    assert "0 failed" in full.stdout
    assert "0 not run" in full.stdout

    # Review, rules approval, acceptance.
    bull_ok(bull, "status", "stage", "5", cwd=stack)
    bull_ok(bull, "status", "checkpoint", "rules-approved", cwd=stack)
    commit_all(stack, env, "chore: rules approved")
    tag_checkpoint(bull, stack, env, "rules-approved")
    # Acceptance needs a full pass at the new HEAD, so the self-test runs once more.
    assert bull("status", "checkpoint", "accepted", cwd=stack).returncode != 0
    bull_ok(bull, "stack", "test", here or str(stack), cwd=stack)
    bull_ok(bull, "status", "checkpoint", "accepted", cwd=stack)
    commit_all(stack, env, "chore: accepted")
    tag_checkpoint(bull, stack, env, "accepted")
    assert _status_file(stack)["checkpoints"] == [
        "design-approved",
        "rules-approved",
        "accepted",
    ]
    tags = git_out(stack, env, "tag").splitlines()
    assert {"stack/design-approved", "stack/rules-approved", "stack/accepted"} <= set(
        tags
    )

    # Install: selectable, and listed as experimental.
    before = bull_ok(bull, "stacks", cwd=tmp_path).stdout
    assert literal == ("go_cli" not in before)
    bull_ok(bull, "stack", "install", str(stack), cwd=tmp_path)
    listing = bull_ok(bull, "stacks", cwd=tmp_path)
    line = next(ln for ln in listing.stdout.splitlines() if "go_cli" in ln)
    assert "experimental" in line
    assert "installed" in line
    as_json = json.loads(bull_ok(bull, "stacks", "--json", cwd=tmp_path).stdout)
    entry = next(item for item in as_json if item["name"] == "go_cli")
    assert entry["maturity"] == "experimental"
    app = tmp_path / "goapp"
    bull_ok(bull, "init", str(app), cwd=tmp_path)
    bull_ok(bull, "stack", "select", "go_cli", cwd=app)
    assert 'stack = "go_cli"' in (app / ".bull/config.toml").read_text()
    assert (app / "src").is_dir() and (app / "tests").is_dir()


def test_add_a_stack_through_the_stack_workflow_ends_with_it_listed_as_experimental(
    bull: BullRunner, tmp_path: Path, journey_env: dict[str, str]
) -> None:
    _add_a_stack(bull, tmp_path, journey_env, literal=True)


def test_add_a_stack_when_it_is_installed_before_its_full_self_test(
    bull: BullRunner, tmp_path: Path, journey_env: dict[str, str]
) -> None:
    _add_a_stack(bull, tmp_path, journey_env, literal=False)


def test_a_gate_that_passes_everything_gives_the_failing_test_case_the_wrong_verdict(
    bull: BullRunner, tmp_path: Path, journey_env: dict[str, str]
) -> None:
    env = journey_env
    stack = _build_stack_to_gate_code(
        bull, tmp_path, env, gates=PASS_EVERYTHING_GATES_PY
    )
    bull_ok(
        bull, "stack", "install", str(stack), cwd=tmp_path
    )  # the cases run an installed stack

    one = bull("stack", "test", str(stack), "--case", "failing-test", cwd=stack)
    assert one.returncode == 1
    out = one.stdout + one.stderr
    assert "failing-test" in out
    assert "fail" in out
    assert "FAILED" in out
    assert "0 passed" in out

    full = bull("stack", "test", str(stack), cwd=stack)
    assert full.returncode == 1
    assert "failing-test" in full.stdout
    assert "0 not run" in full.stdout
    # No pass is recorded, so the workflow cannot move on or be installed as accepted.
    assert bull("status", "stage", "5", cwd=stack).returncode != 0


def test_a_case_whose_tool_is_missing_is_reported_not_run_and_fails(
    bull: BullRunner, tmp_path: Path, journey_env: dict[str, str]
) -> None:
    env = journey_env
    stack = _build_stack_to_gate_code(bull, tmp_path, env, tool="gox-not-installed")

    result = bull("stack", "test", str(stack), cwd=stack)
    assert result.returncode == 1
    out = result.stdout + result.stderr
    assert "not run" in out
    assert "gox-not-installed" in out
    assert f"0 passed, 0 failed, {len(CASES['cases']) + 1} not run" in out
    assert run_cmd(["git", "status", "--porcelain"], stack, env).stdout.strip() == ""
    git(stack, env, "log", "-1")
