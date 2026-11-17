"""Tests for `bull.Modules.cli.wiring`: the composition root and the command table."""

from __future__ import annotations

import argparse
import io
import json
from dataclasses import replace
from pathlib import Path

import pytest

import bull
from bull.Modules.claude_code.mocks import MockProvider
from bull.Modules.cli import wiring
from bull.Modules.cli.main import main
from bull.Modules.foundation.Contracts import AppLayout
from bull.Modules.hooks.Contracts import HookDecision, HookEvent, HookKind
from bull.Modules.hooks.mocks import MockHooks
from bull.Modules.settings.loader import LiveSettingsLoader
from bull.Modules.stackflow.mocks import MockStackWorkflow
from bull.Modules.stacks.Contracts import Stack
from bull.Modules.stacks.mocks import MockStackRegistry, sample_stack
from bull.Modules.stacktest.mocks import MockStackTester

_COMMANDS = [
    "init",
    "open",
    "doctor",
    "status",
    "feature",
    "adopt",
    "gates",
    "coverage",
    "api",
    "stacks",
    "stack",
    "part",
    "config",
    "migrate",
    "template",
    "hook",
    "statusline",
]

_STACK_LEAVES = [
    "select",
    "rules",
    "setup",
    "check",
    "run",
    "install",
    "test",
    "detect",
]


def _table() -> argparse._SubParsersAction[argparse.ArgumentParser]:
    parser = argparse.ArgumentParser(prog="bull")
    commands = parser.add_subparsers(dest="command")
    wiring.get_wiring().register_commands(commands)
    return commands


# --- building ---------------------------------------------------------------------------


def test_the_real_implementations_are_built_once_per_process() -> None:
    assert wiring.get_wiring() is wiring.get_wiring()


def test_the_wiring_provides_what_main_needs() -> None:
    built = wiring.get_wiring()

    for name in (
        "layouts",
        "formats",
        "settings_loader",
        "stack_layer",
        "register_commands",
        "provider",
        "hooks",
    ):
        assert hasattr(built, name), name


def test_builtin_stack_roots_are_the_stack_folders_under_modules() -> None:
    modules = Path(bull.__file__).resolve().parent / "Modules"

    roots = [Path(p).resolve() for p in wiring.builtin_stack_roots()]

    assert roots
    for root in roots:
        assert root.is_dir()
        assert root.parent.parent == modules
        assert root.parent.name.startswith("stack_")
    names = {root.name for root in roots}
    assert {"fixture", "fixture_service", "ios", "python_cli"} <= names


def test_builtin_stack_roots_hold_no_folder_outside_the_stack_modules() -> None:
    roots = [Path(p).resolve() for p in wiring.builtin_stack_roots()]

    assert all(root.parent.name.startswith("stack_") for root in roots)
    assert len(roots) == len(set(roots))


# --- the command table ------------------------------------------------------------------


@pytest.mark.parametrize("command", _COMMANDS)
def test_the_command_table_holds_every_command_of_the_commands_table(
    command: str,
) -> None:
    assert command in _table().choices


@pytest.mark.parametrize("leaf", _STACK_LEAVES)
def test_the_stack_command_has_every_subcommand_of_the_commands_table(
    leaf: str, capsys: pytest.CaptureFixture[str]
) -> None:
    parser = argparse.ArgumentParser(prog="bull")
    commands = parser.add_subparsers(dest="command")
    wiring.get_wiring().register_commands(commands)

    with pytest.raises(SystemExit) as raised:
        parser.parse_args(["stack", leaf, "--help"])

    assert raised.value.code == 0
    assert capsys.readouterr().out != ""


@pytest.mark.parametrize(
    "argv",
    [
        ["status", "usage-check", "--help"],
        ["status", "ref", "trunk", "--help"],
        ["feature", "add", "--help"],
        ["adopt", "start", "--help"],
        ["part", "list", "--help"],
        ["config", "show", "--help"],
        ["open", "--help"],
        ["gates", "--help"],
        ["api", "--help"],
    ],
)
def test_subcommands_of_the_commands_table_parse(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    parser = argparse.ArgumentParser(prog="bull")
    commands = parser.add_subparsers(dest="command")
    wiring.get_wiring().register_commands(commands)

    with pytest.raises(SystemExit) as raised:
        parser.parse_args(argv)

    assert raised.value.code == 0
    assert capsys.readouterr().out != ""


def test_every_registered_leaf_command_has_a_run_function() -> None:
    parser = argparse.ArgumentParser(prog="bull")
    commands = parser.add_subparsers(dest="command")
    wiring.get_wiring().register_commands(commands)

    args = parser.parse_args(["config", "show"])

    assert callable(args.run)


# --- hook entry points ------------------------------------------------------------------


class _Hooks(MockHooks):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[HookEvent] = []

    def handle(self, event: HookEvent) -> HookDecision:
        self.events.append(event)
        return super().handle(event)


class _BadHooks(MockHooks):
    def handle(self, event: HookEvent) -> HookDecision:
        raise RuntimeError("safeguard exploded")


class _BadParse(MockProvider):
    def parse_hook(self, kind: HookKind, raw: str) -> HookEvent:
        raise ValueError("not json")


def _hook(
    kind: str,
    raw: str = "{}",
    *,
    provider: MockProvider | None = None,
    hooks: MockHooks | None = None,
) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = wiring.run_hook(
        kind,
        raw,
        out,
        err,
        provider=provider or MockProvider(),
        hooks=hooks or MockHooks(),
    )
    return code, out.getvalue(), err.getvalue()


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("session-start", HookKind.SESSION_START),
        ("before-agent", HookKind.BEFORE_AGENT),
        ("before-shell", HookKind.BEFORE_SHELL),
        ("before-edit", HookKind.BEFORE_EDIT),
        ("before-read", HookKind.BEFORE_READ),
        ("agent-end", HookKind.AGENT_END),
    ],
)
def test_a_hook_is_parsed_by_the_provider_and_handled_as_its_kind(
    name: str, kind: HookKind
) -> None:
    provider, hooks = MockProvider(), _Hooks()

    code, _, _ = _hook(name, '{"x": 1}', provider=provider, hooks=hooks)

    assert code == 0
    assert ("parse_hook", (kind, '{"x": 1}')) in provider.calls
    assert [event.kind for event in hooks.events] == [kind]


