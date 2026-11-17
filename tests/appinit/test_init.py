"""Tests for `bull.Modules.appinit.init` (spec: appinit Behavior spec, `init` and `open_argv`).

Construction assumed (see the report's ASSUMPTIONS):
`LiveAppInit(layouts=, git=, files=, formats=, status=, adoption=, stackflow=, provider=,
settings=, version=, out=)` with `status` and `settings` callables taking the `AppLayout`,
plus `init_stack(path) -> InitResult` for `bull init --stack`.
"""

from __future__ import annotations

import io
import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from bull.Modules.adoption.Contracts import DetectionReport
from bull.Modules.adoption.mocks import MockAdoption
from bull.Modules.appinit.init import LiveAppInit
from bull.Modules.claude_code.mocks import MockProvider
from bull.Modules.formats.mocks import MockFormats
from bull.Modules.foundation.Contracts import AppLayout, BullError, Files
from bull.Modules.foundation.mocks import MockLayouts, sample_layout
from bull.Modules.gitrepo.mocks import MockGit
from bull.Modules.settings.Contracts import Settings
from bull.Modules.settings.mocks import MockSettings
from bull.Modules.stackflow.mocks import MockStackWorkflow
from bull.Modules.stacks.Contracts import Issue, IssueLevel
from bull.Modules.status.Contracts import StatusStore
from bull.Modules.status.mocks import MockStatusStore

VERSION = "9.9.9"


