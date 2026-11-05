"""Detecting an existing app to adopt: the pbxproj reader, iOS detect.py, git findings, `stack detect`."""

import importlib.util
import json
import sys
import unittest
from pathlib import Path

from helpers import PIPELINE, TempDirTest, commit_all, git_repo, run

from git_checks import findings

CLI = str(PIPELINE / "bin" / "ios-pipeline")


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"ios_{name}", PIPELINE / "stacks" / "ios" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


pbxproj = load("pbxproj")
detect = load("detect").detect
inventory_module = load("inventory")


def project_text(swift_version: str = "5.0", synchronized: bool = True, ui_tests: bool = True,
                 isolation: str = "") -> str:
    """A small but realistic project.pbxproj for an app named Legacy."""
    sync = {"app": "fileSystemSynchronizedGroups = (S1 /* Legacy */, );" if synchronized else "",
            "tests": "fileSystemSynchronizedGroups = (S2 /* LegacyTests */, );" if synchronized else ""}
    groups = ("S1 /* Legacy */ = {isa = PBXFileSystemSynchronizedRootGroup; path = Legacy; sourceTree = \"<group>\"; };\n"
              "S2 /* LegacyTests */ = {isa = PBXFileSystemSynchronizedRootGroup; path = LegacyTests; "
              "sourceTree = \"<group>\"; };") if synchronized else (
              "F1 /* Store.swift */ = {isa = PBXFileReference; lastKnownFileType = sourcecode.swift; "
              "path = Store.swift; sourceTree = \"<group>\"; };")
    targets = ["T1 /* Legacy */", "T2 /* LegacyTests */"] + (["T3 /* LegacyUITests */"] if ui_tests else [])
    ui = """
        T3 /* LegacyUITests */ = {
            isa = PBXNativeTarget;
            buildConfigurationList = L3;
            name = LegacyUITests;
            productType = "com.apple.product-type.bundle.ui-testing";
        };
        L3 = {isa = XCConfigurationList; buildConfigurations = (C3, ); };
        C3 = {isa = XCBuildConfiguration; buildSettings = {}; name = Debug; };""" if ui_tests else ""
    extra = f'SWIFT_DEFAULT_ACTOR_ISOLATION = {isolation};' if isolation else ""
    return f"""// !$*UTF8*$!
{{
    archiveVersion = 1;
    objects = {{
        {groups}
        P0 /* Project object */ = {{
            isa = PBXProject;
            buildConfigurationList = L0 /* Build configuration list for PBXProject "Legacy" */;
            targets = ({", ".join(targets)}, );
        }};
        L0 = {{isa = XCConfigurationList; buildConfigurations = (C0 /* Debug */, ); }};
        C0 /* Debug */ = {{
            isa = XCBuildConfiguration;
            buildSettings = {{
                SDKROOT = iphoneos;
                IPHONEOS_DEPLOYMENT_TARGET = 17.0;
                OTHER_SWIFT_FLAGS = "-D \\"DEBUG\\"";
            }};
            name = Debug;
        }};
        T1 /* Legacy */ = {{
            isa = PBXNativeTarget;
            buildConfigurationList = L1;
            {sync["app"]}
            name = Legacy;
            productType = "com.apple.product-type.application";
        }};
        L1 = {{isa = XCConfigurationList; buildConfigurations = (C1, C1R, ); }};
        C1 = {{isa = XCBuildConfiguration; buildSettings = {{SWIFT_VERSION = {swift_version}; {extra}
            PRODUCT_MODULE_NAME = "$(PRODUCT_NAME:c99extidentifier)"; }}; name = Debug; }};
        C1R = {{isa = XCBuildConfiguration; buildSettings = {{SWIFT_VERSION = {swift_version}; }}; name = Release; }};
        T2 /* LegacyTests */ = {{
            isa = PBXNativeTarget;
            buildConfigurationList = L2;
            {sync["tests"]}
            name = LegacyTests;
            productType = "com.apple.product-type.bundle.unit-test";
        }};
        L2 = {{isa = XCConfigurationList; buildConfigurations = (C2, ); }};
        C2 = {{isa = XCBuildConfiguration; buildSettings = {{}}; name = Debug; }};{ui}
    }};
    rootObject = P0 /* Project object */;
}}
"""


