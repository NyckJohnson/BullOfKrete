"""Tests for `bull.Modules.interfaces.interfaces`."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from bull.Modules.foundation.Contracts import AppLayout, BullError
from bull.Modules.foundation.mocks import sample_layout
from bull.Modules.interfaces.interfaces import LiveInterfaces
from bull.Modules.memo.Contracts import BuildEntry, InterfaceEntry, Memo, SideRef
from bull.Modules.parts.Contracts import Part
from bull.Modules.parts.mocks import MockParts
from bull.Modules.settings.Contracts import Layer, Resolved, SettingValue
from bull.Modules.settings.mocks import MockSettings
from bull.Modules.stacks.Contracts import (
    CheckItem,
    OptionalReaders,
    Role,
    RunCommands,
    Stack,
)
from bull.Modules.stacks.mocks import MockStackRegistry, sample_stack

Call = tuple[Path, dict[str, SettingValue], Path, str, Role, str]


class FakeSettings(MockSettings):
    """Per-part settings: `show(part)` lists that part's entries; `get("stack", part)`."""

    def __init__(
        self,
        stacks: Mapping[str, str],
        values: Mapping[str, Mapping[str, SettingValue]],
    ):
        super().__init__()
        self._stack_of = dict(stacks)
        self._values = {k: dict(v) for k, v in values.items()}

    def get(self, key: str, part: str | None = None) -> SettingValue:
        if key == "stack" and part is not None:
            return self._stack_of[part]
        return super().get(key, part)

    def show(self, part: str | None = None) -> list[Resolved]:
        assert part is not None
        return [
            Resolved(k, v, Layer.PART, None)
            for k, v in self._values.get(part, {}).items()
        ]


def _stack(
    name: str,
    formats: tuple[str, ...] = ("json-schema",),
    check: bool = True,
    run: bool = False,
    calls: list[Call] | None = None,
    items: list[CheckItem] | None = None,
) -> Stack:
    base = sample_stack(name)

    def interface_check(
        part_root: Path,
        settings: Mapping[str, SettingValue],
        file: Path,
        fmt: str,
        role: Role,
        module: str,
    ) -> list[CheckItem]:
        if calls is not None:
            calls.append((part_root, dict(settings), file, fmt, role, module))
        return list(items) if items is not None else [CheckItem(True, "ok", "")]

    manifest = replace(
        base.manifest,
        interface_formats=formats,
        run=RunCommands(
            start=("serve",), ready=("ping",), stop=("halt",), ready_timeout=5.0
        )
        if run
        else None,
    )
    optional = OptionalReaders(
        detect=None,
        inventory=None,
        legacy_declarations=None,
        interface_check=interface_check if check else None,
    )
    return replace(base, manifest=manifest, optional=optional)


def _entry(
    name: str = "TallyEvents",
    file: str = "interfaces/tally-events.json",
    fmt: str = "json-schema",
    provider: SideRef | None = None,
    consumers: tuple[SideRef, ...] | None = None,
) -> InterfaceEntry:
    provider = provider if provider is not None else SideRef("cli", "Export")
    if consumers is None:
        consumers = (SideRef("web", "Import"),)
    return InterfaceEntry(
        name=name,
        file=file,
        format=fmt,
        provider=provider,
        consumers=consumers,
        contract_changes={},
    )


def _memo(*entries: InterfaceEntry, order: tuple[str, ...] = ()) -> Memo:
    return Memo(
        build_order=tuple(BuildEntry(n, (), i) for i, n in enumerate(order)),
        modules=(),
        journeys=(),
        interfaces=tuple(entries),
        parts=(),
        unmapped_reference_tests=(),
        legacy=None,
    )


def _live(
    root: Path,
    stacks: dict[str, Stack],
    part_stack: dict[str, str],
    settings: dict[str, dict[str, SettingValue]] | None = None,
) -> tuple[LiveInterfaces, AppLayout]:
    app = sample_layout(root)
    parts = MockParts()
    parts.parts = [
        Part(
            name=name,
            stack=stack,
            dir=name,
            root=root / name,
            source_dir=Path("src"),
            test_dir=Path("tests"),
        )
        for name, stack in part_stack.items()
    ]
    registry = MockStackRegistry()
    registry.stacks = dict(stacks)
    fake = FakeSettings(part_stack, settings or {})
    return LiveInterfaces(parts, registry, fake), app


