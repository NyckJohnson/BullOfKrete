"""The composition root: builds every real implementation once and the command table.

This is the only file that imports other modules' implementation files. Every other file
uses other modules through their `Contracts` only. App-bound objects (status store, usage,
event log, settings…) are built when a command runs, for the app found from the current
folder (or, for hooks and the status line, from the provider's `cwd`).
"""

from __future__ import annotations

import argparse
import functools
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, TextIO, TypeAlias

from bull import __version__
from bull.Modules.adoption import cli as adoption_cli
from bull.Modules.adoption.adopt import LiveAdoption
from bull.Modules.adoption.Contracts import Adoption
from bull.Modules.api import cli as api_cli
from bull.Modules.api.Contracts import ApiSnapshots
from bull.Modules.api.snapshots import LiveApiSnapshots
from bull.Modules.appinit import cli as appinit_cli
from bull.Modules.appinit.Contracts import Doctor, InitResult
from bull.Modules.appinit.doctor import LiveDoctor
from bull.Modules.appinit.init import LiveAppInit
from bull.Modules.claude_code.Contracts import Provider
from bull.Modules.claude_code.plugin import LiveProvider
from bull.Modules.cli.statusline import run_statusline
from bull.Modules.coverage.triage import LiveCoverageTriage
from bull.Modules.events.Contracts import EventLog
from bull.Modules.events.event_log import LiveEventLog
from bull.Modules.features import cli as features_cli
from bull.Modules.features.backlog import LiveBacklog
from bull.Modules.features.Contracts import Backlog, FeatureCycle, IdeaReader
from bull.Modules.features.cycle import LiveFeatureCycle
from bull.Modules.features.ideas import LiveIdeaReader
from bull.Modules.formats import cli as formats_cli
from bull.Modules.formats.Contracts import FileFormat, Formats
from bull.Modules.formats.formats import LiveFormats
from bull.Modules.foundation.clock import LiveClock
from bull.Modules.foundation.Contracts import (
    AppLayout,
    BullError,
    FileFormatError,
    Files,
    Layouts,
    Runner,
)
from bull.Modules.foundation.files import LiveFiles
from bull.Modules.foundation.layout import LiveLayouts
from bull.Modules.foundation.runner import LiveRunner
from bull.Modules.gates import cli as gates_cli
from bull.Modules.gates.Contracts import Gates
from bull.Modules.gates.driver import LiveGates
from bull.Modules.gates.journeys import JourneyRunner
from bull.Modules.gates.passes import LivePassRecords
from bull.Modules.gates.steps import LiveSteps
from bull.Modules.gitrepo.git import LiveGit
from bull.Modules.hooks.Contracts import HookDecision, HookEvent, HookKind, Hooks
from bull.Modules.hooks.dispatch import LiveHooks
from bull.Modules.hooks.merge_guard import MergeGuard, merge_targets
from bull.Modules.hooks.protection import Protection
from bull.Modules.hooks.session import SessionStart
from bull.Modules.hooks.usage_guard import UsageGuard
from bull.Modules.interfaces.Contracts import Interfaces
from bull.Modules.interfaces.interfaces import LiveInterfaces
from bull.Modules.memo import cli as memo_cli
from bull.Modules.memo.Contracts import Memo, Templates
from bull.Modules.memo.parser import LiveMemoReader
from bull.Modules.memo.templates import LiveTemplates
from bull.Modules.parts import cli as parts_cli
from bull.Modules.parts.Contracts import Parts
from bull.Modules.parts.parts import LiveParts
from bull.Modules.plugin_text.plugin_files import LivePluginText
from bull.Modules.settings import cli as settings_cli
from bull.Modules.settings.Contracts import (
    Layer,
    Resolved,
    Setting,
    Settings,
    SettingsLoader,
    SettingValue,
    StackLayer,
)
from bull.Modules.settings.loader import LiveSettingsLoader
from bull.Modules.stackflow import cli as stackflow_cli
from bull.Modules.stackflow.Contracts import StackWorkflow
from bull.Modules.stackflow.workflow import LiveStackWorkflow
from bull.Modules.stacks import cli as stacks_cli
from bull.Modules.stacks.Contracts import CheckItem, Stack, StackOps, StackRegistry
from bull.Modules.stacks.registry import LiveStackRegistry
from bull.Modules.stacks.select import LiveStackOps
from bull.Modules.stacktest import cli as stacktest_cli
from bull.Modules.stacktest.Contracts import Case, StackTester, StackTestReport
from bull.Modules.stacktest.runner import LiveStackTester
from bull.Modules.status import cli as status_cli
from bull.Modules.status.Contracts import Progress, Refs, StatusStore
from bull.Modules.status.refs import LiveRefs
from bull.Modules.status.store import LiveStatusStore
from bull.Modules.status.summary import LiveProgress
from bull.Modules.usage.Contracts import Usage
from bull.Modules.usage.usage import LiveUsage

