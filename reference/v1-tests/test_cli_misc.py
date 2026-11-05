import unittest

from helpers import PIPELINE, TempDirTest, git_repo, run

from features import parse_backlog, slugify

CLI = str(PIPELINE / "bin" / "ios-pipeline")


class InitLocationTests(TempDirTest, unittest.TestCase):
    def test_subfolder_of_app_is_refused_before_anything_is_created(self) -> None:
        app = git_repo(self.tmp / "AlarmingRoutines")
        result = run(CLI, "init", "AlarmingRoutines", cwd=app)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ios-pipeline init .", result.stderr)
        self.assertFalse((app / "AlarmingRoutines").exists())

    def test_init_dot_relinks_the_current_app(self) -> None:
        app = git_repo(self.tmp / "App")
        result = run(CLI, "init", ".", cwd=app)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((app / ".pipeline" / "config.sh").is_file())
        self.assertIn('"Bash(ios-pipeline stack *)"', (app / ".claude" / "settings.json").read_text())


class IosSuiteSelectionTests(TempDirTest, unittest.TestCase):
    """Which suites `gates <Module> --fast` runs on iOS (stacks/ios/gates.sh)."""

    def test_selection(self) -> None:
        folder = self.tmp / "Tests" / "Persistence"
        folder.mkdir(parents=True)
        (folder / "A.swift").write_text(
            "struct SwiftDataTaskRepositoryMoveTests {\n    struct NestedTests {}\n}\n"
            "@Suite(.tags(.slow)) struct BTests {}\n@Suite(\"Move (drag)\") struct CTests {}\n"
            "@MainActor final class DTests: XCTestCase {}\nstruct MoveBehavior {}\n")
        script = (f'module_tests() {{ echo "{self.tmp}/Tests/$1"; }}\n'
                  f'source <(sed -n "/^ios_module_suites() {{/,/^}}/p" "{PIPELINE}/stacks/ios/gates.sh")\n'
                  "ios_module_suites Persistence\n")
        result = run("bash", "-c", script, cwd=self.tmp)
        self.assertEqual(result.stdout.split(), ["BTests", "CTests", "DTests", "SwiftDataTaskRepositoryMoveTests"])

    def busy_run(self, busy_runs: int) -> tuple[int, int, str]:
        """ios_xcodebuild_test against an xcodebuild that is busy `busy_runs` times, then passes.
        Returns (exit status, xcodebuild runs, bootstatus waits)."""
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        counter, waits = self.tmp / "count", self.tmp / "waits"
        (bin_dir / "xcodebuild").write_text(
            f'#!/bin/bash\nn=$(cat {counter} 2>/dev/null || echo 0); echo $((n+1)) > {counter}\n'
            f'[[ $n -lt {busy_runs} ]] && {{ echo "Application failed preflight checks (Busy)"; exit 65; }}\nexit 0\n')
        (bin_dir / "xcrun").write_text(f'#!/bin/bash\n[[ "$2" == bootstatus ]] && echo w >> {waits}\nexit 0\n')
        for tool in bin_dir.iterdir():
            tool.chmod(0o755)
        script = (f'PATH="{bin_dir}:$PATH"; RESULTS="{self.tmp}"; ROOT=/; SIM_UDID=X; IOS_BUSY_WAIT=0\n'
                  f'source <(sed -n "/^ios_wait_for_simulator() {{/,/^}}/p" "{PIPELINE}/stacks/ios/gates.sh")\n'
                  f'source <(sed -n "/^ios_xcodebuild_test() {{/,/^}}/p" "{PIPELINE}/stacks/ios/gates.sh")\n'
                  f'ios_xcodebuild_test "{self.tmp}/bundle" -quiet\n')
        result = run("bash", "-c", script, cwd=self.tmp)
        wait_count = len(waits.read_text().split()) if waits.exists() else 0
        return result.returncode, int(counter.read_text()), result.stdout + f"\nwaits={wait_count}"

    def test_diagnostics_flag_only_when_set(self) -> None:
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        args = self.tmp / "args"
        (bin_dir / "xcodebuild").write_text(f'#!/bin/bash\necho "$@" >> {args}\nexit 0\n')
        (bin_dir / "xcodebuild").chmod(0o755)
        for setting in ("", "on-failure"):
            script = (f'PATH="{bin_dir}:$PATH"; RESULTS="{self.tmp}"; IOS_COLLECT_TEST_DIAGNOSTICS="{setting}"\n'
                      f'source <(sed -n "/^ios_xcodebuild_test() {{/,/^}}/p" "{PIPELINE}/stacks/ios/gates.sh")\n'
                      f'ios_xcodebuild_test "{self.tmp}/bundle" -quiet\n')
            self.assertEqual(run("bash", "-c", script, cwd=self.tmp).returncode, 0)
        plain, with_flag = args.read_text().splitlines()
        self.assertNotIn("-collect-test-diagnostics", plain)
        self.assertIn("-collect-test-diagnostics on-failure", with_flag)

    def test_busy_simulator_is_waited_for_and_retried(self) -> None:
        status, runs, out = self.busy_run(2)
        self.assertEqual((status, runs), (0, 3), out)
        self.assertIn("waits=2", out)          # waited for the simulator before each retry
        self.assertIn("attempt 3 of 3", out)

    def test_busy_retries_stop_after_three_attempts(self) -> None:
        status, runs, out = self.busy_run(5)
        self.assertEqual((status, runs), (65, 3), out)

    def test_xcode_launch_noise_is_hidden_but_logged(self) -> None:
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        noise = ("2026-10-30 16:40:35.569 xcodebuild[1:2] [MT] IDELaunchParametersSnapshot: no debugger version\n"
                 "2026-10-30 16:40:57.722 xcodebuild[1:2] [MT] IDELaunchParametersSnapshot: The operation "
                 "couldn\u2019t be completed. (DebuggerLLDB.DebuggerVersionStore.StoreError error 0.)\n")
        (bin_dir / "xcodebuild").write_text(f"#!/bin/bash\nprintf '%s' \"{noise}\"\necho real warning\nexit 3\n")
        (bin_dir / "xcodebuild").chmod(0o755)
        script = (f'PATH="{bin_dir}:$PATH"; RESULTS="{self.tmp}"; ROOT=/\n'
                  f'source <(sed -n "/^ios_xcodebuild_test() {{/,/^}}/p" "{PIPELINE}/stacks/ios/gates.sh")\n'
                  f'ios_xcodebuild_test "{self.tmp}/bundle" -quiet\n')
        result = run("bash", "-c", script, cwd=self.tmp)
        self.assertEqual(result.returncode, 3)
        self.assertEqual(result.stdout.strip(), "real warning")
        self.assertIn("StoreError", (self.tmp / "xcodebuild.log").read_text())