def _write(app: AppLayout, entry: InterfaceEntry) -> None:
    path = app.root / entry.file
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}")


# ---------------------------------------------------------------- for_module


def test_for_module_provider_gets_provider_role(tmp_path: Path) -> None:
    entry = _entry()
    live, _ = _live(tmp_path, {}, {})
    assert live.for_module(_memo(entry), "Export") == [(entry, Role.PROVIDER)]


def test_for_module_consumer_gets_consumer_role(tmp_path: Path) -> None:
    entry = _entry()
    live, _ = _live(tmp_path, {}, {})
    assert live.for_module(_memo(entry), "Import") == [(entry, Role.CONSUMER)]


def test_for_module_second_consumer_gets_consumer_role(tmp_path: Path) -> None:
    entry = _entry(consumers=(SideRef("web", "Import"), SideRef("mobile", "Sync")))
    live, _ = _live(tmp_path, {}, {})
    assert live.for_module(_memo(entry), "Sync") == [(entry, Role.CONSUMER)]


def test_for_module_returns_interfaces_in_memo_order(tmp_path: Path) -> None:
    first = _entry(name="A")
    second = _entry(name="B", provider=SideRef("web", "Import"), consumers=())
    third = _entry(name="C", consumers=(SideRef("web", "Import"),))
    live, _ = _live(tmp_path, {}, {})
    assert live.for_module(_memo(first, second, third), "Import") == [
        (first, Role.CONSUMER),
        (second, Role.PROVIDER),
        (third, Role.CONSUMER),
    ]


def test_for_module_module_in_no_interface_is_empty(tmp_path: Path) -> None:
    live, _ = _live(tmp_path, {}, {})
    assert live.for_module(_memo(_entry()), "Other") == []


def test_for_module_matches_module_name_exactly(tmp_path: Path) -> None:
    live, _ = _live(tmp_path, {}, {})
    assert live.for_module(_memo(_entry()), "export") == []
    assert live.for_module(_memo(_entry()), "Exp") == []


def test_for_module_with_no_interfaces_is_empty(tmp_path: Path) -> None:
    live, _ = _live(tmp_path, {}, {})
    assert live.for_module(_memo(), "Export") == []


# ------------------------------------------------------------------ problems


def test_problems_empty_when_file_exists_and_both_sides_support_it(
    tmp_path: Path,
) -> None:
    entry = _entry()
    live, app = _live(
        tmp_path,
        {"pya": _stack("pya"), "pyb": _stack("pyb")},
        {"cli": "pya", "web": "pyb"},
    )
    _write(app, entry)
    assert live.problems(app, _memo(entry)) == []


def test_problems_reports_missing_interface_file(tmp_path: Path) -> None:
    entry = _entry()
    live, app = _live(
        tmp_path,
        {"pya": _stack("pya"), "pyb": _stack("pyb")},
        {"cli": "pya", "web": "pyb"},
    )
    assert live.problems(app, _memo(entry)) == [
        "interface TallyEvents: file interfaces/tally-events.json not found"
    ]


def test_problems_missing_file_reported_once_with_several_consumers(
    tmp_path: Path,
) -> None:
    entry = _entry(consumers=(SideRef("web", "Import"), SideRef("mobile", "Sync")))
    stacks = {"pya": _stack("pya")}
    live, app = _live(tmp_path, stacks, {"cli": "pya", "web": "pya", "mobile": "pya"})
    problems = live.problems(app, _memo(entry))
    assert (
        problems.count(
            "interface TallyEvents: file interfaces/tally-events.json not found"
        )
        == 1
    )


