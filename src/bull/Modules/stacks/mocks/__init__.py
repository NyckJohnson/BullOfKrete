"""Mocks of the stacks contract, for tests and previews."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from bull.Modules.foundation.Contracts import AppLayout
from bull.Modules.settings.Contracts import (
    Setting,
    SettingType,
    SettingValue,
    StackLayer,
)
from bull.Modules.stacks.Contracts import (
    CheckItem,
    CoverageData,
    GateCommands,
    Maturity,
    OptionalReaders,
    Requirement,
    Stack,
    StackError,
    StackKind,
    StackManifest,
    StackOps,
    StackReaders,
    StackRegistry,
    TestRun,
)

SAMPLE_STACK_HOME = Path("/tmp/bull/Modules/stack_fixture/fixture")


def sample_manifest(
    name: str = "fixture", maturity: Maturity = Maturity.TEST
) -> StackManifest:
    """A manifest shaped like the built-in `fixture` stack's."""
    step = ("{python}", "-m", "bull.Modules.stack_fixture.tool")
    return StackManifest(
        name=name,
        title="Fixture tool",
        description="A small, toolchain-free stack for bull's own tests.",
        language="fixture",
        kind=StackKind.TOOL,
        maturity=maturity,
        source_glob="*.fx",
        test_glob=("*.test",),
        comment="#",
        scaffold=("src", "tests"),
        gitignore=("results/",),
        agents=(
            "skeleton-builder",
            "test-writer",
            "code-writer",
            "reviewer",
            "coverage-analyst",
            "journey-test-writer",
        ),
        requires=(Requirement("git", "https://git-scm.com/downloads"),),
        settings=StackLayer(
            schema=(
                Setting("source_dir", SettingType.STR, "src/fx", "Source folder."),
                Setting("test_dir", SettingType.STR, "tests", "Test folder."),
            ),
            values={"source_dir": "src/fx", "test_dir": "tests"},
        ),
        gates=GateCommands(
            preflight=(*step, "preflight"),
            setup=(*step, "setup"),
            build_test=(*step, "build-test"),
            build_test_fast=(*step, "build-test-fast", "{module}"),
            lint=(*step, "lint", "{module}"),
            rerun_failed=(*step, "rerun", "{failed_ids}"),
            journeys=(*step, "journeys"),
        ),
        run=None,
        interface_formats=("json-schema",),
        commands={},
    )


class MockStackReaders(StackReaders):
    """Ten tests, none failing; everything covered; every check passing."""

    def __init__(self) -> None:
        self.declarations: list[str] = ["pub counter.increment", "pub counter.value"]
        self.run: TestRun | None = TestRun(count=10, failed=())
        self.coverage = CoverageData(uncovered={}, no_data=())
        self.items: list[CheckItem] = [CheckItem(True, "fixture.toml present", "")]
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def contract_declarations(self, path: Path) -> list[str]:
        self.calls.append(("contract_declarations", (path,)))
        return list(self.declarations)

    def test_results(self, results: Path) -> TestRun | None:
        self.calls.append(("test_results", (results,)))
        return self.run

    def uncovered(
        self, part_root: Path, sources: Sequence[Path], results: Path
    ) -> CoverageData:
        self.calls.append(("uncovered", (part_root, tuple(sources), results)))
        return self.coverage

    def check(
        self, part_root: Path, settings: Mapping[str, SettingValue], adopting: bool
    ) -> list[CheckItem]:
        self.calls.append(("check", (part_root, dict(settings), adopting)))
        return list(self.items)


def sample_stack(name: str = "fixture", maturity: Maturity = Maturity.TEST) -> Stack:
    return Stack(
        manifest=sample_manifest(name, maturity),
        home=SAMPLE_STACK_HOME.parent / name,
        builtin=True,
        readers=MockStackReaders(),
        optional=OptionalReaders(
            detect=None, inventory=None, legacy_declarations=None, interface_check=None
        ),
    )


class MockStackRegistry(StackRegistry):
    """Holds `fixture` (test maturity) and `python_cli` (experimental)."""

    def __init__(self) -> None:
        self.stacks: dict[str, Stack] = {
            "fixture": sample_stack("fixture", Maturity.TEST),
            "python_cli": sample_stack("python_cli", Maturity.EXPERIMENTAL),
        }
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def all(self, include_test: bool = False) -> list[Stack]:
        self.calls.append(("all", (include_test,)))
        return [
            stack
            for name, stack in sorted(self.stacks.items())
            if include_test or stack.manifest.maturity is not Maturity.TEST
        ]

    def get(self, name: str) -> Stack:
        self.calls.append(("get", (name,)))
        if name not in self.stacks:
            raise StackError(
                f"unknown stack `{name}`; known: {', '.join(sorted(self.stacks))}"
            )
        return self.stacks[name]

    def load_path(self, path: Path) -> Stack:
        self.calls.append(("load_path", (path,)))
        return sample_stack(path.name, Maturity.EXPERIMENTAL)

    def install(self, path: Path) -> Stack:
        self.calls.append(("install", (path,)))
        stack = sample_stack(path.name, Maturity.EXPERIMENTAL)
        self.stacks[path.name] = stack
        return stack


class MockStackOps(StackOps):
    def __init__(self) -> None:
        self.items: list[CheckItem] = [
            CheckItem(True, "git on PATH", ""),
            CheckItem(True, "source folder src/fx exists", ""),
        ]
        self.exit_code = 0
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def select(self, app: AppLayout, name: str) -> None:
        self.calls.append(("select", (app, name)))

    def rules(self, stack: Stack, agent: str) -> str:
        self.calls.append(("rules", (stack, agent)))
        return f"# {stack.manifest.title}: rules\n\n## common\n- Keep it small.\n\n## {agent}\n"

    def setup_guide(self, stack: Stack, section: str | None = None) -> str:
        self.calls.append(("setup_guide", (stack, section)))
        return "# Setup\n\n1. Create `fixture.toml` at the part root.\n"

    def check(self, app: AppLayout, part: str | None = None) -> list[CheckItem]:
        self.calls.append(("check", (app, part)))
        return list(self.items)

    def run_command(self, app: AppLayout, command: str, part: str | None = None) -> int:
        self.calls.append(("run_command", (app, command, part)))
        return self.exit_code
