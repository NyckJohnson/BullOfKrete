"""Parts: several stacks in one app (docs/stacks.md), and one-part apps unchanged."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import FakeStackApp, commit_all, git_repo, run

import parts

TWO_PART_OUTLINE = """## Build order
1. Core (depends on: none)
2. Sync (depends on: {sync_deps})
## Modules
### Core
- Part: app
- Files: Store.txt, Impl.txt
### Sync
{sync_part}
- Files: Push.txt
"""


class PartsTests(FakeStackApp):
    """An app on the fake stack (part `app`), to which tests add a part `api` on the `other` stack."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        stacks = cls.cli.parent.parent / "stacks"
        (stacks / "fake" / "gitignore").write_text("# fake\nbuild/\n/out/\nlib/gen/\n")
        (stacks / "fake" / "defaults.sh").write_text('FAKE_OPT="a"\n')
        shutil.copytree(stacks / "fake", stacks / "other")
        manifest = stacks / "other" / "stack.sh"
        manifest.write_text(manifest.read_text().replace('STACK_TITLE="Fake"', 'STACK_TITLE="Other"')
                            + 'STACK_KIND="tool"\nSTACK_TEST_GLOB="*_test.txt"\n')
        # No journey layer: whether UI tests run is decided by defining stack_ui_tests, not STACK_KIND.
        gates = stacks / "other" / "gates.sh"
        gates.write_text(gates.read_text().replace('stack_ui_tests() { true; }\n', ''))

    def add_api(self) -> None:
        self.ios("part", "add", "api", "other")

    def outline(self, sync_part: str = "- Part: api", sync_deps: str = "none") -> None:
        (self.app / "docs" / "outline.md").write_text(
            TWO_PART_OUTLINE.format(sync_part=sync_part, sync_deps=sync_deps))

    def config(self, relative: str) -> str:
        return (self.app / ".pipeline" / relative).read_text()

    # ---- one-part apps ----

    def test_implicit_part(self) -> None:
        out = self.ios("part", "list").stdout
        self.assertIn("app: fake in ./", out)
        self.assertIn("settings in .pipeline/config.sh", out)
        self.assertFalse((self.app / ".pipeline" / "parts").exists())
        self.assertIn("plain", self.ios("stack", "rules").stdout)  # no --part needed

    # ---- adding a part ----

    def test_add_moves_the_implicit_part(self) -> None:
        config = self.app / ".pipeline" / "config.sh"
        config.write_text(config.read_text() + 'FAKE_OPT="b"\nMAX_ATTEMPTS="5"\n')
        self.add_api()
        app_part, api_part, app_config = self.config("parts/app.sh"), self.config("parts/api.sh"), self.config("config.sh")
        for line in ('STACK="fake"', 'PART_DIR="."', 'APP_SOURCE_DIR="src"', 'FAKE_OPT="b"'):
            self.assertIn(line, app_part)
        for line in ('STACK="other"', 'PART_DIR="api"', 'APP_SOURCE_DIR="src"'):
            self.assertIn(line, api_part)
        self.assertNotIn("APP_SOURCE_DIR", app_config)
        self.assertNotIn("FAKE_OPT", app_config)
        self.assertNotIn('STACK="fake"', app_config)
        self.assertIn('MAX_ATTEMPTS="5"', app_config)  # app-wide settings stay
        self.assertTrue((self.app / "api" / "src" / ".gitkeep").is_file())
        ignore = (self.app / ".gitignore").read_text()
        self.assertIn("/api/out/", ignore)
        self.assertIn("/api/lib/gen/", ignore)
        out = self.ios("part", "list").stdout
        self.assertIn("app: fake in ./", out)
        self.assertIn("api: other in api/", out)

    def test_existing_modules_still_resolve_after_the_move(self) -> None:
        self.add_api()
        status = json.loads(self.config("status.json"))
        self.assertEqual([m.get("part") for m in status["modules"]], ["app"])
        self.assertIn("load()", self.ios("api", "Core").stdout)

    def test_rejects_bad_names_and_folders(self) -> None:
        self.add_api()
        cases = [
            (("Web", "other"), "lowercase"),
            (("web", "nope"), "unknown stack"),
            (("api", "other", "--dir", "other"), "already has a part"),
            (("web", "other", "--dir", "src"), "overlap"),          # the app part's source folder
            (("web", "other", "--dir", "api/web"), "overlap"),      # inside another part
            (("web", "other", "--dir", "."), "overlap"),            # the app folder holds part app
            (("web", "other", "--dir", "docs"), "whole app"),
            (("web", "other", "--dir", "../web"), "outside the app"),
        ]
        for args, message in cases:
            with self.subTest(args=args):
                result = self.ios("part", "add", *args, ok=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stdout + result.stderr)
        self.assertFalse((self.app / ".pipeline" / "parts" / "web.sh").exists())

    def test_check(self) -> None:
        self.add_api()
        self.assertIn("all good", self.ios("part", "check").stdout)
        api = self.app / ".pipeline" / "parts" / "api.sh"
        api.write_text(api.read_text().replace('PART_DIR="api"', 'PART_DIR="src/api"'))
        result = self.ios("part", "check", ok=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("overlap", result.stdout)

    def test_stack_select_refused_once_parts_exist(self) -> None:
        self.add_api()
        result = self.ios("stack", "select", "other", ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("part add", result.stderr)

    # ---- stack commands per part ----

    def test_stack_commands_take_part(self) -> None:
        self.add_api()
        result = self.ios("stack", "rules", ok=False)
        self.assertIn("several parts", result.stderr)
        self.assertIn("plain", self.ios("stack", "rules", "--part", "api").stdout)
        self.assertIn("STACK_TITLE=Other", self.ios("stack", "show", "--part", "api").stdout)
        self.assertIn("no part 'web'", self.ios("stack", "rules", "--part", "web", ok=False).stderr)
        out = self.ios("stack", "check").stdout  # every part
        self.assertIn("part app (fake)", out)
        self.assertIn("part api (other)", out)
        self.assertIn("(this app: api)", self.ios("stacks").stdout)

    # ---- memo and status ----

    def test_modules_get_their_part(self) -> None:
        self.add_api()
        self.outline()
        self.ios("status", "init-modules", "--force")
        status = json.loads(self.config("status.json"))
        sync = next(m for m in status["modules"] if m["name"] == "Sync")
        core = next(m for m in status["modules"] if m["name"] == "Core")
        self.assertEqual((sync["part"], sync["path"]), ("api", "api/src/Modules/Sync"))
        self.assertEqual((core["part"], core["path"]), ("app", "src/Modules/Core"))
        summary = self.ios("status", "summary").stdout
        self.assertIn("part app (fake)", summary)
        self.assertIn("part api (other)", summary)

        contract = self.app / "api" / "src" / "Modules" / "Sync" / "Contracts" / "Push.txt"
        contract.parent.mkdir(parents=True)
        contract.write_text("api push()\n")
        self.assertIn("push()", self.ios("api", "Sync").stdout)  # the module's own part and stack

    def test_memo_part_problems(self) -> None:
        self.add_api()
        cases = [
            ({"sync_part": ""}, "Sync has no '- Part:' line"),
            ({"sync_part": "- Part: web"}, "part 'web', which this app doesn't have"),
            ({"sync_deps": "Core"}, "different parts"),
        ]
        for kwargs, message in cases:
            with self.subTest(kwargs=kwargs):
                self.outline(**kwargs)
                result = self.ios("status", "init-modules", "--force", ok=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)

    # ---- gates ----

    def two_part_app(self) -> Path:
        """Parts app (Core) and api (Sync, on the `other` stack, kind tool), set up and committed."""
        self.add_api()
        self.outline()
        sync = self.app / "api" / "src" / "Modules" / "Sync"
        (sync / "Contracts").mkdir(parents=True)
        (sync / "Contracts" / "Push.txt").write_text("# coverage-exempt-file: declarations only\napi push()\nNODATA\n")
        (sync / "Push.txt").write_text("fine\n")
        self.ios("status", "init-modules", "--force")
        self.ios("api", "Sync", "--write")
        commit_all(self.app)
        return sync

    def test_gates_run_the_module_part(self) -> None:
        self.two_part_app()
        out = self.ios("gates", "Sync").stdout
        self.assertIn("part api (other)", out)
        self.assertNotIn("part app", out)
        self.assertIn("GATES: PASS", out)
        self.assertEqual(len(self.passes()), 1)
        self.assertIn("part app (fake)", self.ios("gates", "Core").stdout)

    def test_gates_all_covers_every_part(self) -> None:
        sync = self.two_part_app()
        self.assertIn("GATES: PASS", self.ios("gates", "--all").stdout)
        (sync / "Push.txt").write_text("BROKEN\n")
        commit_all(self.app)
        result = self.ios("gates", "--all", ok=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("part app (fake)", result.stdout)
        self.assertIn("  - api: build/test", result.stdout)
        self.assertNotIn("  - build/test", result.stdout)   # the app part passed

    def test_failed_tests_rerun_in_their_part(self) -> None:
        sync = self.two_part_app()
        (sync / "Push.txt").write_text("BROKEN\n")
        self.ios("gates", "Sync", "--fast", ok=False)
        failed = self.app / ".pipeline" / "results" / "failed-tests-api.txt"
        self.assertEqual(failed.read_text(), "Sync/broken()\n")
        result = self.ios("gates", "--failed", ok=False)
        self.assertIn("part api (other)", result.stdout)
        self.assertIn("rerun: Sync/broken()", result.stdout)
        self.assertNotIn("part app", result.stdout)

    def test_unknown_module_names_the_right_one(self) -> None:
        self.two_part_app()
        result = self.ios("gates", "sync", ok=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("did you mean 'Sync'", result.stderr)

    def test_ui_tests_only_where_the_stack_defines_them(self) -> None:
        self.two_part_app()
        out = self.ios("gates", "--app-ui-tests").stdout
        self.assertIn("part api: no UI tests (stack defines no stack_ui_tests)", out)
        self.assertIn("=== UI tests ===", out)  # part app (fake stack: defines stack_ui_tests)


    # ---- test protection ----

    def edit(self, path: str, agent: str = "ios-pipeline:code-writer") -> int:
        hook = self.cli.parent.parent / "workflow" / "hooks" / "protect-tests.py"
        payload = json.dumps({"agent_type": agent, "cwd": str(self.app), "tool_input": {"file_path": path}})
        result = subprocess.run(["python3", str(hook)], input=payload, capture_output=True, text=True,
                                cwd=self.app, env={k: v for k, v in os.environ.items()
                                                   if k not in ("PIPELINE_APP_ROOT", "CLAUDE_PROJECT_DIR")})
        return result.returncode

    def test_code_writer_kept_out_of_every_part_s_tests(self) -> None:
        self.two_part_app()
        self.assertEqual(self.edit("api/tests/Sync/PushTests.txt"), 2)         # api's APP_TEST_DIR
        self.assertEqual(self.edit(str(self.app / "tests" / "Core" / "x.txt")), 2)  # app's, absolute path
        self.assertEqual(self.edit("api/src/Modules/Sync/push_test.txt"), 2)   # the other stack's glob
        self.assertEqual(self.edit("api/src/Modules/Sync/Push.txt"), 0)
        self.assertEqual(self.edit("src/Modules/Core/Impl.txt"), 0)
        self.assertEqual(self.edit("api/tests/Sync/PushTests.txt", agent="test-writer"), 0)


class OnePartFileTests(unittest.TestCase):
    """An app whose only part was added with `part add … --dir .` runs its gates as before."""

    def test_gates_read_the_part_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            from helpers import pipeline_with_fake_stack
            cli = str(pipeline_with_fake_stack(Path(tmp) / "pipeline"))
            app = git_repo(Path(tmp) / "app")
            for args in (("init", str(app)), ("part", "add", "app", "fake", "--dir", ".")):
                result = run(cli, *args, cwd=app)
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("APP_SOURCE_DIR", (app / ".pipeline" / "config.sh").read_text())
            core = app / "src" / "Modules" / "Core"
            (core / "Contracts").mkdir(parents=True)
            (core / "Contracts" / "Store.txt").write_text("# coverage-exempt-file: declarations\napi load()\nNODATA\n")
            (core / "Impl.txt").write_text("fine\n")
            (app / "docs" / "outline.md").write_text(
                "## Build order\n1. Core (depends on: none)\n## Modules\n### Core\n- Files: Store.txt, Impl.txt\n")
            for args in (("status", "init-modules"), ("api", "Core", "--write")):
                result = run(cli, *args, cwd=app)
                self.assertEqual(result.returncode, 0, result.stderr)
            commit_all(app)
            result = run(cli, "gates", "Core", cwd=app)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("GATES: PASS", result.stdout)


class GitignoreTests(unittest.TestCase):
    def test_anchored_patterns_move_under_the_part(self) -> None:
        template = "# x\nbuild/\n/out\nlib/gen/\n!/keep\n*.log\n"
        self.assertEqual(parts.prefixed_gitignore(template, "api"),
                         "# x\nbuild/\n/api/out\n/api/lib/gen/\n!/api/keep\n*.log\n")
        self.assertEqual(parts.prefixed_gitignore(template, "."), template)


if __name__ == "__main__":
    unittest.main()