def test_problems_reports_format_unsupported_by_consumer_stack(
    tmp_path: Path,
) -> None:
    entry = _entry()
    live, app = _live(
        tmp_path,
        {"pya": _stack("pya"), "pyb": _stack("pyb", formats=("openapi",))},
        {"cli": "pya", "web": "pyb"},
    )
    _write(app, entry)
    assert live.problems(app, _memo(entry)) == [
        "interface TallyEvents: format json-schema is not supported by the pyb stack (part web)"
    ]


def test_problems_reports_format_unsupported_by_provider_stack(
    tmp_path: Path,
) -> None:
    entry = _entry()
    live, app = _live(
        tmp_path,
        {"pya": _stack("pya", formats=()), "pyb": _stack("pyb")},
        {"cli": "pya", "web": "pyb"},
    )
    _write(app, entry)
    assert live.problems(app, _memo(entry)) == [
        "interface TallyEvents: format json-schema is not supported by the pya stack (part cli)"
    ]


def test_problems_reports_stack_without_interface_check(tmp_path: Path) -> None:
    entry = _entry()
    live, app = _live(
        tmp_path,
        {"pya": _stack("pya"), "pyb": _stack("pyb", check=False)},
        {"cli": "pya", "web": "pyb"},
    )
    _write(app, entry)
    assert live.problems(app, _memo(entry)) == [
        "interface TallyEvents: the pyb stack has no interface check (part web)"
    ]


def test_problems_orders_file_then_provider_then_consumers(tmp_path: Path) -> None:
    entry = _entry(consumers=(SideRef("web", "Import"), SideRef("mobile", "Sync")))
    stacks = {
        "pya": _stack("pya", formats=(), check=False),
        "pyb": _stack("pyb", formats=(), check=False),
        "pyc": _stack("pyc", formats=(), check=False),
    }
    live, app = _live(tmp_path, stacks, {"cli": "pya", "web": "pyb", "mobile": "pyc"})
    assert live.problems(app, _memo(entry)) == [
        "interface TallyEvents: file interfaces/tally-events.json not found",
        "interface TallyEvents: format json-schema is not supported by the pya stack (part cli)",
        "interface TallyEvents: the pya stack has no interface check (part cli)",
        "interface TallyEvents: format json-schema is not supported by the pyb stack (part web)",
        "interface TallyEvents: the pyb stack has no interface check (part web)",
        "interface TallyEvents: format json-schema is not supported by the pyc stack (part mobile)",
        "interface TallyEvents: the pyc stack has no interface check (part mobile)",
    ]


def test_problems_follow_memo_order_across_interfaces(tmp_path: Path) -> None:
    first = _entry(name="First", file="interfaces/first.json")
    second = _entry(name="Second", file="interfaces/second.json")
    live, app = _live(
        tmp_path,
        {"pya": _stack("pya"), "pyb": _stack("pyb")},
        {"cli": "pya", "web": "pyb"},
    )
    assert live.problems(app, _memo(first, second)) == [
        "interface First: file interfaces/first.json not found",
        "interface Second: file interfaces/second.json not found",
    ]


def test_problems_have_no_duplicate_lines(tmp_path: Path) -> None:
    entry = _entry(consumers=(SideRef("web", "Import"), SideRef("web", "Sync")))
    live, app = _live(
        tmp_path,
        {"pya": _stack("pya"), "pyb": _stack("pyb", check=False)},
        {"cli": "pya", "web": "pyb"},
    )
    _write(app, entry)
    assert live.problems(app, _memo(entry)) == [
        "interface TallyEvents: the pyb stack has no interface check (part web)"
    ]


def test_problems_empty_when_memo_has_no_interfaces(tmp_path: Path) -> None:
    live, app = _live(tmp_path, {}, {})
    assert live.problems(app, _memo()) == []


# -------------------------------------------------------------- check_module


def test_check_module_calls_interface_check_with_full_arguments(
    tmp_path: Path,
) -> None:
    calls: list[Call] = []
    entry = _entry()
    live, app = _live(
        tmp_path,
        {"pya": _stack("pya", calls=calls), "pyb": _stack("pyb")},
        {"cli": "pya", "web": "pyb"},
        settings={"cli": {"source_dir": "src/x", "strict": True}},
    )
    live.check_module(app, _memo(entry), "Export")
    assert calls == [
        (
            tmp_path / "cli",
            {"source_dir": "src/x", "strict": True},
            app.root / "interfaces/tally-events.json",
            "json-schema",
            Role.PROVIDER,
            "Export",
        )
    ]