def make_app(root: Path, **options) -> Path:
    project = root / "Legacy.xcodeproj"
    (project / "xcshareddata" / "xcschemes").mkdir(parents=True)
    (project / "project.pbxproj").write_text(project_text(**options))
    (project / "xcshareddata" / "xcschemes" / "Legacy.xcscheme").write_text("<Scheme/>\n")
    (root / "Legacy").mkdir()
    (root / "Legacy" / "LegacyApp.swift").write_text("import SwiftUI\n@main struct LegacyApp: App {}\n")
    (root / "Legacy" / "ListController.swift").write_text("import UIKit\nfinal class ListController {}\n")
    (root / "LegacyTests").mkdir()
    return root


def levels(issues, level: str) -> list[str]:
    return [item for lvl, item, _ in issues if lvl == level]


class PbxprojTests(unittest.TestCase):
    def test_parses_quotes_comments_and_settings(self) -> None:
        data = pbxproj.parse(project_text())
        settings = data["objects"]["C0"]["buildSettings"]
        self.assertEqual(settings["OTHER_SWIFT_FLAGS"], '-D "DEBUG"')
        self.assertEqual(data["rootObject"], "P0")

    def test_target_settings_fall_back_to_the_project(self) -> None:
        project = pbxproj.Project(Path("Legacy.xcodeproj"), pbxproj.parse(project_text()))
        app = project.targets()[0]
        self.assertTrue(app.is_app)
        self.assertEqual(app.setting_values("SWIFT_VERSION"), {"5.0"})
        self.assertEqual(app.setting_values("SDKROOT"), {"iphoneos"})
        self.assertEqual(app.synchronized_folders(), ["Legacy"])

    def test_malformed_input_raises(self) -> None:
        with self.assertRaises(pbxproj.PlistError):
            pbxproj.parse("{ objects = { A = { isa = X; }; ")


class IosDetectTests(TempDirTest, unittest.TestCase):
    def test_no_project(self) -> None:
        self.assertEqual(detect(self.tmp)["confidence"], 0.0)

    def test_synchronized_swift5_app(self) -> None:
        result = detect(make_app(self.tmp))
        self.assertEqual(result["confidence"], 1.0)
        self.assertEqual(result["config"], {
            "APP_PROJECT": "Legacy.xcodeproj", "APP_MODULE": "Legacy", "APP_SCHEME": "Legacy",
            "APP_SOURCE_DIR": "Legacy", "UNIT_TEST_TARGET": "LegacyTests", "APP_TEST_DIR": "LegacyTests",
            "UI_TEST_TARGET": "LegacyUITests"})
        notes = " ".join(levels(result["issues"], "note"))
        self.assertIn("Swift language version 5.0", notes)
        self.assertIn("UIKit: 1 Swift files import UIKit", notes)
        self.assertIn("no -uiTesting", notes)
        self.assertEqual(levels(result["issues"], "block") + levels(result["issues"], "fix"), [])
        self.assertIn("2 Swift files", result["summary"])

    def test_setup_fixes(self) -> None:
        root = make_app(self.tmp, synchronized=False, ui_tests=False, isolation="MainActor")
        (root / "Legacy.xcodeproj" / "xcshareddata" / "xcschemes" / "Legacy.xcscheme").unlink()
        fixes = " | ".join(levels(detect(root)["issues"], "fix"))
        for expected in ("listed in groups", "no UI test target", "scheme isn't shared", "Default Actor Isolation"):
            self.assertIn(expected, fixes)

    def test_unsupported_dependencies_block(self) -> None:
        root = make_app(self.tmp)
        (root / "Podfile").write_text("pod 'X'\n")
        (root / "Legacy" / "Bridge.m").write_text("")
        blocks = " | ".join(levels(detect(root)["issues"], "block"))
        self.assertIn("CocoaPods", blocks)
        self.assertIn("Objective-C", blocks)


