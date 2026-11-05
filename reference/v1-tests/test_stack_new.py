"""`ios-pipeline stack new` and `stacks/_template/` (stacks/README.md "Adding a stack")."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import pipeline_copy, run


class StackNewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.home = Path(cls._tmp.name) / "pipeline"
        cls.cli = str(pipeline_copy(cls.home))

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def new(self, name: str, cwd: Path | None = None):
        return run(self.cli, "stack", "new", name, cwd=cwd or self.home)

    def test_scaffolds_from_the_template(self) -> None:
        result = self.new("widget")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        stack = self.home / "stacks" / "widget"
        manifest = (stack / "stack.sh").read_text()
        self.assertIn('STACK_MATURITY="experimental"', manifest)
        self.assertIn("TODO", manifest)   # the human fills these in during design
        design = (stack / "DESIGN.md").read_text()
        self.assertIn("# widget stack: design", design)   # <name> replaced
        self.assertIn("ios-pipeline stack new widget", design)
        self.assertTrue((stack / "cases.json").is_file())
        # nothing else is scaffolded: every other file is authored fresh, not copied
        self.assertEqual(sorted(p.name for p in stack.iterdir()), ["DESIGN.md", "cases.json", "stack.sh"])

    def test_refuses_an_existing_name(self) -> None:
        self.new("dup")
        result = self.new("dup")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already exists", result.stderr)

    def test_refuses_an_invalid_name(self) -> None:
        for bad in ("Bad-Name", "has space", "UPPER"):
            result = self.new(bad)
            self.assertNotEqual(result.returncode, 0, bad)
            self.assertIn("isn't a valid stack name", result.stderr)
            self.assertFalse((self.home / "stacks" / bad).exists())

    def test_refuses_the_reserved_template_name(self) -> None:
        result = self.new("_template")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("isn't a valid stack name", result.stderr)

    def test_refuses_inside_an_app(self) -> None:
        app = self.home.parent / "an-app"
        run(self.cli, "init", str(app), cwd=self.home, check=True)
        result = self.new("widget2", cwd=app)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("never inside an app", result.stderr)
        self.assertFalse((self.home / "stacks" / "widget2").exists())

    def test_template_is_not_a_stack(self) -> None:
        result = run(self.cli, "stacks", cwd=self.home)
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("_template", result.stdout)
        self.assertIn("ios:", result.stdout)   # the real stack is still listed


if __name__ == "__main__":
    unittest.main()