def test_check_module_consumer_uses_consumer_side_part_stack_and_settings(
    tmp_path: Path,
) -> None:
    provider_calls: list[Call] = []
    consumer_calls: list[Call] = []
    entry = _entry()
    live, app = _live(
        tmp_path,
        {
            "pya": _stack("pya", calls=provider_calls),
            "pyb": _stack("pyb", calls=consumer_calls),
        },
        {"cli": "pya", "web": "pyb"},
        settings={"cli": {"k": "cli"}, "web": {"k": "web"}},
    )
    live.check_module(app, _memo(entry), "Import")
    assert provider_calls == []
    assert consumer_calls == [
        (
            tmp_path / "web",
            {"k": "web"},
            app.root / entry.file,
            "json-schema",
            Role.CONSUMER,
            "Import",
        )
    ]


def test_check_module_returns_one_result_with_checker_items(tmp_path: Path) -> None:
    items = [CheckItem(True, "a", ""), CheckItem(False, "b", "fix b")]
    live, app = _live(
        tmp_path,
        {"pya": _stack("pya", items=items), "pyb": _stack("pyb")},
        {"cli": "pya", "web": "pyb"},
    )
    results = live.check_module(app, _memo(_entry()), "Export")
    assert len(results) == 1
    result = results[0]
    assert (result.interface, result.part, result.module, result.role) == (
        "TallyEvents",
        "cli",
        "Export",
        Role.PROVIDER,
    )
    assert result.items == tuple(items)
    assert result.ok is False


def test_check_module_one_result_per_interface_in_memo_order(tmp_path: Path) -> None:
    first = _entry(name="First")
    second = _entry(name="Second", provider=SideRef("web", "Import"), consumers=())
    live, app = _live(
        tmp_path,
        {"pya": _stack("pya"), "pyb": _stack("pyb")},
        {"cli": "pya", "web": "pyb"},
    )
    results = live.check_module(app, _memo(first, second), "Import")
    assert [(r.interface, r.part, r.role) for r in results] == [
        ("First", "web", Role.CONSUMER),
        ("Second", "web", Role.PROVIDER),
    ]


def test_check_module_without_interface_check_gives_failing_item(
    tmp_path: Path,
) -> None:
    live, app = _live(
        tmp_path,
        {"pya": _stack("pya", check=False), "pyb": _stack("pyb")},
        {"cli": "pya", "web": "pyb"},
    )
    results = live.check_module(app, _memo(_entry()), "Export")
    assert len(results) == 1
    assert results[0].items == (
        CheckItem(
            False,
            "interface check for json-schema",
            "the pya stack has no interface check",
        ),
    )
    assert results[0].ok is False


def test_check_module_with_no_interfaces_is_empty(tmp_path: Path) -> None:
    live, app = _live(
        tmp_path,
        {"pya": _stack("pya"), "pyb": _stack("pyb")},
        {"cli": "pya", "web": "pyb"},
    )
    assert live.check_module(app, _memo(_entry()), "Other") == []


# ------------------------------------------------------------- parts_to_run


def _run_world(
    tmp_path: Path, runs: dict[str, bool]
) -> tuple[LiveInterfaces, dict[str, str]]:
    stacks = {f"s_{p}": _stack(f"s_{p}", run=r) for p, r in runs.items()}
    part_stack = {p: f"s_{p}" for p in runs}
    live, _ = _live(tmp_path, stacks, part_stack)
    return live, part_stack


def test_parts_to_run_returns_providers_part_of_consumed_interface(
    tmp_path: Path,
) -> None:
    live, _ = _run_world(tmp_path, {"cli": True, "web": False})
    memo = _memo(_entry(), order=("Export", "Import"))
    assert live.parts_to_run(memo, "web") == ["cli"]


