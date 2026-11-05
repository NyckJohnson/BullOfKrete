"""`ios-pipeline stack test`: a stack's gates against its fixture, with known verdicts."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from helpers import FAKE_OUTLINE, FAKE_STACK, PIPELINE, pipeline_with_fake_stack, run

CASES: list[dict[str, Any]] = [
    {"id": "clean", "about": "a clean module passes",
     "steps": [{"run": ["gates", "Core"], "exit": 0, "output": ["GATES: PASS"], "recorded": True}]},
    {"id": "failing-test",
     "change": {"write": {"source/Modules/Core/Impl.txt": "BROKEN\n"}},
     "steps": [{"run": ["gates", "Core"], "exit": 1, "output": ["build/test"], "recorded": False}]},
    {"id": "rerun",
     "change": {"write": {"source/Modules/Core/Impl.txt": "BROKEN\n"}},
     "steps": [{"run": ["gates", "Core", "--fast"], "exit": 1,
                "files": {".pipeline/results/failed-tests.txt": "nonempty"}},
               {"run": ["gates", "--failed"], "exit": 1, "output": ["rerun: Core/broken()"]}]},
    {"id": "fast",
     "steps": [{"run": ["gates", "Core", "--fast"], "exit": 0, "output": ["not recorded"], "recorded": False}]},
    {"id": "contract-change",
     "change": {"replace": [{"file": "source/Modules/Core/Contracts/Store.txt",
                             "old": "api load()", "new": "api load()\napi save()"}]},
     "steps": [{"run": ["gates", "Core"], "exit": 1, "output": ["api (Core)"]}]},
    {"id": "uncovered",
     "change": {"write": {"source/Modules/Core/Impl.txt": "x UNCOVERED\n"}},
     "steps": [{"run": ["gates", "Core"], "exit": 1, "output": ["coverage (Core)"]}]},
    {"id": "exemption",
     "change": {"write": {"source/Modules/Core/Impl.txt": "x UNCOVERED # coverage-exempt: test case\n"}},
     "steps": [{"run": ["gates", "Core"], "exit": 0, "absent": ["FAIL"]}]},
]


class StackTestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.cli = str(pipeline_with_fake_stack(Path(cls._tmp.name) / "pipeline"))
        cls.stack = Path(cls._tmp.name) / "pipeline" / "stacks" / "fake"
        fixture = cls.stack / "fixture"
        (fixture / "project" / "docs").mkdir(parents=True)
        (fixture / "project" / "docs" / "outline.md").write_text(FAKE_OUTLINE)
        core = fixture / "source" / "Modules" / "Core"
        (core / "Contracts").mkdir(parents=True)
        (core / "Contracts" / "Store.txt").write_text("# coverage-exempt-file: declarations only\napi load()\nNODATA\n")
        (core / "Impl.txt").write_text("fine\n")
        cls.outside = Path(cls._tmp.name) / "elsewhere"   # not an app: stack test needs none
        cls.outside.mkdir()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def cases(self, cases: list[dict[str, Any]], **extra: Any) -> None:
        spec = {"layout": {"project": ".", "source": "{APP_SOURCE_DIR}"},
                "setup": [["status", "init-modules"], ["api", "Core", "--write"]],
                "cases": cases, **extra}
        (self.stack / "cases.json").write_text(json.dumps(spec))

    def stack_test(self, *args: str):
        return run(self.cli, "stack", "test", "fake", *args, cwd=self.outside)

    def test_every_case_gives_its_verdict(self) -> None:
        self.cases(CASES)
        result = self.stack_test()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"{len(CASES)} passed, 0 failed, 0 not run", result.stdout)

    def test_a_wrong_verdict_fails(self) -> None:
        wrong = {**CASES[1], "steps": [{"run": ["gates", "Core"], "exit": 0, "recorded": True}]}
        self.cases([CASES[0], wrong])
        result = self.stack_test()
        self.assertEqual(result.returncode, 1)
        self.assertIn("❌ failing-test", result.stdout)
        self.assertIn("exit 1, expected 0", result.stdout)
        self.assertIn("gate pass not recorded", result.stdout)
        self.assertIn("GATES: FAIL", result.stdout)   # the failing case's output is shown

    def test_missing_tools_are_not_run_never_passed(self) -> None:
        self.cases(CASES[:2], requires={"commands": ["no-such-tool-xyz"], "note": "install it"})
        result = self.stack_test()
        self.assertEqual(result.returncode, 3)
        self.assertIn("0 passed, 0 failed, 2 not run", result.stdout)
        self.assertIn("command 'no-such-tool-xyz' not found", result.stdout)
        self.assertIn("install it", result.stdout)

    def test_missing_fixture_files_are_not_run(self) -> None:
        self.cases(CASES[:1], requires={"files": ["project/App/App.xcodeproj"]})
        result = self.stack_test()
        self.assertEqual(result.returncode, 3)
        self.assertIn("fixture file project/App/App.xcodeproj missing", result.stdout)

    def test_one_case(self) -> None:
        self.cases(CASES)
        result = self.stack_test("--case", "contract-change")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("1 passed", result.stdout)
        self.assertNotIn("clean", result.stdout)
        result = self.stack_test("--case", "nope")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no case nope", result.stderr)

    def test_a_change_that_does_not_apply_fails_the_case(self) -> None:
        self.cases([{"id": "bad", "change": {"replace": [{"file": "source/Modules/Core/Impl.txt",
                                                          "old": "absent", "new": "x"}]}, "steps": []}])
        result = self.stack_test()
        self.assertEqual(result.returncode, 1)
        self.assertIn("'absent' not found", result.stdout)

    def test_stack_without_cases(self) -> None:
        (self.stack / "cases.json").unlink(missing_ok=True)
        result = self.stack_test()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("has no cases.json", result.stderr)


class StaticCheckTests(unittest.TestCase):
    """`stack test <name> --static`: a stack's shape, no toolchain needed."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.home = Path(cls._tmp.name) / "pipeline"
        cls.cli = str(pipeline_with_fake_stack(cls.home))
        cls.outside = Path(cls._tmp.name) / "elsewhere"
        cls.outside.mkdir()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def static(self, stack: str = "fake"):
        return run(self.cli, "stack", "test", stack, "--static", cwd=self.outside)

    def test_the_real_ios_stack_passes(self) -> None:
        # Read-only: run straight against the actual pipeline, not a copy.
        result = run(str(PIPELINE / "bin" / "ios-pipeline"), "stack", "test", "ios", "--static",
                    cwd=self.outside)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("shape looks complete", result.stdout)

    def test_a_freshly_scaffolded_stack_reports_problems(self) -> None:
        # pipeline_with_fake_stack writes only stack.sh, config.sh, gates.sh, contract.py,
        # coverage.py, check.py, rules.md and setup.md (FAKE_STACK): no defaults.sh, gitignore,
        # cases.json or fixture/, and stack.sh is missing several required keys.
        result = self.static()
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing defaults.sh", result.stdout)
        self.assertIn("missing gitignore", result.stdout)
        self.assertIn("missing cases.json", result.stdout)
        self.assertIn("fixture/ is missing or empty", result.stdout)
        self.assertIn("stack.sh: STACK_KIND is not set", result.stdout)
        self.assertIn("rules.md: missing '## outline' section", result.stdout)

    def test_a_properly_shaped_stack_passes(self) -> None:
        stack = self.home / "stacks" / "fake"
        (stack / "defaults.sh").write_text("")
        (stack / "gitignore").write_text("build/\n")
        manifest = (stack / "stack.sh").read_text()
        manifest += ('STACK_LANGUAGE="fake"\nSTACK_KIND="tool"\nSTACK_MATURITY="experimental"\n'
                    'STACK_TEST_GLOB="*Tests.txt"\n')
        (stack / "stack.sh").write_text(manifest)
        (stack / "rules.md").write_text(
            "# fake\n## common\nx\n## outline\nx\n## skeleton-builder\nx\n## test-writer\nx\n"
            "## code-writer\nx\n## reviewer\nx\n## coverage-analyst\nx\n## ui-test-writer\nx\n")
        (stack / "fixture").mkdir(exist_ok=True)
        (stack / "fixture" / "placeholder.txt").write_text("x\n")
        ids = ["clean", "fast", "no-tests", "failing-test", "build-warning", "lint",
              "contract-change", "uncovered", "exemption", "setup-broken", "journey", "journey-failing"]
        (stack / "cases.json").write_text(json.dumps({"cases": [{"id": i, "steps": []} for i in ids]}))
        result = self.static()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("shape looks complete", result.stdout)

    def test_missing_a_required_case_id_fails(self) -> None:
        stack = self.home / "stacks" / "fake"
        (stack / "fixture").mkdir(exist_ok=True)
        (stack / "fixture" / "placeholder.txt").write_text("x\n")
        (stack / "cases.json").write_text(json.dumps({"cases": [{"id": "clean", "steps": []}]}))
        result = self.static()
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing required case 'setup-broken'", result.stdout)
        self.assertIn("missing required case 'journey'", result.stdout)   # fake defines stack_ui_tests


if __name__ == "__main__":
    unittest.main()