_Commands: TypeAlias = "argparse._SubParsersAction[argparse.ArgumentParser]"
_Run = Callable[[argparse.Namespace, TextIO], int]

# Folders inside a `stack_*` module that are its Python package, not a stack.
_NOT_STACKS = frozenset({"Contracts", "mocks"})

# `bull hook <name>` → the hook kind the provider's input is parsed as.
_HOOK_KINDS: dict[str, HookKind] = {
    "session-start": HookKind.SESSION_START,
    "before-agent": HookKind.BEFORE_AGENT,
    "before-shell": HookKind.BEFORE_SHELL,
    "before-edit": HookKind.BEFORE_EDIT,
    "before-read": HookKind.BEFORE_READ,
    "agent-end": HookKind.AGENT_END,
}

_STACK_REPO_FIX = "use the stack commands here, not the app's"


class Wiring(Protocol):
    """What `main` needs of the composition root (`main(argv, wiring=…)` takes a fake)."""

    @property
    def layouts(self) -> Layouts:
        """Finds the app from a folder."""
        ...

    @property
    def formats(self) -> Formats:
        """Checks the app's file formats before a command runs."""
        ...

    @property
    def settings_loader(self) -> SettingsLoader:
        """Loads (and so validates) the app's settings before a command runs."""
        ...

    @property
    def stack_layer(self) -> Callable[[str], StackLayer]:
        """A stack's settings layer by stack name, for `settings_loader.load`."""
        ...

    def register_commands(self, commands: _Commands) -> None:
        """Add every command's parser; each leaf sets `run(args, out) -> int`."""
        ...


def builtin_stack_roots() -> list[Path]:
    """The built-in stack folders: `Modules/stack_*/<stack name>/`, sorted."""
    modules = Path(__file__).resolve().parent.parent
    return sorted(
        folder
        for folder in modules.glob("stack_*/*")
        if folder.is_dir()
        and folder.name not in _NOT_STACKS
        and not folder.name.startswith(("_", "."))
    )


@functools.cache
def get_wiring() -> _LiveWiring:
    """The real composition root, built once per process."""
    return _LiveWiring()


def run_hook(
    kind: str,
    raw: str,
    out: TextIO,
    err: TextIO,
    *,
    provider: Provider,
    hooks: Hooks,
) -> int:
    """Run hook `kind` (`session-start`, `before-shell`, …) on the provider's input `raw`.

    The provider parses the input and turns the decision into output and an exit code
    (a block uses its exit code and stderr). Never raises: if anything fails, the hook allows
    (exit 0, nothing on `out`) with the details on `err`, so a bull bug never stops a session.
    """
    try:
        hook_kind = _HOOK_KINDS[kind]
        event = provider.parse_hook(hook_kind, raw)
        decision = hooks.handle(event)
        output = provider.hook_output(hook_kind, decision)
    except Exception as error:  # noqa: BLE001 - a hook never fails the session
        err.write(
            f"bull hook {kind}: allowed after an error: {describe_error(error)}\n"
        )
        return 0
    out.write(output.stdout)
    err.write(output.stderr)
    return output.exit_code


def describe_error(error: Exception) -> str:
    """One line for an error: a `BullError`'s message and fix, else its type and text."""
    if isinstance(error, BullError):
        return f"{error.message} ({error.fix})" if error.fix else error.message
    return f"{type(error).__name__}: {error}"


