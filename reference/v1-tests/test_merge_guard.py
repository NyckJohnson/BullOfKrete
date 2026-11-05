import importlib.util
import json
import os
import subprocess
import unittest

from helpers import PIPELINE, TempDirTest, commit_all, git_repo, run

spec = importlib.util.spec_from_file_location("merge_guard", PIPELINE / "workflow" / "hooks" / "merge-guard.py")
merge_guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(merge_guard)


class MergeTargetTests(unittest.TestCase):
    CASES = {
        'git switch main && git merge --no-ff module/Persistence -m "Merge module/Persistence" 2>&1 | tail -3 && echo ok':
            ["module/Persistence"],
        "git merge --no-ff module/Persistence -m \"Merge module/Persistence\"": ["module/Persistence"],
        "git merge x>/dev/null; git merge y 2> err.log": ["x", "y"],
        "git -C app merge --no-ff -X ours -s recursive b1 b2 &": ["b1", "b2"],
        'git merge -m "msg with 2>&1 and && in it" z': ["z"],
        "GIT_EDITOR=true git merge feature/a/main": ["feature/a/main"],
        "(cd x && git merge q) | cat": ["q"],
        'echo "git merge fake"': [],
        "git merge --abort": [],
        "git log --merges": [],
        "git mergetool": [],
    }

    def test_targets(self) -> None:
        for command, expected in self.CASES.items():
            with self.subTest(command=command):
                self.assertEqual(merge_guard.merge_targets(command), expected)


class HookTests(TempDirTest, unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.app = git_repo(self.tmp / "app")
        (self.app / ".pipeline").mkdir()
        (self.app / ".pipeline" / "config.sh").write_text('STACK="ios"\n')
        commit_all(self.app)
        run("git", "branch", "module/Persistence", cwd=self.app, check=True)

    def hook(self, command: str) -> int:
        """Run the hook as Claude Code does: hook JSON on stdin; exit 2 blocks."""
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(self.app)}
        result = subprocess.run(["python3", str(PIPELINE / "workflow" / "hooks" / "merge-guard.py")],
                                input=payload, capture_output=True, text=True, env=env, cwd=self.app)
        self.last_error = result.stderr
        return result.returncode

    COMPOUND = 'git switch main && git merge --no-ff module/Persistence -m "Merge" 2>&1 | tail -3'

    def test_blocks_without_pass(self) -> None:
        self.assertEqual(self.hook(self.COMPOUND), 2)
        self.assertIn("module/Persistence", self.last_error)
        self.assertNotIn("2>&1", self.last_error)

    def test_allows_compound_with_pass(self) -> None:
        sha = run("git", "rev-parse", "module/Persistence", cwd=self.app, check=True).stdout.strip()
        (self.app / ".pipeline" / "gates").mkdir()
        (self.app / ".pipeline" / "gates" / f"{sha}.pass").touch()
        self.assertEqual(self.hook(self.COMPOUND), 0)

    def test_unknown_ref_is_blocked(self) -> None:
        self.assertEqual(self.hook("git merge module/Nope"), 2)
        self.assertIn("unknown", self.last_error)


if __name__ == "__main__":
    unittest.main()
