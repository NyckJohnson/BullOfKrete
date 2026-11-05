"""Faster gate runs: skipping the run after a merge that changed nothing, scoped module runs while
adopting, and rerunning only the tests that failed."""

import json
import unittest

from helpers import PIPELINE, FakeStackApp, TempDirTest, commit_all, run
from test_adopt_gates import load

failed_ids = load("failed_tests").failed_ids


class AfterMergeTests(FakeStackApp):
    def git(self, *args: str) -> str:
        return run("git", *args, cwd=self.app, check=True).stdout.strip()

    def build_module(self, gate_base: bool = True) -> None:
        """Gate the base, build module/Core with a gated change, leave HEAD on the base."""
        if gate_base:
            self.ios("gates", "--all")
        self.git("switch", "-q", "-c", "module/Core")
        self.write("Impl.txt", "line\nfine\nmore\n")
        commit_all(self.app, "feat(Core)")
        self.ios("gates", "Core")
        self.git("switch", "-q", "main")

    def merge(self) -> None:
        self.git("merge", "-q", "--no-ff", "module/Core", "-m", "Merge module/Core")

    def test_skips_when_the_merge_holds_the_gated_code(self) -> None:
        self.build_module()
        self.merge()
        result = self.ios("gates", "--after-merge", "module/Core")
        self.assertIn("skipped the full run", result.stdout)
        self.assertNotIn("build + unit tests", result.stdout)
        self.assertIn(f"{self.git('rev-parse', 'HEAD')}.pass", self.passes())

    def test_ungated_bookkeeping_commits_on_the_base_still_skip(self) -> None:
        self.ios("gates", "--all")
        (self.app / "docs" / "notes.md").write_text("status\n")
        commit_all(self.app, "chore: status")
        self.build_module(gate_base=False)
        self.merge()
        self.assertIn("skipped the full run", self.ios("gates", "--after-merge", "module/Core").stdout)

    def test_runs_everything_when_the_base_moved(self) -> None:
        self.build_module()
        (self.app / "src" / "legacy.txt").write_text("changed on the trunk\n")
        commit_all(self.app, "human change")
        self.merge()
        result = self.ios("gates", "--after-merge", "module/Core")
        self.assertIn("base branch moved", result.stdout)
        self.assertIn("scope=", result.stdout)

    def test_runs_everything_without_an_earlier_gated_commit(self) -> None:
        self.build_module(gate_base=False)
        self.merge()
        self.assertIn("no earlier commit", self.ios("gates", "--after-merge", "module/Core").stdout)

    def test_runs_everything_when_another_module_changed(self) -> None:
        self.ios("gates", "--all")
        self.git("switch", "-q", "-c", "module/Core")
        (self.app / "src" / "Modules" / "Extra").mkdir()
        (self.app / "src" / "Modules" / "Extra" / "X.txt").write_text("x\n")
        commit_all(self.app, "touches Extra")
        self.ios("gates", "Core")
        self.git("switch", "-q", "main")
        self.merge()
        result = self.ios("gates", "--after-merge", "module/Core", ok=False)
        self.assertIn("files of other modules changed", result.stdout)

    def test_runs_everything_when_the_branch_head_was_not_gated(self) -> None:
        self.ios("gates", "--all")
        self.git("switch", "-q", "-c", "module/Core")
        self.write("Impl.txt", "line\nfine\nmore\n")
        commit_all(self.app, "feat(Core)")
        self.git("switch", "-q", "main")
        self.merge()
        self.assertIn("no recorded gate pass", self.ios("gates", "--after-merge", "module/Core").stdout)