class AgentDefinitionTests(unittest.TestCase):
    def test_every_agent_has_frontmatter_and_its_stack_rules_exist(self) -> None:
        rules = (PIPELINE / "stacks" / "ios" / "rules.md").read_text()
        for path in sorted((PIPELINE / "agents").glob("*.md")):
            with self.subTest(agent=path.stem):
                text = path.read_text()
                self.assertTrue(text.startswith("---\n"))
                header = text.split("---\n")[1]
                self.assertIn(f"name: {path.stem}\n", header)
                self.assertIn("description: ", header)
                if f"stack rules {path.stem}" in text:
                    self.assertIn(f"\n## {path.stem}\n", rules)


class BacklogParsingTests(unittest.TestCase):
    def test_sections_and_lists(self) -> None:
        found, _ = parse_backlog("# Ideas\n## Widgets\nHome screen.\n## Siri\n")
        self.assertEqual([f["title"] for f in found], ["Widgets", "Siri"])
        found, notes = parse_backlog("- A: one\n  more\n- [x] Done\n- [ ] B\n")
        self.assertEqual([(f["title"], f["description"]) for f in found], [("A", "one\nmore"), ("B", "")])
        self.assertTrue(notes)
        found, _ = parse_backlog("## Later features\n- Watch app: wrist\n## Other\n- no\n", "later features")
        self.assertEqual([f["title"] for f in found], ["Watch app"])

    def test_slugs_are_unique(self) -> None:
        self.assertEqual(slugify("iCloud sync!", {"icloud-sync"}), "icloud-sync-2")


if __name__ == "__main__":
    unittest.main()