class _LiveWiring:
    """Every real implementation; app-bound ones are built per app when a command runs."""

    def __init__(self) -> None:
        self.files: Files = LiveFiles()
        self.clock = LiveClock()
        self.runner = LiveRunner()
        self.git = LiveGit(self.runner)
        self.layouts: Layouts = LiveLayouts()
        self.registry: StackRegistry = LiveStackRegistry(
            sorted({root.parent for root in builtin_stack_roots()}),
            self.layouts.user_data_dir(),
        )
        # One wiring serves one command: each app's settings are loaded once, then shared by
        # the preamble and every collaborator.
        self.settings_loader: SettingsLoader = _CachingSettingsLoader(
            LiveSettingsLoader()
        )
        self.stack_layer: Callable[[str], StackLayer] = self._stack_layer
        self.memo_reader = LiveMemoReader()
        self.ideas: IdeaReader = LiveIdeaReader()
        self.parts: Parts = LiveParts(self.registry, self.settings_loader)
        self.triage = LiveCoverageTriage()
        self.provider: Provider = LiveProvider(LivePluginText(), self.clock)
        self.tester: StackTester = LiveStackTester((sys.executable, "-m", "bull"))
        self.workflow: StackWorkflow = LiveStackWorkflow(
            self.files, self.layouts, self.git, self.registry
        )
        self.app_formats: Formats = LiveFormats(self.git)
        self.formats: Formats = _AppFormats(self.app_formats, self._is_stack_repo)
        self.templates: Templates = _Templates(LiveTemplates())
        self.hooks: Hooks = _AppHooks(self)

    # --- the command table ---------------------------------------------------------------

    def register_commands(self, commands: _Commands) -> None:
        """Every module's commands, in the order of the Commands table."""
        appinit_cli.register(
            commands,
            app_init=self._app_init,
            doctor=self._doctor,
            stack_init=self._stack_init,
        )
        repo = self._stack_repo(Path.cwd())
        if repo is None:
            status_cli.register(
                commands,
                store=lambda: self._store(self._app()),
                refs=lambda: self._refs(self._app()),
                progress=lambda: self._progress(self._app()),
                usage=lambda: self._usage(self._app()),
                memo=lambda: self._memo(self._app()),
            )
        else:
            stackflow_cli.register_status(
                commands, workflow=lambda: self.workflow, root=lambda: repo.root
            )
        features_cli.register(
            commands,
            backlog=self._backlog,
            ideas=lambda: self.ideas,
            cycle=self._cycle,
        )
        adoption_cli.register(commands, self._adoption, self.layouts)
        gates_cli.register(
            commands,
            gates=self._gates,
            app=self._app,
            triage=lambda: self.triage,
        )
        api_cli.register(commands, snapshots=self._snapshots, app=self._app)
        stacks_cli.register(
            commands,
            registry=lambda: self.registry,
            ops=self._ops,
            app=self._app,
            settings=lambda: self._settings(self._app()),
            before_install=stackflow_cli.before_install(
                lambda: self.tester, lambda: self.registry
            ),
        )
        leaves = _subcommands(commands.choices["stack"])
        adoption_cli.register_detect(leaves, self._adoption, self.layouts)
        stacktest_cli.register(
            leaves,
            tester=lambda: _RecordingTester(self.tester, self._record_test),
            registry=lambda: self.registry,
        )
        parts_cli.register(commands, parts=lambda: self.parts, app=self._app)
        settings_cli.register(commands, settings=self._config_settings)
        formats_cli.register(commands, formats=lambda: self.app_formats, app=self._app)
        memo_cli.register(commands, templates=lambda: self.templates)
        self._register_hook(commands)
        self._register_statusline(commands)

    def _register_hook(self, commands: _Commands) -> None:
        hook = commands.add_parser("hook", help="Hook entry point (input on stdin)")
        hook.add_argument("kind", choices=list(_HOOK_KINDS), help="Which hook")

        def run(args: argparse.Namespace, out: TextIO) -> int:
            return run_hook(
                args.kind,
                sys.stdin.read(),
                out,
                sys.stderr,
                provider=self.provider,
                hooks=self.hooks,
            )

        hook.set_defaults(run=run)

    def _register_statusline(self, commands: _Commands) -> None:
        line = commands.add_parser(
            "statusline", help="Status line: record usage, print the line"
        )

        def run(args: argparse.Namespace, out: TextIO) -> int:
            return run_statusline(
                sys.stdin.read(),
                out,
                sys.stderr,
                provider=self.provider,
                layouts=_AppsOnly(self.layouts, self._is_stack_repo),
                usage=self._usage,
                progress=self._progress,
            )

        line.set_defaults(run=run)

    # --- finding the app -----------------------------------------------------------------

    def _app(self) -> AppLayout:
        """The bull app the current folder is in; a stack repo or no app is refused."""
        app = self.layouts.find(Path.cwd())
        if app is None:
            raise BullError(
                "not a bull app (no .bull/ folder here or above)",
                "run `bull init` in the app's folder, or cd into a bull app",
            )
        if self._is_stack_repo(app):
            raise BullError("this is a stack repo", _STACK_REPO_FIX)
        return app

    def _stack_repo(self, start: Path) -> AppLayout | None:
        """The stack repo `start` is in, or None."""
        found = self.layouts.find(start)
        if found is None or not self._is_stack_repo(found):
            return None
        return found

    def _is_stack_repo(self, app: AppLayout) -> bool:
        """True when the folder's status file has kind "stack".

        An unreadable status file counts as an app's, so the app commands report it.
        """
        try:
            data = self.files.read_json(app.status_file)
        except FileFormatError:
            return False
        return isinstance(data, dict) and data.get("kind") == "stack"

    # --- per-app builders ----------------------------------------------------------------

    def _stack_layer(self, name: str) -> StackLayer:
        """The named stack's settings; an unknown stack raises `StackError` (a problem)."""
        return self.registry.get(name).manifest.settings

    def _settings(self, app: AppLayout | None) -> Settings:
        """The app's settings (user layer only for None), loaded on first use."""
        return _LazySettings(lambda: self.settings_loader.load(app, self.stack_layer))

    def _config_settings(self) -> Settings:
        """Settings for `bull config`: the app's, or the user layer's outside an app."""
        app = self.layouts.find(Path.cwd())
        if app is not None and self._is_stack_repo(app):
            raise BullError("this is a stack repo", _STACK_REPO_FIX)
        return self._settings(app)

    def _events(self, app: AppLayout) -> EventLog:
        return LiveEventLog(app.events_file, self.files, self.clock)

    def _store(self, app: AppLayout) -> StatusStore:
        return LiveStatusStore(
            app,
            self.files,
            self._events(app),
            self.clock,
            self._settings(app),
            self.parts,
            self.memo_reader,
        )

    def _refs(self, app: AppLayout) -> Refs:
        return LiveRefs(self._settings(app), self._store(app))

    def _progress(self, app: AppLayout) -> Progress:
        store = self._store(app)
        return LiveProgress(app, store, LiveRefs(self._settings(app), store), self.git)

    def _usage(self, app: AppLayout) -> Usage:
        return LiveUsage(app, self.files, self._settings(app), self.clock)

    def _memo(self, app: AppLayout) -> Memo:
        """The app's parsed `docs/outline.md` (empty when the file is missing)."""
        return self.memo_reader.parse(self.files.read_text(app.memo_file) or "")

    def _interfaces(self, app: AppLayout) -> Interfaces:
        return LiveInterfaces(self.parts, self.registry, self._settings(app))

    def _ops(self) -> StackOps:
        return _AppOps(self.registry, self.runner, self._settings)

    # --- command providers ---------------------------------------------------------------

    def _app_init(self) -> LiveAppInit:
        return LiveAppInit(
            layouts=self.layouts,
            git=self.git,
            files=self.files,
            formats=self.app_formats,
            status=self._store,
            adoption=self._adoption(),
            stackflow=self.workflow,
            provider=self.provider,
            settings=self._settings,
            version=__version__,
            out=sys.stdout,
        )

    def _doctor(self) -> Doctor:
        version = sys.version_info
        return LiveDoctor(
            runner=self.runner,
            registry=self.registry,
            provider=self.provider,
            python_version=(version.major, version.minor, version.micro),
        )

    def _stack_init(self) -> Callable[[Path], InitResult]:
        return self._app_init().init_stack

    def _adoption(self) -> Adoption:
        return LiveAdoption(
            self.files,
            self.git,
            self.runner,
            self.registry,
            self._ops(),
            self.parts,
            self.memo_reader,
            self._settings,
            self._store,
            self._refs,
        )

    def _backlog(self) -> Backlog:
        return LiveBacklog(self._app(), self.files, self.clock, self.ideas)

    def _cycle(self) -> FeatureCycle:
        app = self._app()
        return LiveFeatureCycle(
            app,
            self.files,
            self.git,
            self.memo_reader,
            self._store(app),
            self._refs(app),
        )

    def _gates(self) -> Gates:
        events = self._events(self._app())
        return LiveGates(
            self.files,
            self.git,
            self.runner,
            events,
            self.clock,
            self.registry,
            self.parts,
            self.triage,
            LiveApiSnapshots(
                self.files,
                self.parts,
                self.registry,
                memo=lambda: self._memo(self._app()),
                store=self._store(self._app()),
            ),
            LivePassRecords(self.files, self.clock),
            JourneyRunner(
                self.runner, LiveSteps(self.runner, events, self.files), self.clock
            ),
            settings=self._settings,
            store=self._store,
            refs=self._refs,
            memo=self._memo,
            interfaces=self._interfaces,
        )

    def _snapshots(self) -> ApiSnapshots:
        app = self._app()
        return LiveApiSnapshots(
            self.files,
            self.parts,
            self.registry,
            memo=lambda: self._memo(app),
            store=self._store(app),
        )

    def _record_test(self, stack: Stack, report: StackTestReport) -> None:
        """After `bull stack test` on a stack repo's own folder, record the pass there."""
        home = stack.home.resolve()
        repo = self._stack_repo(home)
        if repo is not None and repo.root.resolve() == home:
            self.workflow.record_test(home, report)

    def live_hooks(self, app: AppLayout) -> Hooks:
        """The safeguards for `app`. Settings load on first use, so a broken config
        surfaces inside `LiveHooks`, which fails closed for guarded hooks."""
        settings = self._settings(app)
        events = self._events(app)
        store = LiveStatusStore(
            app,
            self.files,
            events,
            self.clock,
            settings,
            self.parts,
            self.memo_reader,
        )
        refs = LiveRefs(settings, store)
        progress = LiveProgress(app, store, refs, self.git)
        usage = LiveUsage(app, self.files, settings, self.clock)
        return LiveHooks(
            self.layouts,
            SessionStart(store, progress),
            UsageGuard(usage, store, settings, events),
            MergeGuard(
                self.git, LivePassRecords(self.files, self.clock), refs, store, events
            ),
            Protection(self.parts, settings),
            events,
            self.files,
        )


