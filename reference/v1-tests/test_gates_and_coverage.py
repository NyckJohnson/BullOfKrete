"""The generic gate driver and coverage report, run against a throwaway fake stack
(.txt sources, '#' comments) in a copy of the pipeline."""

import unittest

from helpers import FakeStackApp, commit_all, git_repo


class GateTests(FakeStackApp):
    # ---- coverage ----

    def test_declaration_only_file_with_marker_passes(self) -> None:
        result = self.ios("gates", "Core")
        self.assertIn("1 declaration-only file(s) exempt", result.stdout)

    def test_file_without_data_and_without_marker_fails(self) -> None:
        self.write("Impl.txt", "real code\nNODATA\n")
        commit_all(self.app)
        result = self.ios("gates", "Core", ok=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Files without coverage data", result.stdout)
        self.assertIn("src/Modules/Core/Impl.txt", result.stdout)
        self.assertIn("# coverage-exempt-file:", result.stdout)  # hint uses the stack's comment

    def test_marker_does_not_hide_uncovered_code(self) -> None:
        self.write("Impl.txt", "# coverage-exempt-file: wrongly marked\nUNCOVERED line\n")
        commit_all(self.app)
        result = self.ios("gates", "Core", ok=False)
        self.assertIn("Impl.txt:2", result.stdout)
        self.assertIn("unnecessary file marker", result.stdout)

    def test_line_and_block_markers(self) -> None:
        self.write("Impl.txt", "UNCOVERED # coverage-exempt: callback\n# coverage-exempt-begin: os\n"
                               "UNCOVERED\n# coverage-exempt-end\n")
        commit_all(self.app)
        self.ios("gates", "Core")

    def test_exclude_extra_adds_to_default(self) -> None:
        self.write("Generated/Gen.txt", "UNCOVERED\n")
        commit_all(self.app)
        self.ios("gates", "Core", ok=False)
        config = self.app / ".pipeline" / "config.sh"
        config.write_text(config.read_text() + "COVERAGE_EXCLUDE_REGEX='/Mocks/'\nCOVERAGE_EXCLUDE_EXTRA='/Generated/'\n")
        commit_all(self.app)
        self.ios("gates", "Core")

    # ---- merge passes ----

    def test_only_full_runs_record_a_pass(self) -> None:
        for args in (("Core", "--fast"), ("Core", "--skip-coverage"), ("--all", "--skip-coverage"),
                     ("--app-ui-tests",)):
            with self.subTest(args=args):
                result = self.ios("gates", *args)
                self.assertIn("pass not recorded", result.stdout)
                self.assertEqual(self.passes(), [])
        self.ios("gates", "Core")
        self.assertEqual(len(self.passes()), 1)

    def test_dirty_tree_records_nothing(self) -> None:
        self.write("Impl.txt", "changed\n")
        result = self.ios("gates", "--all")
        self.assertIn("uncommitted changes", result.stdout)
        self.assertEqual(self.passes(), [])

    def test_failures(self) -> None:
        self.write("Impl.txt", "BROKEN\n")
        commit_all(self.app)
        self.assertIn("build/test (fast)", self.ios("gates", "Core", "--fast", ok=False).stdout)
        self.write("Impl.txt", "fine\n")
        self.write("Contracts/Store.txt", "# coverage-exempt-file: x\napi load(changed)\nNODATA\n")
        commit_all(self.app)
        self.assertIn("public API changed", self.ios("gates", "Core", ok=False).stdout)

    def test_nested_repo_is_refused(self) -> None:
        git_repo(self.app / "src" / "inner")
        result = self.ios("gates", "--all", ok=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("nested git repo", result.stderr)


if __name__ == "__main__":
    unittest.main()