def test_a_hook_decision_goes_out_through_the_provider() -> None:
    hooks = MockHooks()

    code, out, _ = _hook("session-start", hooks=hooks)

    assert code == 0
    assert "stage 5" in out


def test_a_blocking_hook_decision_uses_the_providers_exit_code_and_stderr() -> None:
    hooks = MockHooks()
    hooks.decision = HookDecision(False, "blocked: merge needs a gate pass")

    code, out, err = _hook("before-shell", hooks=hooks)

    assert code == 2
    assert out == ""
    assert "blocked: merge needs a gate pass" in err


def test_a_hook_whose_input_cannot_be_parsed_allows_and_reports_on_stderr() -> None:
    code, out, err = _hook("before-shell", provider=_BadParse())

    assert code == 0
    assert out == ""
    assert "not json" in err


def test_a_hook_that_raises_allows_and_reports_on_stderr() -> None:
    code, out, err = _hook("before-edit", hooks=_BadHooks())

    assert code == 0
    assert out == ""
    assert "safeguard exploded" in err


def test_a_hook_that_raises_still_allows_session_start() -> None:
    code, _, err = _hook("session-start", hooks=_BadHooks())

    assert code == 0
    assert "safeguard exploded" in err


# --- stack repo routing -----------------------------------------------------------------

_STACK_STATUS = {
    "format": 1,
    "kind": "stack",
    "name": "demo",
    "stage": 1,
    "checkpoints": [],
}
_APP_STATUS = {"format": 1, "kind": "app"}


def _folder(root: Path, status: object | None, *, raw: str | None = None) -> Path:
    """A folder with `.bull/status.json` holding `status` (or the text `raw`)."""
    root.mkdir(parents=True, exist_ok=True)
    (root / ".bull").mkdir(exist_ok=True)
    if raw is not None:
        (root / ".bull" / "status.json").write_text(raw, encoding="utf-8")
    elif status is not None:
        (root / ".bull" / "status.json").write_text(
            json.dumps(status), encoding="utf-8"
        )
    return root


@pytest.fixture
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Keep user-level folders inside the test's temporary directory."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
    return tmp_path