def test_parts_to_run_ignores_interfaces_the_part_does_not_consume(
    tmp_path: Path,
) -> None:
    live, _ = _run_world(tmp_path, {"cli": True, "web": True})
    memo = _memo(_entry(), order=("Export", "Import"))
    assert live.parts_to_run(memo, "cli") == []


def test_parts_to_run_skips_providers_whose_stack_has_no_run(tmp_path: Path) -> None:
    live, _ = _run_world(tmp_path, {"cli": False, "web": False})
    memo = _memo(_entry(), order=("Export", "Import"))
    assert live.parts_to_run(memo, "web") == []


def test_parts_to_run_excludes_the_part_itself(tmp_path: Path) -> None:
    entry = _entry(provider=SideRef("web", "Serve"), consumers=(SideRef("web", "Use"),))
    live, _ = _run_world(tmp_path, {"web": True})
    assert live.parts_to_run(_memo(entry, order=("Serve", "Use")), "web") == []


def test_parts_to_run_orders_by_provider_module_build_order(tmp_path: Path) -> None:
    first = _entry(
        name="A", provider=SideRef("alpha", "Late"), consumers=(SideRef("web", "Use"),)
    )
    second = _entry(
        name="B", provider=SideRef("beta", "Early"), consumers=(SideRef("web", "Use"),)
    )
    live, _ = _run_world(tmp_path, {"alpha": True, "beta": True, "web": False})
    memo = _memo(first, second, order=("Early", "Late", "Use"))
    assert live.parts_to_run(memo, "web") == ["beta", "alpha"]


def test_parts_to_run_puts_provider_missing_from_build_order_last(
    tmp_path: Path,
) -> None:
    unknown = _entry(
        name="A", provider=SideRef("alpha", "Ghost"), consumers=(SideRef("web", "Use"),)
    )
    known = _entry(
        name="B", provider=SideRef("beta", "Known"), consumers=(SideRef("web", "Use"),)
    )
    live, _ = _run_world(tmp_path, {"alpha": True, "beta": True, "web": False})
    memo = _memo(unknown, known, order=("Known", "Use"))
    assert live.parts_to_run(memo, "web") == ["beta", "alpha"]


def test_parts_to_run_missing_providers_keep_memo_order(tmp_path: Path) -> None:
    one = _entry(
        name="A", provider=SideRef("alpha", "G1"), consumers=(SideRef("web", "Use"),)
    )
    two = _entry(
        name="B", provider=SideRef("beta", "G2"), consumers=(SideRef("web", "Use"),)
    )
    live, _ = _run_world(tmp_path, {"alpha": True, "beta": True, "web": False})
    assert live.parts_to_run(_memo(one, two), "web") == ["alpha", "beta"]


def test_parts_to_run_lists_each_part_once(tmp_path: Path) -> None:
    one = _entry(
        name="A", provider=SideRef("cli", "Export"), consumers=(SideRef("web", "Use"),)
    )
    two = _entry(
        name="B", provider=SideRef("cli", "Export"), consumers=(SideRef("web", "Use"),)
    )
    three = _entry(
        name="C", provider=SideRef("cli", "Other"), consumers=(SideRef("web", "Use"),)
    )
    live, _ = _run_world(tmp_path, {"cli": True, "web": False})
    memo = _memo(one, two, three, order=("Export", "Other", "Use"))
    assert live.parts_to_run(memo, "web") == ["cli"]


def test_parts_to_run_with_no_interfaces_is_empty(tmp_path: Path) -> None:
    live, _ = _run_world(tmp_path, {"web": False})
    assert live.parts_to_run(_memo(), "web") == []


def test_parts_to_run_non_string_stack_setting_raises_not_a_name() -> None:
    registry = MockStackRegistry()
    registry.stacks = {"s_web": _stack("s_web")}
    settings = FakeSettings({"cli": cast(str, 7), "web": "s_web"}, {})
    live = LiveInterfaces(MockParts(), registry, settings)
    memo = _memo(_entry(), order=("Export", "Import"))
    with pytest.raises(BullError) as caught:
        live.parts_to_run(memo, "web")
    assert caught.value.message == "part cli: the stack setting is not a name"
    assert caught.value.fix == "set the part's stack to a stack name"
