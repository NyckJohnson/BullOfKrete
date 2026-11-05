"""Shared test helpers: temporary apps, a throwaway copy of the pipeline with a fake stack."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

PIPELINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE / "workflow"))

FAKE_STACK = {
    "stack.sh": 'STACK_TITLE="Fake"\nSTACK_DESCRIPTION="test"\nSTACK_REQUIRES="none"\n'
                'STACK_SOURCE_GLOB="*.txt"\nSTACK_COMMENT="#"\nSTACK_SCAFFOLD="src"\n',
    "config.sh": 'APP_SOURCE_DIR="src"\nAPP_TEST_DIR="tests"\n',
    "gates.sh": textwrap.dedent("""\
        stack_preflight() { :; }
        stack_setup_gate() { :; }
        stack_build_test() { echo "scope=$SCOPE_MODULE"; COVERAGE_DATA="$RESULTS/cov"; touch "$COVERAGE_DATA"; ! grep -rq BROKEN src || { fail "build/test"; return 1; }; }
        stack_build_test_fast() { ! grep -rq BROKEN "$(module_src "$1")" || { echo "$1/broken()" >> "$FAILED_TESTS"; fail "build/test (fast)"; return 1; }; }
        stack_lint() { :; }
        stack_ui_tests() { true; }
        stack_rerun_failed() { echo "rerun: $*"; ! grep -rq BROKEN src || { echo "Core/broken()" >> "$FAILED_TESTS"; return 1; }; }
        """),
    "contract.py": 'SOURCE_GLOB = "*.txt"\ndef extract(path):\n'
                   '    return [l[4:] for l in path.read_text().splitlines() if l.startswith("api ")]\n',
    "coverage.py": textwrap.dedent("""\
        def uncovered(root, sources, data):
            found, missing = {}, []
            for p in sources:
                text = p.read_text()
                if "NODATA" in text:
                    missing.append(p)
                else:
                    found[p] = [i for i, l in enumerate(text.splitlines(), 1) if "UNCOVERED" in l]
            return found, missing
        """),
    "check.py": "def check(root, config):\n    return [(True, 'ok', '')]\n",
    "rules.md": "# fake\n## common\nplain\n",
    "setup.md": "nothing\n",
}


def run(*args: str, cwd: Path, env: dict[str, str] | None = None, check: bool = False) -> subprocess.CompletedProcess[str]:
    full_env = {**os.environ, **(env or {})}
    full_env.pop("PIPELINE_APP_ROOT", None)
    full_env.pop("CLAUDE_PROJECT_DIR", None)
    full_env.update(env or {})
    return subprocess.run(list(args), cwd=cwd, env=full_env, capture_output=True, text=True, check=check)


def git_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    run("git", "init", "-q", "-b", "main", cwd=path, check=True)
    run("git", "config", "user.email", "t@t", cwd=path, check=True)
    run("git", "config", "user.name", "t", cwd=path, check=True)
    return path


def commit_all(path: Path, message: str = "c") -> None:
    run("git", "add", "-A", cwd=path, check=True)
    run("git", "commit", "-qm", message, cwd=path, check=True)


class TempDirTest:
    """Mixin: self.tmp is a fresh directory per test."""

    def setUp(self) -> None:  # noqa: D401
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name).resolve()

    def tearDown(self) -> None:
        self._tmp.cleanup()


def pipeline_copy(target: Path) -> Path:
    """Copy the pipeline to `target` (no fake stack added); returns the copy's bin/ios-pipeline.
    Tests that write into stacks/ (stack new, a fake stack) use a copy, never the real repo."""
    shutil.copytree(PIPELINE, target, ignore=shutil.ignore_patterns(".git", "__pycache__", "tests"))
    return target / "bin" / "ios-pipeline"


def pipeline_with_fake_stack(target: Path) -> Path:
    """Copy the pipeline to `target` and add stacks/fake; returns the copy's bin/ios-pipeline."""
    cli = pipeline_copy(target)
    stack = target / "stacks" / "fake"
    stack.mkdir()
    for name, text in FAKE_STACK.items():
        (stack / name).write_text(text)
    return cli


FAKE_OUTLINE = """## Build order
1. Core (depends on: none)
## Modules
### Core
- Files: Store.txt, Impl.txt
"""


class FakeStackApp(unittest.TestCase):
    """An app on the fake stack with one module, Core; subclasses add the tests."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.cli = pipeline_with_fake_stack(Path(cls._tmp.name) / "pipeline")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def setUp(self) -> None:
        self._app = tempfile.TemporaryDirectory()
        self.app = git_repo(Path(self._app.name).resolve() / "app")
        self.ios("init", str(self.app))
        self.ios("stack", "select", "fake")
        core = self.app / "src" / "Modules" / "Core"
        (core / "Contracts").mkdir(parents=True)
        (self.app / "docs").mkdir(exist_ok=True)
        (self.app / "docs" / "outline.md").write_text(FAKE_OUTLINE)
        self.write("Contracts/Store.txt", "# coverage-exempt-file: declarations only\napi load()\nNODATA\n")
        self.write("Impl.txt", "line\nfine\n")
        self.ios("status", "init-modules")
        self.ios("api", "Core", "--write")
        commit_all(self.app)

    def tearDown(self) -> None:
        self._app.cleanup()

    def ios(self, *args: str, ok: bool = True):
        result = run(str(self.cli), *args, cwd=self.app)
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def write(self, relative: str, text: str) -> None:
        path = self.app / "src" / "Modules" / "Core" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def passes(self) -> list[str]:
        folder = self.app / ".pipeline" / "gates"
        return sorted(p.name for p in folder.iterdir()) if folder.is_dir() else []
