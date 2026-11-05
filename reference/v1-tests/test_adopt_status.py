"""Adopting an existing app: `status adopt start|finish|abandon`, adopt/ refs, and BASE_BRANCH."""

import json
import unittest

from helpers import PIPELINE, TempDirTest, commit_all, git_repo, run

CLI = str(PIPELINE / "bin" / "ios-pipeline")

OUTLINE = """## Build order
1. Core (depends on: none)
## Modules
### Core
- Files: Store.swift
"""


class AdoptStatusTests(TempDirTest, unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.app = git_repo(self.tmp / "Legacy")
        run("git", "switch", "-q", "-c", "develop", cwd=self.app, check=True)
        for path, text in (("Legacy/LegacyApp.swift", "@main struct LegacyApp {}\n"),
                           ("Legacy/Old.swift", "struct Old {}\n"),
                           ("LegacyTests/OldTests.swift", "struct OldTests {}\n")):
            (self.app / path).parent.mkdir(parents=True, exist_ok=True)
            (self.app / path).write_text(text)
        self.ios("init", ".")
        with (self.app / ".pipeline" / "config.sh").open("a") as config:
            config.write('STACK="ios"\nBASE_BRANCH="develop"\nAPP_SOURCE_DIR="Legacy"\nAPP_TEST_DIR="LegacyTests"\n')
        commit_all(self.app, "existing app")

    def ios(self, *args: str, ok: bool = True):
        result = run(CLI, *args, cwd=self.app)
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
        return result

    def out(self, *args: str) -> str:
        return self.ios(*args).stdout.strip()

    def status(self) -> dict:
        return json.loads((self.app / ".pipeline" / "status.json").read_text())

    def start(self) -> None:
        self.ios("status", "adopt", "start")
        commit_all(self.app, "start adoption")
        run("git", "switch", "-q", "-c", "adopt/main", cwd=self.app, check=True)

    def test_trunk_comes_from_base_branch(self) -> None:
        self.assertEqual(self.out("status", "ref", "trunk"), "develop")
        self.assertEqual(self.out("status", "ref", "base"), "develop")
        self.assertEqual(self.out("status", "ref", "module", "Core"), "module/Core")

    def test_start_needs_a_clean_tree_on_the_trunk(self) -> None:
        (self.app / "Legacy" / "Old.swift").write_text("struct Changed {}\n")
        self.assertIn("clean tree", self.ios("status", "adopt", "start", ok=False).stderr)
        run("git", "checkout", "--", "Legacy/Old.swift", cwd=self.app, check=True)
        run("git", "switch", "-q", "-c", "elsewhere", cwd=self.app, check=True)
        self.assertIn("git switch develop", self.ios("status", "adopt", "start", ok=False).stderr)

    def test_start_refuses_an_app_the_pipeline_already_built(self) -> None:
        self.ios("status", "stage", "2")
        commit_all(self.app)
        self.assertIn("already started", self.ios("status", "adopt", "start", ok=False).stderr)

    def test_adoption_uses_adopt_refs_and_its_own_steps(self) -> None:
        self.start()
        self.assertEqual(self.status()["stage"], 1)
        self.assertEqual(self.out("status", "ref", "base"), "adopt/main")
        self.assertEqual(self.out("status", "ref", "module", "Core"), "adopt/module/Core")
        self.assertEqual(self.out("status", "ref", "tag", "baseline"), "adopt/baseline")
        self.assertEqual(self.out("status", "ref", "trunk"), "develop")
        self.assertIn("adoption stage 1", self.out("status", "next"))
        self.ios("status", "stage", "2")
        self.assertIn("adoption stage 2", self.out("status", "next"))
        for checkpoint, hint in (("outline-approved", "adopt setup"), ("setup", "stage 3: baseline"),
                                 ("baseline", "stage 4"), ("scaffold", "adopt the modules")):
            self.assertIn(f"tag adopt/{checkpoint}", self.out("status", "checkpoint", checkpoint))
            self.assertIn(hint, self.out("status", "next"))
        self.assertIn("adopt s2", self.out("status", "progress"))

    def test_next_step_points_back_to_the_adopt_branch(self) -> None:
        self.start()
        run("git", "switch", "-q", "develop", cwd=self.app, check=True)
        self.assertIn("git switch adopt/main", self.out("status", "next"))

    def test_features_queue_during_adoption_but_start_only_after_it(self) -> None:
        self.start()
        self.ios("feature", "add", "Widgets: home screen")
        self.assertIn("after the adoption finishes", self.ios("feature", "start", ok=False).stderr)

    def test_finish_makes_a_normal_app(self) -> None:
        self.start()
        (self.app / "docs" / "outline.md").write_text(OUTLINE)
        self.ios("status", "init-modules")
        self.ios("status", "stage", "6")
        self.assertIn("not adopted: Core", self.ios("status", "adopt", "finish", ok=False).stderr)
        self.ios("status", "module", "Core", "done")
        self.assertIn("legacy code is left", self.ios("status", "adopt", "finish", ok=False).stderr)
        listing = self.ios("status", "adopt", "legacy", ok=False).stdout
        for item in ("Legacy/LegacyApp.swift", "Legacy/Old.swift", "LegacyTests/OldTests.swift"):
            self.assertIn(item, listing)
        # Adopt: the module replaces Old.swift and its old test; the entry point is app shell.
        (self.app / "Legacy" / "Old.swift").unlink()
        (self.app / "LegacyTests" / "OldTests.swift").unlink()
        (self.app / "Legacy" / "Modules" / "Core").mkdir(parents=True)
        (self.app / "Legacy" / "Modules" / "Core" / "Store.swift").write_text("struct LegacyStore {}\n")
        (self.app / "LegacyTests" / "Core").mkdir()
        (self.app / "LegacyTests" / "Core" / "StoreTests.swift").write_text("struct StoreTests {}\n")
        with (self.app / "docs" / "outline.md").open("a") as memo:
            memo.write("## Legacy code\n- App shell: `LegacyApp.swift`, Assets.xcassets/\n")
        self.assertIn("LegacyStore (Legacy/Modules/Core/Store.swift)",
                      self.ios("status", "adopt", "legacy", ok=False).stdout)
        (self.app / "Legacy" / "Modules" / "Core" / "Store.swift").write_text("struct Store {}\n")
        self.assertIn("legacy: empty", self.out("status", "adopt", "legacy"))
        self.ios("feature", "add", "Widgets")
        self.assertIn("git merge --no-ff adopt/main", self.out("status", "adopt", "finish"))
        status = self.status()
        self.assertEqual(status["adopt"]["state"], "finished")
        self.assertIn("app-accepted", status["checkpoints"])
        self.assertEqual(self.out("status", "ref", "base"), "develop")
        commit_all(self.app, "adopted")
        run("git", "switch", "-q", "develop", cwd=self.app, check=True)
        run("git", "merge", "-q", "--no-ff", "adopt/main", "-m", "adopt", cwd=self.app, check=True)
        self.assertIn("git switch -c feature/widgets/main", self.out("feature", "start"))

    def test_app_shell_tests_are_not_old_tests(self) -> None:
        for path in ("LegacyTests/ShellTests.swift", "LegacyTests/.swiftlint.yml", "LegacyTests/Fixtures/a.storekit"):
            (self.app / path).parent.mkdir(parents=True, exist_ok=True)
            (self.app / path).write_text("x\n")
        commit_all(self.app, "shell tests")
        self.start()
        listing = self.ios("status", "adopt", "legacy", ok=False).stdout
        for item in ("ShellTests.swift", ".swiftlint.yml", "Fixtures/a.storekit"):
            self.assertIn(item, listing)
        with (self.app / "docs").joinpath("outline.md").open("w") as memo:
            memo.write("## Legacy code\n- App shell: `LegacyApp.swift`\n"
                       "- App shell tests: `ShellTests.swift`, .swiftlint.yml, Fixtures/\n")
        listing = self.ios("status", "adopt", "legacy", ok=False).stdout
        for item in ("ShellTests.swift", ".swiftlint.yml", "Fixtures"):
            self.assertNotIn(item, listing)
        self.assertIn("LegacyTests/OldTests.swift", listing)

    def test_adopted_modules_get_a_switch_over_unit(self) -> None:
        memo = OUTLINE.replace("- Files: Store.swift\n", "- Files: Store.swift | Sync.swift\n"
                               "- Legacy files: Old.swift\n- Callers to repoint: `A.swift`, B.swift\n")
        self.start()
        (self.app / "docs" / "outline.md").write_text(memo)
        listing = self.out("status", "init-modules")
        self.assertIn("unit 3: switch-over (callers: A.swift, B.swift)", listing)
        units = self.status()["modules"][0]["units"]
        self.assertEqual([u.get("kind") for u in units], [None, None, "switch-over"])
        for number in (1, 2):
            self.ios("status", "unit", "Core", str(number), "done")
        self.ios("status", "stage", "5")
        self.assertIn("switch-over; callers: A.swift, B.swift): legacy-test scan", self.out("status", "next"))
        self.ios("status", "init-modules", "--force")
        self.assertEqual([u["state"] for u in self.status()["modules"][0]["units"]], ["done", "done", "pending"])

    def test_switch_over_units_exist_only_while_adopting(self) -> None:
        memo = OUTLINE.replace("- Files: Store.swift\n", "- Files: Store.swift\n- Legacy files: Old.swift\n")
        (self.app / "docs" / "outline.md").write_text(memo)
        self.assertNotIn("switch-over", self.out("status", "init-modules"))

    def test_finish_waits_for_verify(self) -> None:
        self.start()
        self.assertIn("finish after verify", self.ios("status", "adopt", "finish", ok=False).stderr)

    def test_abandon_keeps_the_trunk_and_carries_the_backlog(self) -> None:
        self.start()
        self.ios("feature", "add", "Widgets")
        self.ios("status", "stage", "3")
        commit_all(self.app, "queued on adopt/main")
        run("git", "switch", "-q", "develop", cwd=self.app, check=True)
        result = self.out("status", "adopt", "abandon")
        self.assertIn("carried over from adopt/main: widgets", result)
        status = self.status()
        self.assertEqual((status["stage"], status["adopt"]["state"]), (0, "abandoned"))
        self.assertEqual(self.out("status", "ref", "base"), "develop")
        self.assertEqual([f["slug"] for f in status["features"]], ["widgets"])


if __name__ == "__main__":
    unittest.main()