def _subcommands(parser: argparse.ArgumentParser) -> _Commands:
    """The subcommand table a parser (e.g. `stack`) was given by its module's `register`."""
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            found: _Commands = action
            return found
    raise RuntimeError(  # coverage-exempt: unreachable, the stacks module always adds subcommands
        f"`{parser.prog}` has no subcommands"
    )  # unreachable: stacks adds them


class _CachingSettingsLoader(SettingsLoader):
    """Loads each app's settings once (per app root and stack layer); failures are not kept."""

    def __init__(self, loader: SettingsLoader) -> None:
        self._loader = loader
        self._loaded: dict[
            tuple[Path | None, Callable[[str], StackLayer]], Settings
        ] = {}

    def load(
        self, app: AppLayout | None, stack_layer: Callable[[str], StackLayer]
    ) -> Settings:
        key = (None if app is None else app.root, stack_layer)
        found = self._loaded.get(key)
        if found is None:
            found = self._loader.load(app, stack_layer)
            self._loaded[key] = found
        return found


class _LazySettings(Settings):
    """Settings loaded on first use, so building a collaborator reads no file."""

    def __init__(self, load: Callable[[], Settings]) -> None:
        self._load = load
        self._loaded: Settings | None = None

    def _settings(self) -> Settings:
        if self._loaded is None:
            self._loaded = self._load()
        return self._loaded

    def schema(self) -> list[Setting]:
        return self._settings().schema()

    def get(self, key: str, part: str | None = None) -> SettingValue:
        return self._settings().get(key, part)

    def show(self, part: str | None = None) -> list[Resolved]:
        return self._settings().show(part)

    def set(
        self, key: str, raw: str, layer: Layer = Layer.APP, part: str | None = None
    ) -> Resolved:
        return self._settings().set(key, raw, layer, part)