class DiskFiles(Files):
    """`Files` over the real disk (a tmp folder), so tests can read what was written."""

    def read_text(self, path: Path) -> str | None:
        return path.read_text(encoding="utf-8") if path.is_file() else None

    def write_atomic(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def read_json(self, path: Path) -> object | None:
        text = self.read_text(path)
        if text is None:
            return None
        data: object = json.loads(text)
        return data

    def write_json(self, path: Path, data: object) -> None:
        self.write_atomic(path, json.dumps(data, indent=2, sort_keys=True) + "\n")

    def append_line(self, path: Path, line: str) -> None:
        self.write_atomic(path, (self.read_text(path) or "") + line + "\n")


class FakeGit(MockGit):
    """A `MockGit` that is not a repo until `init`, and can report a different top level."""

    def __init__(self, repo: bool = False) -> None:
        super().__init__()
        self.repo = repo
        self.top: Path | None = None

    def is_repo(self, path: Path) -> bool:
        super().is_repo(path)
        return self.repo

    def toplevel(self, path: Path) -> Path | None:
        super().toplevel(path)
        if self.top is not None:
            return self.top
        return path if self.repo else None

    def init(self, path: Path, branch: str) -> None:
        super().init(path, branch)
        self.repo = True


@dataclass
class Env:
    root: Path
    layouts: MockLayouts = field(default_factory=MockLayouts)
    git: FakeGit = field(default_factory=FakeGit)
    files: DiskFiles = field(default_factory=DiskFiles)
    formats: MockFormats = field(default_factory=MockFormats)
    status: MockStatusStore = field(default_factory=MockStatusStore)
    adoption: MockAdoption = field(default_factory=MockAdoption)
    stackflow: MockStackWorkflow = field(default_factory=MockStackWorkflow)
    provider: MockProvider = field(default_factory=MockProvider)
    settings: MockSettings = field(default_factory=MockSettings)
    out: io.StringIO = field(default_factory=io.StringIO)

    def __post_init__(self) -> None:
        self.layouts.found = None

    def app_at(self, root: Path) -> None:
        """Make `layouts.find` report a bull app rooted at `root`."""
        self.layouts.found = sample_layout(root)

    def make(self) -> LiveAppInit:
        def status(_app: AppLayout) -> StatusStore:
            return self.status

        def settings(_app: AppLayout) -> Settings:
            return self.settings

        return LiveAppInit(
            layouts=self.layouts,
            git=self.git,
            files=self.files,
            formats=self.formats,
            status=status,
            adoption=self.adoption,
            stackflow=self.stackflow,
            provider=self.provider,
            settings=settings,
            version=VERSION,
            out=self.out,
        )

    def commits(self) -> list[str]:
        return [str(c[1][1]) for c in self.git.calls if c[0] == "commit_all"]

    def names(self, calls: list[tuple[str, tuple[object, ...]]]) -> list[str]:
        return [c[0] for c in calls]


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(root=tmp_path)


def _blocked_report() -> DetectionReport:
    return DetectionReport(
        stack=None,
        detection=None,
        issues=(Issue(IssueLevel.BLOCK, "no supported stack found", "add one"),),
    )


# --- init on a missing or empty folder -------------------------------------------------


def test_init_creates_a_missing_folder(env: Env) -> None:
    target = env.root / "newapp"
    result = env.make().init(target)
    assert target.is_dir()
    assert (result.root, result.created, result.relinked, result.adopting) == (
        target,
        True,
        False,
        False,
    )


def test_init_uses_an_existing_empty_folder(env: Env) -> None:
    result = env.make().init(env.root)
    assert (result.root, result.created, result.relinked) == (env.root, True, False)


def test_init_runs_git_init_on_main(env: Env) -> None:
    env.make().init(env.root / "a")
    assert ("init", (env.root / "a", "main")) in env.git.calls


def test_init_writes_config_toml_with_format_one(env: Env) -> None:
    env.make().init(env.root)
    data = tomllib.loads((env.root / ".bull" / "config.toml").read_text())
    assert data["format"] == 1


def test_init_creates_status_through_the_status_store(env: Env) -> None:
    env.make().init(env.root)
    assert ("create", ()) in env.status.calls


def test_init_writes_an_empty_backlog_with_format_one(env: Env) -> None:
    env.make().init(env.root)
    data = json.loads((env.root / ".bull" / "backlog.json").read_text())
    assert data == {"format": 1, "items": []}


def test_init_gitignore_has_every_machine_local_line(env: Env) -> None:
    env.make().init(env.root)
    lines = (env.root / ".gitignore").read_text().splitlines()
    for line in env.layouts.machine_local_ignores():
        assert line in lines


def test_init_writes_the_providers_app_files(env: Env) -> None:
    env.make().init(env.root)
    assert (env.root / "CLAUDE.md").is_file()
    assert (env.root / ".claude" / "settings.json").is_file()


def test_init_commits_chore_bull_init_after_git_init(env: Env) -> None:
    env.make().init(env.root)
    assert env.commits() == ["chore: bull init"]
    assert env.names(env.git.calls).index("init") < env.names(env.git.calls).index(
        "commit_all"
    )


# --- relink ----------------------------------------------------------------------------


def _existing_app(env: Env) -> None:
    bull = env.root / ".bull"
    bull.mkdir()
    (bull / "status.json").write_text("STATE")
    (bull / "backlog.json").write_text("BACKLOG")
    (bull / "config.toml").write_text("CONFIG")
    (env.root / ".gitignore").write_text("node_modules/\n")
    env.app_at(env.root)
    env.git.repo = True


def test_init_on_an_app_root_relinks(env: Env) -> None:
    _existing_app(env)
    result = env.make().init(env.root)
    assert (result.root, result.created, result.relinked, result.adopting) == (
        env.root,
        False,
        True,
        False,
    )


def test_relink_leaves_state_files_untouched(env: Env) -> None:
    _existing_app(env)
    env.make().init(env.root)
    bull = env.root / ".bull"
    assert (bull / "status.json").read_text() == "STATE"
    assert (bull / "backlog.json").read_text() == "BACKLOG"
    assert (bull / "config.toml").read_text() == "CONFIG"
    assert ("create", ()) not in env.status.calls


def test_relink_does_not_run_git_init(env: Env) -> None:
    _existing_app(env)
    env.make().init(env.root)
    assert "init" not in env.names(env.git.calls)


def test_relink_rewrites_provider_files_and_merges_gitignore(env: Env) -> None:
    _existing_app(env)
    env.make().init(env.root)
    assert (env.root / "CLAUDE.md").is_file()
    lines = (env.root / ".gitignore").read_text().splitlines()
    assert "node_modules/" in lines
    for line in env.layouts.machine_local_ignores():
        assert line in lines


def test_relink_commits_when_something_changed(env: Env) -> None:
    _existing_app(env)
    env.make().init(env.root)
    assert len(env.commits()) == 1


def test_relink_twice_makes_no_second_commit_and_no_duplicate_lines(env: Env) -> None:
    _existing_app(env)
    app_init = env.make()
    app_init.init(env.root)
    app_init.init(env.root)
    assert len(env.commits()) == 1
    lines = (env.root / ".gitignore").read_text().splitlines()
    assert lines.count(".bull/usage.json") == 1


def test_init_dot_relinks_the_current_app(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    _existing_app(env)
    monkeypatch.chdir(env.root)
    result = env.make().init(Path("."))
    assert result.relinked is True
    assert result.root.resolve() == env.root.resolve()
    assert (env.root / ".bull" / "status.json").read_text() == "STATE"


# --- refusals --------------------------------------------------------------------------


def test_subfolder_of_an_app_is_refused_before_anything_is_created(env: Env) -> None:
    env.app_at(env.root)
    target = env.root / "sub" / "deeper"
    with pytest.raises(BullError):
        env.make().init(target)
    assert not (env.root / "sub").exists()
    assert "init" not in env.names(env.git.calls)
    assert env.commits() == []
    assert ("create", ()) not in env.status.calls


def test_existing_subfolder_of_an_app_is_refused_and_left_alone(env: Env) -> None:
    env.app_at(env.root)
    sub = env.root / "sub"
    sub.mkdir()
    with pytest.raises(BullError):
        env.make().init(sub)
    assert list(sub.iterdir()) == []


def test_subfolder_refusal_fix_names_init_dot_and_the_app_root(env: Env) -> None:
    env.app_at(env.root)
    target = env.root / "sub"
    with pytest.raises(BullError) as raised:
        env.make().init(target)
    assert "bull init ." in raised.value.fix
    assert str(env.root) in raised.value.fix
    assert not target.exists()
    assert env.commits() == []


def _empty_git_repo(env: Env) -> None:
    (env.root / ".git").mkdir()
    env.git.repo = True
    env.git.heads.clear()


def test_init_on_an_empty_git_repo_does_not_run_git_init_again(env: Env) -> None:
    _empty_git_repo(env)
    env.make().init(env.root)
    assert "init" not in env.names(env.git.calls)


def test_init_on_an_empty_git_repo_writes_bull_files_and_commits(env: Env) -> None:
    _empty_git_repo(env)
    env.make().init(env.root)
    assert (env.root / ".bull" / "config.toml").is_file()
    assert (env.root / ".bull" / "backlog.json").is_file()
    assert ("create", ()) in env.status.calls
    lines = (env.root / ".gitignore").read_text().splitlines()
    for line in env.layouts.machine_local_ignores():
        assert line in lines
    assert (env.root / "CLAUDE.md").is_file()
    assert (env.root / ".claude" / "settings.json").is_file()
    assert env.commits() == ["chore: bull init"]


def test_init_on_an_empty_git_repo_reports_created_like_an_empty_folder(
    env: Env,
) -> None:
    _empty_git_repo(env)
    result = env.make().init(env.root)
    assert (result.root, result.created, result.relinked, result.adopting) == (
        env.root,
        True,
        False,
        False,
    )


def test_init_on_an_empty_git_repo_on_another_branch_still_succeeds(env: Env) -> None:
    _empty_git_repo(env)
    env.git.branch = "trunk"
    result = env.make().init(env.root)
    assert result.created is True
    assert "init" not in env.names(env.git.calls)


def test_init_dot_in_an_empty_git_repo_succeeds(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    _empty_git_repo(env)
    monkeypatch.chdir(env.root)
    result = env.make().init(Path("."))
    assert result.created is True
    assert result.root.resolve() == env.root.resolve()
    assert "init" not in env.names(env.git.calls)
    assert env.commits() == ["chore: bull init"]


def test_git_repo_with_other_files_is_still_refused_without_adopt(env: Env) -> None:
    _empty_git_repo(env)
    (env.root / "main.py").write_text("print('hi')\n")
    with pytest.raises(BullError) as raised:
        env.make().init(env.root)
    assert "bull init --adopt" in f"{raised.value.message} {raised.value.fix}"
    assert not (env.root / ".bull").exists()
    assert env.commits() == []


def test_git_repo_with_commits_is_still_refused_without_adopt(env: Env) -> None:
    (env.root / ".git").mkdir()
    env.git.repo = True  # MockGit.heads still reports a HEAD commit
    with pytest.raises(BullError) as raised:
        env.make().init(env.root)
    assert "bull init --adopt" in f"{raised.value.message} {raised.value.fix}"
    assert not (env.root / ".bull").exists()
    assert env.commits() == []


def test_non_empty_folder_without_adopt_is_refused_naming_adopt(env: Env) -> None:
    (env.root / "main.py").write_text("print('hi')\n")
    with pytest.raises(BullError) as raised:
        env.make().init(env.root)
    assert "bull init --adopt" in f"{raised.value.message} {raised.value.fix}"
    assert "not empty" in raised.value.message
    assert not (env.root / ".bull").exists()
    assert "init" not in env.names(env.git.calls)


def test_relink_appends_missing_lines_when_gitignore_lacks_a_trailing_newline(
    env: Env,
) -> None:
    _existing_app(env)
    (env.root / ".gitignore").write_text("node_modules/")
    env.make().init(env.root)
    lines = (env.root / ".gitignore").read_text().splitlines()
    assert "node_modules/" in lines
    for line in env.layouts.machine_local_ignores():
        assert line in lines


def test_init_on_an_existing_file_is_refused_and_creates_nothing(env: Env) -> None:
    target = env.root / "afile"
    target.write_text("data")
    with pytest.raises(BullError) as raised:
        env.make().init(target)
    assert "not empty" in raised.value.message
    assert "bull init --adopt" in f"{raised.value.message} {raised.value.fix}"
    assert target.read_text() == "data"
    assert not (env.root / ".bull").exists()
    assert "init" not in env.names(env.git.calls)


def test_init_where_the_folder_cannot_be_created_names_the_folder(env: Env) -> None:
    parent = env.root / "afile"
    parent.write_text("data")
    target = parent / "app"
    with pytest.raises(BullError) as raised:
        env.make().init(target)
    assert raised.value.message.startswith(f"cannot create {target}")
    assert "writable" in raised.value.fix
    assert "init" not in env.names(env.git.calls)


# --- adopt -----------------------------------------------------------------------------


def _legacy_repo(env: Env) -> None:
    (env.root / "main.py").write_text("print('hi')\n")
    env.git.repo = True


def test_adopt_adds_bull_files_commits_detects_applies_and_starts(env: Env) -> None:
    _legacy_repo(env)
    result = env.make().init(env.root, adopt=True)
    assert result.adopting is True
    assert result.relinked is False
    assert (env.root / ".bull" / "config.toml").is_file()
    assert (env.root / ".bull" / "backlog.json").is_file()
    assert ("create", ()) in env.status.calls
    assert (env.root / "main.py").read_text() == "print('hi')\n"
    assert env.commits()[0] == "chore: bull init"
    assert env.names(env.adoption.calls) == ["detect", "apply", "start"]


def test_adopt_commits_again_after_apply(env: Env) -> None:
    _legacy_repo(env)
    env.make().init(env.root, adopt=True)
    assert len(env.commits()) == 2


def test_adopt_detects_on_the_app_root(env: Env) -> None:
    _legacy_repo(env)
    env.make().init(env.root, adopt=True)
    assert env.adoption.calls[0] == ("detect", (env.root,))


def test_adopt_applies_the_detected_report(env: Env) -> None:
    _legacy_repo(env)
    env.make().init(env.root, adopt=True)
    apply_call = env.adoption.calls[1]
    assert apply_call[1][1] is env.adoption.report


def test_adopt_prints_the_detection_report(env: Env) -> None:
    _legacy_repo(env)
    env.make().init(env.root, adopt=True)
    assert "active git hook pre-commit" in env.out.getvalue()


def test_adopt_blocked_report_stops_with_an_error(env: Env) -> None:
    _legacy_repo(env)
    env.adoption.report = _blocked_report()
    with pytest.raises(BullError):
        env.make().init(env.root, adopt=True)
    assert "apply" not in env.names(env.adoption.calls)
    assert "start" not in env.names(env.adoption.calls)


def test_adopt_blocked_report_is_printed_before_stopping(env: Env) -> None:
    _legacy_repo(env)
    env.adoption.report = _blocked_report()
    with pytest.raises(BullError):
        env.make().init(env.root, adopt=True)
    assert "no supported stack found" in env.out.getvalue()


def test_adopt_refuses_a_dirty_tree_before_writing(env: Env) -> None:
    _legacy_repo(env)
    env.git.clean = False
    with pytest.raises(BullError):
        env.make().init(env.root, adopt=True)
    assert not (env.root / ".bull").exists()
    assert env.adoption.calls == []
    assert env.commits() == []


def test_adopt_refuses_a_folder_that_is_not_a_git_repo(env: Env) -> None:
    (env.root / "main.py").write_text("x = 1\n")
    env.git.repo = False
    with pytest.raises(BullError):
        env.make().init(env.root, adopt=True)
    assert not (env.root / ".bull").exists()
    assert env.adoption.calls == []


def test_adopt_refuses_a_folder_below_the_git_repo_root(env: Env) -> None:
    _legacy_repo(env)
    env.git.top = env.root.parent
    with pytest.raises(BullError):
        env.make().init(env.root, adopt=True)
    assert not (env.root / ".bull").exists()
    assert env.adoption.calls == []


# --- init --stack ----------------------------------------------------------------------


def test_init_stack_calls_stackflow_init_on_the_path(env: Env) -> None:
    target = env.root / "go_cli"
    env.make().init_stack(target)
    assert env.stackflow.calls == [("init", (target,))]


def test_init_stack_writes_provider_files_in_the_stack_repo(env: Env) -> None:
    target = env.root / "go_cli"
    env.make().init_stack(target)
    assert (target / "CLAUDE.md").is_file()
    assert (target / ".claude" / "settings.json").is_file()


def test_init_stack_commits_the_provider_files(env: Env) -> None:
    target = env.root / "go_cli"
    env.make().init_stack(target)
    assert env.commits() == ["chore: bull init --stack provider files"]


def test_init_stack_returns_the_stack_repo_root(env: Env) -> None:
    target = env.root / "go_cli"
    assert env.make().init_stack(target).root == target


def test_init_stack_does_not_create_app_state(env: Env) -> None:
    target = env.root / "go_cli"
    env.make().init_stack(target)
    assert ("create", ()) not in env.status.calls
    assert not (target / ".bull" / "backlog.json").exists()


# --- open_argv -------------------------------------------------------------------------


def test_open_argv_returns_the_providers_launch_argv(env: Env) -> None:
    env.app_at(env.root)
    argv = env.make().open_argv(env.root, ["--resume", "x"])
    layout = sample_layout(env.root)
    assert argv == ["claude", "--plugin-dir", str(layout.plugin_dir), "--resume", "x"]


def test_open_argv_passes_extra_args_to_the_provider(env: Env) -> None:
    env.app_at(env.root)
    env.make().open_argv(env.root, ["-p", "hi"])
    assert env.provider.calls[-1][0] == "launch_argv"
    assert env.provider.calls[-1][1][1] == ("-p", "hi")


def test_open_argv_renders_the_plugin_into_the_plugin_folder(env: Env) -> None:
    env.app_at(env.root)
    env.make().open_argv(env.root, [])
    render = [c for c in env.provider.calls if c[0] == "render_plugin"]
    assert render == [
        ("render_plugin", (sample_layout(env.root).plugin_dir, env.settings, VERSION))
    ]


def test_open_argv_checks_formats_before_rendering(env: Env) -> None:
    env.app_at(env.root)
    env.make().open_argv(env.root, [])
    assert ("check", (sample_layout(env.root),)) in env.formats.calls


def test_open_argv_stops_on_a_format_error_without_rendering(env: Env) -> None:
    env.app_at(env.root)
    env.formats.found = 0
    with pytest.raises(BullError):
        env.make().open_argv(env.root, [])
    assert "render_plugin" not in env.names(env.provider.calls)
    assert "launch_argv" not in env.names(env.provider.calls)


def test_open_argv_refuses_a_folder_that_is_not_an_app(env: Env) -> None:
    with pytest.raises(BullError):
        env.make().open_argv(env.root, [])
    assert "render_plugin" not in env.names(env.provider.calls)


def test_open_argv_works_in_a_stack_repo(env: Env) -> None:
    env.app_at(env.root)
    status = env.root / ".bull" / "status.json"
    status.parent.mkdir()
    status.write_text(json.dumps({"format": 1, "kind": "stack", "name": "go_cli"}))
    argv = env.make().open_argv(env.root, [])
    assert argv[:2] == ["claude", "--plugin-dir"]
    assert "render_plugin" in env.names(env.provider.calls)
