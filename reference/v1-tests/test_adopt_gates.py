"""Gates while adopting an app: journey tests in full runs, owned-code warnings, the setup check."""

import importlib.util
import json
import sys
import unittest

from helpers import PIPELINE, FakeStackApp, TempDirTest, commit_all, git_repo
from test_adopt_detect import make_app


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"ios_{name}", PIPELINE / "stacks" / "ios" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


owned_warnings = load("owned_warnings").owned_warnings
ios_check = load("check").check

JOURNEYS = "UI tests (journeys"


class AdoptGateDriverTests(FakeStackApp):
    def adopt(self, stage: int) -> None:
        path = self.app / ".pipeline" / "status.json"
        status = json.loads(path.read_text())
        status.update(stage=stage, adopt={"state": "active", "startedAt": None, "finishedAt": None})
        path.write_text(json.dumps(status))
        commit_all(self.app, "adopting")

    def test_full_runs_add_journey_tests_while_adopting(self) -> None:
        self.adopt(5)
        self.assertIn(JOURNEYS, self.ios("gates", "--all").stdout)
        self.assertIn(JOURNEYS, self.ios("gates", "Core").stdout)
        self.assertNotIn(JOURNEYS, self.ios("gates", "Core", "--fast").stdout)

    def test_normal_app_and_stage_6_use_the_normal_gates(self) -> None:
        self.assertNotIn(JOURNEYS, self.ios("gates", "--all").stdout)
        self.adopt(6)
        self.assertNotIn(JOURNEYS, self.ios("gates", "--all").stdout)

    def test_failing_journey_test_fails_the_run(self) -> None:
        self.adopt(3)
        stack_gates = self.cli.parent.parent / "stacks" / "fake" / "gates.sh"
        original = stack_gates.read_text()
        try:
            stack_gates.write_text(original.replace("stack_ui_tests() { true; }", "stack_ui_tests() { false; }"))
            result = self.ios("gates", "--all", ok=False)
            self.assertIn("UI tests (journeys)", result.stdout)
            self.assertEqual(self.passes(), [])
        finally:
            stack_gates.write_text(original)


class OwnedWarningTests(TempDirTest, unittest.TestCase):
    def test_only_module_and_module_test_warnings_count(self) -> None:
        for folder in ("App/Modules/Core", "App/Legacy", "AppTests/Core", "AppTests/LegacyTests"):
            (self.tmp / folder).mkdir(parents=True)
        lines = [f"{self.tmp}/{path}:3:5: warning: {message}" for path, message in (
            ("App/Modules/Core/Store.swift", "var never mutated"),
            ("App/Legacy/Old.swift", "deprecated"),
            ("AppTests/Core/StoreTests.swift", "unused result"),
            ("AppTests/LegacyTests/OldTests.swift", "deprecated"),
        )]
        log = "\n".join(lines + lines[:1] + ["Test Suite 'All tests' passed"])
        found = owned_warnings(log, self.tmp, "App", "AppTests")
        self.assertEqual(found, ["App/Modules/Core/Store.swift:3:5: var never mutated",
                                 "AppTests/Core/StoreTests.swift:3:5: unused result"])

    def test_no_modules_yet(self) -> None:
        log = f"{self.tmp}/App/Old.swift:1:1: warning: x"
        self.assertEqual(owned_warnings(log, self.tmp, "App", "AppTests"), [])


class AdoptSetupCheckTests(TempDirTest, unittest.TestCase):
    CONFIG = {"APP_PROJECT": "Legacy.xcodeproj", "APP_SCHEME": "Legacy", "APP_MODULE": "Legacy",
              "APP_SOURCE_DIR": "Legacy", "APP_TEST_DIR": "LegacyTests", "UNIT_TEST_TARGET": "LegacyTests",
              "UI_TEST_TARGET": "LegacyUITests", "BASE_BRANCH": "main"}

    def results(self, adopting: bool) -> dict[str, bool]:
        config = {**self.CONFIG, "ADOPTING": "1" if adopting else ""}
        return {item: ok for ok, item, _ in ios_check(self.tmp, config)}

    def test_swift5_is_allowed_only_while_adopting(self) -> None:
        make_app(git_repo(self.tmp))
        commit_all(self.tmp)
        adopting = self.results(True)
        self.assertTrue(adopting["Swift Language Version 5.0 (switches to 6 in Stage 6)"])
        self.assertTrue(adopting["no Swift files listed one by one in groups"])
        self.assertTrue(adopting["trunk branch main exists"])
        self.assertFalse(self.results(False)["Swift Language Version is 6 in every target"])

    def test_test_targets_must_include_their_folders(self) -> None:
        make_app(git_repo(self.tmp))
        results = self.results(True)
        self.assertTrue(results["unit test target 'LegacyTests' includes its folder LegacyTests/"])
        self.assertFalse(results["ui test target 'LegacyUITests' includes a test folder"])  # the sample has none
        pbxproj = next(self.tmp.rglob("project.pbxproj"))
        pbxproj.write_text(pbxproj.read_text().replace("fileSystemSynchronizedGroups = (S2 /* LegacyTests */, );", ""))
        self.assertFalse(self.results(True)["unit test target 'LegacyTests' includes its folder LegacyTests/"])

    def test_groups_and_nested_repos_fail(self) -> None:
        make_app(git_repo(self.tmp), synchronized=False)
        git_repo(self.tmp / "Vendor" / "Lib")
        results = self.results(True)
        self.assertFalse(results["no Swift files listed one by one in groups"])
        self.assertFalse(results["no git repository inside the app folder"])
        self.assertFalse(results["trunk branch main exists"])  # no commit yet


if __name__ == "__main__":
    unittest.main()