class ModuleNameTests(FakeStackApp):
    def test_wrong_case_suggests_the_module(self) -> None:
        for args in (["core"], ["core", "--fast"], ["core", "--coverage-report"]):
            result = self.ios("gates", *args, ok=False)
            self.assertEqual(result.returncode, 2)
            self.assertIn("did you mean 'Core'", result.stderr)

    def test_unknown_module_lists_the_modules(self) -> None:
        result = self.ios("gates", "Nope", ok=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("modules: Core", result.stderr)


class FailedRerunTests(FakeStackApp):
    def test_reruns_only_what_failed(self) -> None:
        self.write("Impl.txt", "BROKEN\n")
        self.ios("gates", "Core", "--fast", ok=False)
        result = self.ios("gates", "--failed", ok=False)
        self.assertIn("rerun: Core/broken()", result.stdout)
        self.write("Impl.txt", "fixed\n")
        result = self.ios("gates", "--failed")
        self.assertIn("pass now", result.stdout)
        self.assertIn("nothing to rerun", self.ios("gates", "--failed", ok=False).stdout)
        self.assertEqual(self.passes(), [])

    def test_a_passing_run_clears_the_list(self) -> None:
        self.write("Impl.txt", "BROKEN\n")
        self.ios("gates", "Core", "--fast", ok=False)
        self.write("Impl.txt", "fixed\n")
        self.ios("gates", "Core", "--fast")
        self.assertIn("nothing to rerun", self.ios("gates", "--failed", ok=False).stdout)


class AdoptScopeTests(FakeStackApp):
    def adopt(self) -> None:
        path = self.app / ".pipeline" / "status.json"
        status = json.loads(path.read_text())
        status.update(stage=5, adopt={"state": "active", "startedAt": None, "finishedAt": None})
        path.write_text(json.dumps(status))
        commit_all(self.app, "adopting")

    def test_module_runs_are_scoped_only_while_adopting(self) -> None:
        self.assertIn("scope=\n", self.ios("gates", "Core").stdout)
        self.adopt()
        self.assertIn("scope=Core\n", self.ios("gates", "Core").stdout)
        self.assertIn("scope=Core\n", self.ios("gates", "Core", "--coverage-report").stdout)
        self.assertIn("scope=\n", self.ios("gates", "--all").stdout)


class IosFailedTestsTests(unittest.TestCase):
    def test_failed_ids(self) -> None:
        results = {"testNodes": [{"nodeType": "Test Plan", "name": "App", "children": [
            {"nodeType": "Unit test bundle", "name": "AppTests", "children": [
                {"nodeType": "Test Suite", "name": "StoreTests", "nodeIdentifier": "StoreTests", "children": [
                    {"nodeType": "Test Case", "name": "saves()", "nodeIdentifier": "StoreTests/saves()",
                     "result": "Failed", "children": [{"nodeType": "Arguments", "result": "Failed"}]},
                    {"nodeType": "Test Case", "name": "loads()", "nodeIdentifier": "StoreTests/loads()",
                     "result": "Passed"},
                ]},
            ]},
            {"nodeType": "UI test bundle", "name": "AppUITests", "children": [
                {"nodeType": "Test Suite", "name": "JourneyTests", "children": [
                    {"nodeType": "Test Case", "nodeIdentifier": "JourneyTests/testAddHabit()",
                     "result": "Failed"},
                ]},
            ]},
        ]}]}
        self.assertEqual(failed_ids(results),
                         ["AppTests/StoreTests/saves()", "AppUITests/JourneyTests/testAddHabit()"])
        self.assertEqual(failed_ids({}), [])

    def test_count(self) -> None:
        count = load("failed_tests").test_count
        self.assertEqual(count({"totalTestCount": 0, "result": "unknown"}), 0)
        self.assertEqual(count({"totalTestCount": 3}), 3)
        self.assertIsNone(count({}))

    def test_zero_tests_fail_the_run(self) -> None:
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp)
            xcrun = bin_dir / "xcrun"
            for summary, expected in (('{"totalTestCount": 0}', 1), ('{"totalTestCount": 2}', 0), ("not json", 0)):
                with self.subTest(summary=summary):
                    xcrun.write_text(f"#!/bin/bash\necho '{summary}'\n")
                    xcrun.chmod(0o755)
                    script = (f'PATH="{bin_dir}:$PATH"; STACK_HOME="{PIPELINE}/stacks/ios"\n'
                              f'source <(sed -n "/^ios_tests_ran() {{/,/^}}/p" "{PIPELINE}/stacks/ios/gates.sh")\n'
                              "ios_tests_ran unit.xcresult\n")
                    result = run("bash", "-c", script, cwd=bin_dir)
                    self.assertEqual(result.returncode, expected, result.stderr)
                    if expected:
                        self.assertIn("no tests ran", result.stderr)

    def test_a_runner_that_failed_to_launch_is_not_a_test(self) -> None:
        results = {"testNodes": [{"nodeType": "Unit test bundle", "name": "AppTests", "children": [
            {"nodeType": "Test Case", "nodeIdentifier": "App encountered an error", "result": "Failed"}]}]}
        self.assertEqual(failed_ids(results), [])


class IosCoverageTests(unittest.TestCase):
    def test_asks_xccov_for_the_path_the_bundle_recorded(self) -> None:
        import tempfile
        from pathlib import Path
        coverage = load("coverage")
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp).resolve() / "real"
            real.mkdir()
            (real / "Counter.swift").write_text("x\n")
            link = Path(tmp).resolve() / "link"
            link.symlink_to(real)
            asked = []

            def fake_xccov(*args: str) -> str:
                asked.append(args)
                if args[0] == "--file-list":
                    return f"{link}/Counter.swift\n"   # the bundle saw the symlinked path
                return "    1: 0\n    2: 3\n"

            coverage.xccov = fake_xccov
            found, missing = coverage.uncovered(real, [real / "Counter.swift"], Path("unit.xcresult"))
            self.assertEqual(missing, [])
            self.assertEqual(found, {real / "Counter.swift": [1]})
            self.assertEqual(asked[-1][:2], ("--file", f"{link}/Counter.swift"))


class IosOtherSuitesTests(TempDirTest, unittest.TestCase):
    def test_other_modules_suites(self) -> None:
        for module, suite in (("Core", "CoreTests"), ("Sync", "SyncTests"), ("UI", "ScreenTests")):
            (self.tmp / "Tests" / module).mkdir(parents=True)
            (self.tmp / "Tests" / module / "A.swift").write_text(f"struct {suite} {{}}\n")
        script = (f'module_tests() {{ echo "{self.tmp}/Tests/$1"; }}\n'
                  'module_names() { printf "Core\\nSync\\nUI\\n"; }\n'
                  f'source <(sed -n "/^ios_module_suites() {{/,/^}}/p" "{PIPELINE}/stacks/ios/gates.sh")\n'
                  f'source <(sed -n "/^ios_other_suites() {{/,/^}}/p" "{PIPELINE}/stacks/ios/gates.sh")\n'
                  "ios_other_suites Sync\n")
        result = run("bash", "-c", script, cwd=self.tmp)
        self.assertEqual(result.stdout.split(), ["CoreTests", "ScreenTests"])


if __name__ == "__main__":
    unittest.main()