class _AppOps(StackOps):
    """Stack operations with the settings of the app each call names."""

    def __init__(
        self,
        registry: StackRegistry,
        runner: Runner,
        settings: Callable[[AppLayout | None], Settings],
    ) -> None:
        self._registry = registry
        self._runner = runner
        self._settings = settings

    def _for(self, app: AppLayout | None) -> StackOps:
        return LiveStackOps(self._registry, self._settings(app), self._runner)

    def select(self, app: AppLayout, name: str) -> None:
        self._for(app).select(app, name)

    def rules(self, stack: Stack, agent: str) -> str:
        return self._for(None).rules(stack, agent)

    def setup_guide(self, stack: Stack, section: str | None = None) -> str:
        return self._for(None).setup_guide(stack, section)

    def check(self, app: AppLayout, part: str | None = None) -> list[CheckItem]:
        return self._for(app).check(app, part)

    def run_command(self, app: AppLayout, command: str, part: str | None = None) -> int:
        return self._for(app).run_command(app, command, part)


class _AppFormats(Formats):
    """Formats that leave a stack repo alone: only an app's files are checked."""

    def __init__(
        self, formats: Formats, is_stack_repo: Callable[[AppLayout], bool]
    ) -> None:
        self._formats = formats
        self._is_stack_repo = is_stack_repo

    def current(self) -> int:
        return self._formats.current()

    def inspect(self, app: AppLayout) -> list[FileFormat]:
        return self._formats.inspect(app)

    def check(self, app: AppLayout) -> None:
        if not self._is_stack_repo(app):
            self._formats.check(app)

    def migrate(self, app: AppLayout) -> list[Path]:
        return self._formats.migrate(app)


