"""Mocks of the interfaces contract, for tests and previews."""

from __future__ import annotations

from bull.Modules.foundation.Contracts import AppLayout
from bull.Modules.interfaces.Contracts import InterfaceResult, Interfaces
from bull.Modules.memo.Contracts import InterfaceEntry, Memo, SideRef
from bull.Modules.stacks.Contracts import CheckItem, Role

SAMPLE_INTERFACE = InterfaceEntry(
    name="TallyEvents",
    file="interfaces/tally-events.json",
    format="json-schema",
    provider=SideRef("cli", "Export"),
    consumers=(SideRef("web", "Import"),),
    contract_changes={},
)


class MockInterfaces(Interfaces):
    """Journey 7's `TallyEvents`: provider `cli / Export`, consumer `web / Import`."""

    def __init__(self) -> None:
        self.entries: list[InterfaceEntry] = [SAMPLE_INTERFACE]
        self.found_problems: list[str] = []
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def for_module(self, memo: Memo, module: str) -> list[tuple[InterfaceEntry, Role]]:
        self.calls.append(("for_module", (memo, module)))
        found: list[tuple[InterfaceEntry, Role]] = []
        for entry in self.entries:
            if entry.provider.module == module:
                found.append((entry, Role.PROVIDER))
            elif any(c.module == module for c in entry.consumers):
                found.append((entry, Role.CONSUMER))
        return found

    def problems(self, app: AppLayout, memo: Memo) -> list[str]:
        self.calls.append(("problems", (app, memo)))
        return list(self.found_problems)

    def check_module(
        self, app: AppLayout, memo: Memo, module: str
    ) -> list[InterfaceResult]:
        self.calls.append(("check_module", (app, memo, module)))
        return [
            InterfaceResult(
                interface=entry.name,
                part=entry.provider.part
                if role is Role.PROVIDER
                else next(c.part for c in entry.consumers if c.module == module),
                module=module,
                role=role,
                items=(CheckItem(True, f"{role.value} fields match the schema", ""),),
            )
            for entry, role in self.for_module(memo, module)
        ]

    def parts_to_run(self, memo: Memo, part: str) -> list[str]:
        self.calls.append(("parts_to_run", (memo, part)))
        return ["web"] if part == "cli" else []
