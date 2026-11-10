"""Interfaces between parts: memo entries, sides, checks and parts to run."""

from __future__ import annotations

from bull.Modules.foundation.Contracts import AppLayout, BullError
from bull.Modules.interfaces.Contracts import InterfaceResult, Interfaces
from bull.Modules.memo.Contracts import InterfaceEntry, Memo, SideRef
from bull.Modules.parts.Contracts import Parts
from bull.Modules.settings.Contracts import SettingValue, Settings
from bull.Modules.stacks.Contracts import CheckItem, Role, Stack, StackRegistry


class LiveInterfaces(Interfaces):
    """Interfaces read from the memo, checked through each side's part and stack.

    `settings` is the app's loaded settings; a side's settings are its part's resolved values.
    """

    def __init__(self, parts: Parts, stacks: StackRegistry, settings: Settings) -> None:
        self._parts = parts
        self._stacks = stacks
        self._settings = settings

    def for_module(self, memo: Memo, module: str) -> list[tuple[InterfaceEntry, Role]]:
        found: list[tuple[InterfaceEntry, Role]] = []
        for entry in memo.interfaces:
            if entry.provider.module == module:
                found.append((entry, Role.PROVIDER))
            elif any(c.module == module for c in entry.consumers):
                found.append((entry, Role.CONSUMER))
        return found

    def problems(self, app: AppLayout, memo: Memo) -> list[str]:
        lines: list[str] = []

        def add(line: str) -> None:
            if line not in lines:
                lines.append(line)

        for entry in memo.interfaces:
            if not (app.root / entry.file).is_file():
                add(f"interface {entry.name}: file {entry.file} not found")
            for side in (entry.provider, *entry.consumers):
                stack = self._side_stack(app, side)
                name = stack.manifest.name
                if entry.format not in stack.manifest.interface_formats:
                    add(
                        f"interface {entry.name}: format {entry.format} is not supported"
                        f" by the {name} stack (part {side.part})"
                    )
                if stack.optional.interface_check is None:
                    add(
                        f"interface {entry.name}: the {name} stack has no interface check"
                        f" (part {side.part})"
                    )
        return lines

    def check_module(
        self, app: AppLayout, memo: Memo, module: str
    ) -> list[InterfaceResult]:
        results: list[InterfaceResult] = []
        for entry, role in self.for_module(memo, module):
            side = _module_side(entry, role, module)
            part = self._parts.get(app, side.part)
            stack = self._stacks.get(part.stack)
            check = stack.optional.interface_check
            if check is None:
                items: tuple[CheckItem, ...] = (
                    CheckItem(
                        False,
                        f"interface check for {entry.format}",
                        f"the {stack.manifest.name} stack has no interface check",
                    ),
                )
            else:
                items = tuple(
                    check(
                        part.root,
                        self._side_settings(side.part),
                        app.root / entry.file,
                        entry.format,
                        role,
                        module,
                    )
                )
            results.append(
                InterfaceResult(
                    interface=entry.name,
                    part=side.part,
                    module=module,
                    role=role,
                    items=items,
                )
            )
        return results

    def parts_to_run(self, memo: Memo, part: str) -> list[str]:
        order = {b.name: i for i, b in enumerate(memo.build_order)}
        last = len(order)
        # (build-order position, memo position, provider part); providers missing from the
        # build order sort after every known one, keeping memo order among themselves.
        ranked: list[tuple[int, int, str]] = []
        for index, entry in enumerate(memo.interfaces):
            if not any(c.part == part for c in entry.consumers):
                continue
            provider = entry.provider
            if provider.part == part:
                continue
            ranked.append((order.get(provider.module, last), index, provider.part))
        found: list[str] = []
        for _, _, provider_part in sorted(ranked):
            if provider_part in found:
                continue
            if self._stack_of_part(provider_part).manifest.run is not None:
                found.append(provider_part)
        return found

    def _side_stack(self, app: AppLayout, side: SideRef) -> Stack:
        return self._stacks.get(self._parts.get(app, side.part).stack)

    def _side_settings(self, part: str) -> dict[str, SettingValue]:
        return {r.key: r.value for r in self._settings.show(part)}

    def _stack_of_part(self, part: str) -> Stack:
        """The part's stack by its `stack` setting (used where no app layout is at hand)."""
        name = self._settings.get("stack", part)
        if not isinstance(name, str):
            raise BullError(
                f"part {part}: the stack setting is not a name",
                "set the part's stack to a stack name",
            )
        return self._stacks.get(name)


def _module_side(entry: InterfaceEntry, role: Role, module: str) -> SideRef:
    """The side of `entry` that `module` is on, for the role `for_module` gave it."""
    if role is Role.PROVIDER:
        return entry.provider
    return next(c for c in entry.consumers if c.module == module)
