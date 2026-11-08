"""The status store: reads, validates and writes `.bull/status.json`.

`LiveStatusStore` owns create, load, mode and the write path. Every other change goes
load → apply → validate → atomic write → one `status` event (`what` = the method name).
The apply step is a pure function in `transitions` or `modules`, called through the module
(not imported by name) so it can be replaced in tests. A refusal raises `StatusError` from
that function before anything is written or logged. A change that leaves the status as it
was (a no-op) writes and logs nothing. The one refusal that saves its change is `attempt`
at the limit: the unit is saved `blocked`, then `StatusError` is raised.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence

from bull.Modules.events.Contracts import EventKind, EventLog, EventValue
from bull.Modules.foundation.Contracts import AppLayout, Clock, Files
from bull.Modules.memo.Contracts import Memo, MemoReader, ModuleEntry
from bull.Modules.parts.Contracts import Parts
from bull.Modules.settings.Contracts import Settings
from bull.Modules.status import model, modules, transitions
from bull.Modules.status.Contracts import (
    Approval,
    Mode,
    ModuleState,
    Status,
    StatusError,
    StatusStore,
    Track,
    Unit,
    UnitState,
)


class LiveStatusStore(StatusStore):
    """The real `StatusStore`, over the app's `.bull/status.json`."""

    def __init__(
        self,
        app: AppLayout,
        files: Files,
        events: EventLog,
        clock: Clock,
        settings: Settings,
        parts: Parts,
        memo_reader: MemoReader,
    ) -> None:
        self._app = app
        self._files = files
        self._events = events
        self._clock = clock
        self._settings = settings
        self._parts = parts
        self._memo_reader = memo_reader

    # --- reading, creating, mode ------------------------------------------------------

    def load(self) -> Status:
        """The stored status.

        Raises `StatusError` when the file is missing or belongs to a stack repo, and
        `FileFormatError` when it is malformed.
        """
        data = self._files.read_json(self._app.status_file)
        if data is None:
            raise StatusError(
                "not a bull app (no .bull/status.json)",
                "run `bull init` in the app's folder, or cd into a bull app",
            )
        if isinstance(data, dict) and data.get("kind") == "stack":
            raise StatusError(
                "this is a stack repo", "use the stack commands here, not the app's"
            )
        return model.status_from_json(data)

    def create(self) -> Status:
        """Write a new app status (stage 0); refused when the file already exists."""
        if self._files.read_text(self._app.status_file) is not None:
            raise StatusError(
                ".bull/status.json already exists",
                "this folder is already a bull app; run `bull status` to see it",
            )
        status = Status(
            model.FORMAT, Track(0, ()), (), None, None, (), None, None, None
        )
        self._write(status, "create", {})
        return status

    def mode(self) -> Mode:
        """ADOPT while an adoption is active, else FEATURE while a feature is, else APP."""
        status = self.load()
        if status.adoption is not None:
            return Mode.ADOPT
        if status.feature is not None:
            return Mode.FEATURE
        return Mode.APP

    # --- the write path ---------------------------------------------------------------

    def _write(self, status: Status, what: str, data: dict[str, EventValue]) -> None:
        payload = model.status_to_json(status)
        # Validate: what we write must read back as the same status.
        if model.status_from_json(payload) != status:
            raise StatusError(  # coverage-exempt: round-trip check cannot fail for a status the transitions produce
                f"{what}: the new status does not round-trip; nothing written"
            )
        text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        self._files.write_atomic(self._app.status_file, text)
        self._events.append(EventKind.STATUS, what=what, **data)

    def _apply(
        self,
        what: str,
        apply: Callable[[Status], Status],
        **data: EventValue,
    ) -> tuple[Status, bool]:
        """Apply, and write and log unless nothing changed; returns (new, written)."""
        old = self.load()
        new = apply(old)
        if new == old:
            return old, False
        self._write(new, what, data)
        return new, True

    def _change(
        self,
        what: str,
        apply: Callable[[Status], Status],
        **data: EventValue,
    ) -> Status:
        return self._apply(what, apply, **data)[0]

    def _int_setting(self, key: str) -> int:
        value = self._settings.get(key, None)
        if isinstance(value, bool) or not isinstance(value, int):
            raise StatusError(f"setting {key} must be an integer, not {value!r}")
        return value

    def _known_parts(self) -> list[str]:
        return [part.name for part in self._parts.all(self._app)]

    # --- delegated changes ------------------------------------------------------------

    def set_stage(self, stage: int) -> Status:
        return self._change(
            "set_stage", lambda s: transitions.set_stage(s, stage), stage=stage
        )

    def checkpoint(self, name: str) -> Status:
        return self._change(
            "checkpoint", lambda s: transitions.checkpoint(s, name), checkpoint=name
        )

    def init_modules(self, memo: Memo, replace: bool = False) -> Status:
        known_parts = self._known_parts()
        problems = self._memo_reader.problems(
            memo, known_parts, self._int_setting("max_files_per_unit")
        )
        return self._change(
            "init_modules",
            lambda s: modules.init_modules(
                s, memo, replace, known_parts=known_parts, problems=problems
            ),
            replace=replace,
        )

    def set_module(self, name: str, state: ModuleState) -> Status:
        return self._change(
            "set_module",
            lambda s: modules.set_module(s, name, state),
            module=name,
            state=state.value,
        )

    def set_unit(self, name: str, number: int, state: UnitState) -> Status:
        return self._change(
            "set_unit",
            lambda s: transitions.set_unit(s, name, number, state),
            module=name,
            unit=number,
            state=state.value,
        )

    def attempt(self, name: str, number: int) -> Unit:
        """Start another attempt at a unit and return it.

        At `max_attempts` the unit is saved `blocked` (written and logged) and then
        `StatusError` "unit n blocked after <max_attempts> attempts; ask the human" is raised.
        """
        max_attempts = self._int_setting("max_attempts")
        old = self.load()
        new, unit = transitions.attempt(old, name, number, max_attempts=max_attempts)
        if new != old:
            self._write(
                new,
                "attempt",
                {
                    "module": name,
                    "unit": number,
                    "state": unit.state.value,
                    "attempts": unit.attempts,
                },
            )
        if unit.state == UnitState.BLOCKED:
            raise StatusError(
                f"unit {number} blocked after {max_attempts} attempts; ask the human",
                f"once the human decides, `bull status unblock {name} {number}` "
                "starts it again",
            )
        return unit

    def unblock(self, name: str, number: int) -> Status:
        return self._change(
            "unblock",
            lambda s: transitions.unblock(s, name, number),
            module=name,
            unit=number,
        )

    def pause(self, reason: str) -> Status:
        now = self._clock.now()
        new, written = self._apply(
            "pause", lambda s: transitions.pause(s, reason, now=now), reason=reason
        )
        if written:
            self._events.append(
                EventKind.PAUSE,
                reason=reason,
                unit=None if new.pause is None else new.pause.unit,
            )
        return new

    def resume(self) -> Status:
        new, written = self._apply("resume", transitions.resume)
        if written:
            self._events.append(EventKind.RESUME)
        return new

    def wait(self, module: str, what: str) -> Status:
        now = self._clock.now()
        return self._change(
            "wait",
            lambda s: transitions.wait(s, module, what, now=now),
            module=module,
            detail=what,
        )

    def approve(self, module: str, note: str) -> Status:
        now = self._clock.now()
        new, written = self._apply(
            "approve",
            lambda s: transitions.approve(s, module, note, now=now),
            module=module,
        )
        if written:
            self._events.append(
                EventKind.DECISION, what="approve", module=module, note=note
            )
        return new

    def take_approval(self, module: str) -> Approval | None:
        old = self.load()
        new, approval = transitions.take_approval(old, module)
        if new != old:
            self._write(new, "take_approval", {"module": module})
        return approval

    def record_scan(
        self, module: str, covered: int, missed: int, contradicts: int, not_in_spec: int
    ) -> Status:
        now = self._clock.now()
        return self._change(
            "record_scan",
            lambda s: transitions.record_scan(
                s, module, covered, missed, contradicts, not_in_spec, now=now
            ),
            module=module,
            covered=covered,
            missed=missed,
            contradicts=contradicts,
            not_in_spec=not_in_spec,
        )

    def set_plan(self, label: str, items: Sequence[str]) -> Status:
        items = tuple(items)
        return self._change(
            "set_plan", lambda s: transitions.set_plan(s, label, items), label=label
        )

    def tick(self, item: str) -> Status:
        return self._change("tick", lambda s: transitions.tick(s, item), item=item)

    def clear_plan(self) -> Status:
        return self._change("clear_plan", transitions.clear_plan)

    def start_feature(self, slug: str) -> Status:
        return self._change(
            "start_feature", lambda s: transitions.start_feature(s, slug), slug=slug
        )

    def end_feature(self) -> Status:
        return self._change("end_feature", transitions.end_feature)

    def mark_contract_applied(self, module: str) -> Status:
        return self._change(
            "mark_contract_applied",
            lambda s: transitions.mark_contract_applied(s, module),
            module=module,
        )

    def reopen(self, module: str, files: Sequence[str]) -> Status:
        files = tuple(files)
        return self._change(
            "reopen", lambda s: modules.reopen(s, module, files), module=module
        )

    def add_modules(self, entries: Sequence[ModuleEntry]) -> Status:
        entries = tuple(entries)
        known_parts = self._known_parts()
        return self._change(
            "add_modules",
            lambda s: modules.add_modules(s, entries, known_parts=known_parts),
            modules=",".join(e.name for e in entries),
        )

    def start_adoption(self) -> Status:
        return self._change("start_adoption", transitions.start_adoption)

    def finish_adoption(self) -> Status:
        return self._change("finish_adoption", transitions.finish_adoption)

    def abandon_adoption(self) -> Status:
        return self._change("abandon_adoption", transitions.abandon_adoption)