class _AppsOnly(Layouts):
    """Layouts whose `find` sees bull apps only (a stack repo is not an app)."""

    def __init__(
        self, layouts: Layouts, is_stack_repo: Callable[[AppLayout], bool]
    ) -> None:
        self._layouts = layouts
        self._is_stack_repo = is_stack_repo

    def at(self, root: Path) -> AppLayout:
        return self._layouts.at(root)

    def find(self, start: Path) -> AppLayout | None:
        found = self._layouts.find(start)
        if found is None or self._is_stack_repo(found):
            return None
        return found

    def user_config_dir(self) -> Path:
        return self._layouts.user_config_dir()

    def user_data_dir(self) -> Path:
        return self._layouts.user_data_dir()

    def machine_local_ignores(self) -> list[str]:
        return self._layouts.machine_local_ignores()


class _Templates(Templates):
    """memo's templates plus the stack repo's `design` (from stackflow)."""

    _DESIGN = "design"

    def __init__(self, templates: Templates) -> None:
        self._templates = templates

    def names(self) -> list[str]:
        return sorted([*self._templates.names(), self._DESIGN])

    def text(self, name: str) -> str:
        if name == self._DESIGN:
            return stackflow_cli.design_template()
        return self._templates.text(name)


class _RecordingTester(StackTester):
    """The stack tester; a full run or static run also records its result.

    `record` is called with each whole-suite report (`run` without a case, `static`); it
    records the pass only for a stack repo's own folder.
    """

    def __init__(
        self,
        tester: StackTester,
        record: Callable[[Stack, StackTestReport], None],
    ) -> None:
        self._tester = tester
        self._record = record

    def load_cases(self, stack: Stack) -> list[Case]:
        return self._tester.load_cases(stack)

    def static(self, stack: Stack) -> StackTestReport:
        report = self._tester.static(stack)
        self._record(stack, report)
        return report

    def run(self, stack: Stack, case: str | None = None) -> StackTestReport:
        report = self._tester.run(stack, case)
        if case is None:
            self._record(stack, report)
        return report

    def render(self, report: StackTestReport) -> str:
        return self._tester.render(report)


class _AppHooks(Hooks):
    """Builds the safeguards for the app found from each event's `cwd`, then handles it."""

    def __init__(self, wiring: _LiveWiring) -> None:
        self._wiring = wiring

    def handle(self, event: HookEvent) -> HookDecision:
        app = self._wiring.layouts.find(event.cwd)
        if app is None:
            return HookDecision(True, "")
        return self._wiring.live_hooks(app).handle(event)

    def merge_targets(self, command: str) -> list[str]:
        return merge_targets(command)
