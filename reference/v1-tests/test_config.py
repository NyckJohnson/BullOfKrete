import contextlib
import io
import subprocess
import unittest

from helpers import TempDirTest

import pipeline_common as pc


class ShellValueTests(unittest.TestCase):
    CASES = [
        '"/Views/|/Mocks/|View\\.swift$"',
        "'/Views/|/Mocks/|View\\.swift$'",
        "plain",
        '"a\\"b"',
        "'it'\\''s'",
        '"x" # comment',
        '""',
        "''",
        "with\\ space",
        '"back\\\\slash"',
    ]

    def test_matches_bash(self) -> None:
        for raw in self.CASES:
            with self.subTest(raw=raw):
                bash = subprocess.run(["bash", "-c", f"K={raw}\nprintf %s \"$K\""],
                                      capture_output=True, text=True, check=True).stdout
                value, problem = pc.parse_shell_value(raw)
                self.assertEqual(value, bash)
                self.assertIsNone(problem)

    def test_reports_what_bash_reads_differently(self) -> None:
        for raw in ('"$HOME/x"', "${X}", "two words", "'open", '"open'):
            with self.subTest(raw=raw):
                self.assertIsNotNone(pc.parse_shell_value(raw)[1])

    def test_literal_dollar_is_fine(self) -> None:
        self.assertEqual(pc.parse_shell_value('"end$"'), ("end$", None))


class ConfigFileTests(TempDirTest, unittest.TestCase):
    def test_single_quotes_and_warnings(self) -> None:
        path = self.tmp / "config.sh"
        path.write_text("# comment\nA='/Views/|x'\nexport B=\"y\"\nMAX_ATTEMPTS = 5\nreview_mode=split\nC=$HOME\n")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            config = pc._parse_config(path)
        self.assertEqual(config["A"], "/Views/|x")
        self.assertEqual(config["B"], "y")
        self.assertEqual(config["C"], "$HOME")
        self.assertNotIn("MAX_ATTEMPTS", config)
        self.assertIn("MAX_ATTEMPTS = 5", err.getvalue())
        self.assertIn("review_mode=split", err.getvalue())
        self.assertIn("C:", err.getvalue())

    def test_layers_pipeline_stack_app(self) -> None:
        (self.tmp / ".pipeline").mkdir()
        (self.tmp / ".pipeline" / "config.sh").write_text(
            'STACK="ios"\nCOVERAGE_EXCLUDE_EXTRA=\'/Generated/\'\nMAX_ATTEMPTS="5"\n')
        config = pc.load_config(self.tmp)
        self.assertEqual(config["MAX_ATTEMPTS"], "5")                        # app overrides pipeline
        self.assertEqual(config["COVERAGE_EXCLUDE_REGEX"], "/Views/|/Mocks/|View\\.swift$")  # stack default kept
        self.assertEqual(config["COVERAGE_EXCLUDE_EXTRA"], "/Generated/")


if __name__ == "__main__":
    unittest.main()