def test_status_in_a_stack_repo_is_the_stack_workflow_status(
    isolated: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _folder(isolated / "repo", _STACK_STATUS)
    monkeypatch.chdir(repo)

    code = main(["status"])

    captured = capsys.readouterr()
    assert code == 0
    assert "demo" in captured.out


@pytest.mark.parametrize(
    "argv",
    [
        ["part", "list"],
        ["feature", "list"],
        ["gates", "--all"],
        ["api", "Counter"],
        ["config", "show"],
    ],
)
def test_app_commands_refuse_in_a_stack_repo(
    argv: list[str],
    isolated: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _folder(isolated / "repo", _STACK_STATUS)
    monkeypatch.chdir(repo)

    code = main(argv)

    captured = capsys.readouterr()
    assert code == 1
    assert "bull: this is a stack repo" in captured.err
    assert "fix:" in captured.err


def test_the_formats_check_is_skipped_in_a_stack_repo(
    isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    built = wiring.get_wiring()
    checked: list[AppLayout] = []
    monkeypatch.setattr(built.app_formats, "check", checked.append)
    repo = _folder(isolated / "repo", _STACK_STATUS)

    built.formats.check(built.layouts.at(repo))

    assert checked == []


def test_the_formats_check_runs_in_an_app(
    isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    built = wiring.get_wiring()
    checked: list[AppLayout] = []
    monkeypatch.setattr(built.app_formats, "check", checked.append)
    app = built.layouts.at(_folder(isolated / "app", _APP_STATUS))

    built.formats.check(app)

    assert checked == [app]


@pytest.mark.parametrize(
    ("status", "raw"),
    [
        (None, None),
        (None, "{this is not json"),
        (None, "[1, 2, 3]"),
        (None, '"stack"'),
        ({"format": 1}, None),
        ({"format": 1, "kind": "app"}, None),
    ],
    ids=["missing", "unreadable", "list", "string", "no-kind", "app-kind"],
)
def test_a_missing_unreadable_or_non_object_status_file_is_not_a_stack_repo(
    status: object | None,
    raw: str | None,
    isolated: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built = wiring.get_wiring()
    checked: list[AppLayout] = []
    monkeypatch.setattr(built.app_formats, "check", checked.append)
    folder = _folder(isolated / "folder", status, raw=raw)
    layout = built.layouts.at(folder)

    built.formats.check(layout)

    assert checked == [layout]


def test_statusline_in_a_stack_repo_prints_a_plain_line_and_records_nothing(
    isolated: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _folder(isolated / "repo", _STACK_STATUS)
    monkeypatch.chdir(repo)
    payload = {
        "cwd": str(repo),
        "rate_limits": {"five_hour": {"used_percentage": 50}},
    }
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))

    code = main(["statusline"])

    assert code == 0
    assert capsys.readouterr().out == "bull\n"
    assert not (repo / ".bull" / "usage.json").exists()


class _HomeRegistry(MockStackRegistry):
    """`load_path` returns a stack whose home is the folder asked for."""

    def load_path(self, path: Path) -> Stack:
        return replace(sample_stack(path.name), home=path.resolve())


class _RecordingSetup:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        built = wiring.get_wiring()
        self.workflow = MockStackWorkflow()
        self.tester = MockStackTester()
        monkeypatch.setattr(built, "registry", _HomeRegistry())
        monkeypatch.setattr(built, "tester", self.tester)
        monkeypatch.setattr(built, "workflow", self.workflow)

    @property
    def recorded(self) -> list[Path]:
        return [
            call[1][0]  # type: ignore[misc]
            for call in self.workflow.calls
            if call[0] == "record_test"
        ]


@pytest.mark.parametrize(
    "extra", [["--static"], []], ids=["static-run", "whole-suite-run"]
)
def test_stack_test_on_the_stack_repo_root_records_the_result(
    extra: list[str], isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _folder(isolated / "repo", _STACK_STATUS)
    monkeypatch.chdir(repo)
    setup = _RecordingSetup(monkeypatch)

    code = main(["stack", "test", ".", *extra])

    assert code == 0
    assert setup.recorded == [repo.resolve()]


def test_stack_test_with_a_case_does_not_record(
    isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _folder(isolated / "repo", _STACK_STATUS)
    monkeypatch.chdir(repo)
    setup = _RecordingSetup(monkeypatch)

    code = main(["stack", "test", ".", "--case", "clean"])

    assert code == 0
    assert setup.recorded == []


def test_stack_test_on_a_folder_inside_the_stack_repo_does_not_record(
    isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _folder(isolated / "repo", _STACK_STATUS)
    inner = repo / "stacks" / "inner"
    inner.mkdir(parents=True)
    monkeypatch.chdir(repo)
    setup = _RecordingSetup(monkeypatch)

    code = main(["stack", "test", "stacks/inner", "--static"])

    assert code == 0
    assert setup.recorded == []


def test_stack_test_on_a_folder_outside_any_stack_repo_does_not_record(
    isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _folder(isolated / "repo", _STACK_STATUS)
    elsewhere = isolated / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(repo)
    setup = _RecordingSetup(monkeypatch)

    code = main(["stack", "test", str(elsewhere), "--static"])

    assert code == 0
    assert setup.recorded == []


def test_stack_test_in_an_app_does_not_record(
    isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = _folder(isolated / "app", _APP_STATUS)
    monkeypatch.chdir(app)
    setup = _RecordingSetup(monkeypatch)

    main(["stack", "test", ".", "--static"])

    assert setup.recorded == []


# --- settings load lazily ----------------------------------------------------------------


@pytest.fixture
def loads(monkeypatch: pytest.MonkeyPatch) -> list[AppLayout | None]:
    """Every call to the real settings loader, recorded."""
    seen: list[AppLayout | None] = []
    original = LiveSettingsLoader.load

    def counting(
        self: LiveSettingsLoader, app: AppLayout | None, layer: object
    ) -> object:
        seen.append(app)
        return original(self, app, layer)  # type: ignore[arg-type]

    monkeypatch.setattr(LiveSettingsLoader, "load", counting)
    return seen


def test_building_the_commands_in_an_app_reads_no_settings(
    isolated: Path, monkeypatch: pytest.MonkeyPatch, loads: list[AppLayout | None]
) -> None:
    app = _folder(isolated / "app", _APP_STATUS)
    monkeypatch.chdir(app)

    _table()

    assert loads == []


def test_a_command_loads_the_apps_settings_once(
    isolated: Path,
    monkeypatch: pytest.MonkeyPatch,
    loads: list[AppLayout | None],
    capsys: pytest.CaptureFixture[str],
) -> None:
    app = _folder(isolated / "app", _APP_STATUS)
    monkeypatch.chdir(app)

    code = main(["config", "show"])

    assert code == 0
    assert capsys.readouterr().out != ""
    assert len(loads) == 1