class InventoryTests(TempDirTest, unittest.TestCase):
    def test_types_and_references(self) -> None:
        source, tests = self.tmp / "App", self.tmp / "AppTests"
        (source / "Modules" / "Core").mkdir(parents=True)
        tests.mkdir()
        (source / "Store.swift").write_text(
            "import Foundation\n@MainActor final class TaskStore {\n    struct Inner {}\n}\n"
            "extension TaskStore { }\n")
        (source / "ListController.swift").write_text(
            "import UIKit\nfinal class ListController: UIViewController {\n"
            "    let store = TaskStore() // not a Ghost\n    let title = \"Ghost\"\n}\n")
        (source / "Modules" / "Core" / "New.swift").write_text("struct New {}\n")
        (tests / "StoreTests.swift").write_text("import XCTest\nfinal class StoreTests { let s = TaskStore() }\n")
        data = inventory_module.inventory(self.tmp, {"APP_SOURCE_DIR": "App", "APP_TEST_DIR": "AppTests"})
        files = {f["path"]: f for f in data["files"]}
        self.assertEqual(sorted(files), ["App/ListController.swift", "App/Store.swift"])
        self.assertEqual(files["App/Store.swift"]["declares"], ["TaskStore"])
        self.assertEqual(files["App/Store.swift"]["extends"], ["TaskStore"])
        self.assertEqual(files["App/ListController.swift"]["uses"], ["TaskStore"])
        self.assertEqual(data["tests"][0]["uses"], ["TaskStore"])
        text = inventory_module.report(data)
        self.assertIn("declares: TaskStore (used by 2)", text)
        self.assertIn("ListController.swift (5 lines, UIKit)", text)


class LegacyDeclarationTests(TempDirTest, unittest.TestCase):
    def test_finds_declarations_not_mentions(self) -> None:
        path = self.tmp / "Store.swift"
        path.write_text('final class LegacyStore {}\n// struct LegacyOld\nlet s = "enum LegacyText"\n'
                        "let x = LegacyStore()\nstruct Legacyish {}\n")
        self.assertEqual(load("contract").legacy_declarations(path), ["LegacyStore"])


class GitFindingTests(TempDirTest, unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.repo = git_repo(self.tmp / "repo")
        run("git", "switch", "-q", "-c", "develop", cwd=self.repo, check=True)
        (self.repo / "a.txt").write_text("a\n")
        commit_all(self.repo)

    def test_trunk_clashes_hooks_and_dirty_tree(self) -> None:
        run("git", "tag", "module/Core", cwd=self.repo, check=True)
        hook = self.repo / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\n")
        (self.repo / "a.txt").write_text("changed\n")
        config, issues = findings(self.repo)
        self.assertEqual(config, {"BASE_BRANCH": "develop"})
        text = " | ".join(item for _, item, _ in issues)
        for expected in ("trunk: develop", "uncommitted changes", "tag module/Core", "pre-commit"):
            self.assertIn(expected, text)

    def test_submodules_block_and_nested_repos_need_fixing(self) -> None:
        git_repo(self.repo / "vendor" / "lib")
        _, issues = findings(self.repo)
        self.assertIn("nested git repository at vendor/lib", levels(issues, "fix"))
        (self.repo / ".gitmodules").write_text("")
        _, issues = findings(self.repo)
        self.assertEqual(levels(issues, "block"), ["git submodules (.gitmodules)"])


class StackDetectCliTests(TempDirTest, unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.app = git_repo(self.tmp / "app")
        run("git", "switch", "-q", "-c", "develop", cwd=self.app, check=True)
        make_app(self.app)
        self.assertEqual(run(CLI, "init", ".", cwd=self.app).returncode, 0)
        commit_all(self.app)

    def test_apply_writes_the_detected_settings(self) -> None:
        result = run(CLI, "stack", "detect", "--apply", cwd=self.app)  # the most confident stack
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        config = (self.app / ".pipeline" / "config.sh").read_text()
        for line in ('STACK="ios"', 'BASE_BRANCH="develop"', 'APP_PROJECT="Legacy.xcodeproj"',
                     'APP_SOURCE_DIR="Legacy"', 'UI_TEST_TARGET="LegacyUITests"'):
            self.assertIn(line, config)
        self.assertNotIn("MyApp", config)
        self.assertFalse((self.app / "App").exists(), "an adopted app gets no scaffold folders")
        self.assertEqual(run(CLI, "status", "ref", "trunk", cwd=self.app).stdout.strip(), "develop")

    def test_json_and_blocking_issues(self) -> None:
        result = run(CLI, "stack", "detect", "--json", cwd=self.app)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["stacks"]["ios"]["config"]["APP_SCHEME"], "Legacy")
        (self.app / "Cartfile").write_text("")
        self.assertEqual(run(CLI, "stack", "detect", cwd=self.app).returncode, 1)
        before = (self.app / ".pipeline" / "config.sh").read_text()
        result = run(CLI, "stack", "detect", "--apply", "ios", cwd=self.app)
        self.assertIn("blocking", result.stderr)
        self.assertEqual((self.app / ".pipeline" / "config.sh").read_text(), before)


if __name__ == "__main__":
    unittest.main()
