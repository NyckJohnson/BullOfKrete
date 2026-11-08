"""The status file's JSON model: reading and writing `Status`.

`status_to_json` gives the documented `status.json` shape (see the memo's Data models);
`status_from_json` reads it back, refusing anything malformed with a `FileFormatError` that
names the offending field (for example `modules[0].units[0].attempts`).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from enum import Enum
from typing import TypeVar

from bull.Modules.foundation.Contracts import FileFormatError
from bull.Modules.status.Contracts import (
    ActiveFeature,
    Approval,
    ModuleState,
    ModuleStatus,
    Pause,
    Plan,
    PlanItem,
    ScanRecord,
    Status,
    Track,
    Unit,
    UnitKind,
    UnitState,
    Waiting,
)

FORMAT = 1
KIND = "app"
MIN_STAGE = 0
MAX_STAGE = 6

_T = TypeVar("_T")
_E = TypeVar("_E", bound=Enum)


# --- writing ---------------------------------------------------------------------------


def time_to_text(time: datetime) -> str:
    """ISO 8601 UTC with a `Z` suffix; a naive time is taken to be UTC already."""
    if time.tzinfo is None:
        time = time.replace(tzinfo=UTC)
    return time.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _track_to_json(track: Track) -> dict[str, object]:
    return {"stage": track.stage, "checkpoints": list(track.checkpoints)}


def _unit_to_json(unit: Unit) -> dict[str, object]:
    return {
        "number": unit.number,
        "files": list(unit.files),
        "kind": unit.kind.value,
        "state": unit.state.value,
        "attempts": unit.attempts,
    }


def _scan_to_json(scan: ScanRecord | None) -> dict[str, object] | None:
    if scan is None:
        return None
    return {
        "time": time_to_text(scan.time),
        "covered": scan.covered,
        "missed": scan.missed,
        "contradicts": scan.contradicts,
        "not_in_spec": scan.not_in_spec,
    }


def _module_to_json(module: ModuleStatus) -> dict[str, object]:
    return {
        "name": module.name,
        "part": module.part,
        "depends": list(module.depends),
        "state": module.state.value,
        "reference_tests": module.reference_tests,
        "scan": _scan_to_json(module.scan),
        "units": [_unit_to_json(u) for u in module.units],
    }


def status_to_json(status: Status) -> dict[str, object]:
    """The JSON object stored in `.bull/status.json` for `status`."""
    pause = status.pause
    waiting = status.waiting
    plan = status.plan
    feature = status.feature
    return {
        "format": status.format,
        "kind": KIND,
        "stage": status.app.stage,
        "checkpoints": list(status.app.checkpoints),
        "modules": [_module_to_json(m) for m in status.modules],
        "pause": None
        if pause is None
        else {
            "reason": pause.reason,
            "since": time_to_text(pause.since),
            "unit": pause.unit,
        },
        "waiting": None
        if waiting is None
        else {
            "module": waiting.module,
            "what": waiting.what,
            "since": time_to_text(waiting.since),
        },
        "approvals": [
            {"module": a.module, "note": a.note, "time": time_to_text(a.time)}
            for a in status.approvals
        ],
        "plan": None
        if plan is None
        else {
            "label": plan.label,
            "items": [{"name": i.name, "done": i.done} for i in plan.items],
        },
        "feature": None
        if feature is None
        else {
            "slug": feature.slug,
            "stage": feature.track.stage,
            "checkpoints": list(feature.track.checkpoints),
            "applied_contracts": list(feature.applied_contracts),
        },
        "adoption": None
        if status.adoption is None
        else _track_to_json(status.adoption),
    }


# --- reading ---------------------------------------------------------------------------


def _bad(where: str, expected: str) -> FileFormatError:
    return FileFormatError(
        f"status.json: {where or 'the file'} must be {expected}",
        "fix the field or restore .bull/status.json from git",
    )


class _Obj:
    """A JSON object being read, with the path used in error messages."""

    def __init__(self, data: object, where: str) -> None:
        if not isinstance(data, dict):
            raise _bad(where, "an object")
        self._data: dict[object, object] = data
        self._where = where

    def _path(self, key: str) -> str:
        return f"{self._where}.{key}" if self._where else key

    def _get(self, key: str) -> object:
        if key not in self._data:
            raise FileFormatError(
                f"status.json: missing field {self._path(key)}",
                "fix the field or restore .bull/status.json from git",
            )
        return self._data[key]

    def int_(self, key: str, low: int | None = None, high: int | None = None) -> int:
        """The integer at `key`, refused outside `low`..`high` (each bound optional)."""
        value = self._get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            raise _bad(self._path(key), "an integer")
        if (low is not None and value < low) or (high is not None and value > high):
            if high is None:
                raise _bad(self._path(key), f"an integer of at least {low}")
            if low is None:
                raise _bad(self._path(key), f"an integer of at most {high}")
            raise _bad(self._path(key), f"an integer from {low} to {high}")
        return value

    def bool_(self, key: str) -> bool:
        value = self._get(key)
        if not isinstance(value, bool):
            raise _bad(self._path(key), "true or false")
        return value

    def str_(self, key: str) -> str:
        value = self._get(key)
        if not isinstance(value, str):
            raise _bad(self._path(key), "a string")
        return value

    def opt_str(self, key: str) -> str | None:
        value = self._get(key)
        if value is not None and not isinstance(value, str):
            raise _bad(self._path(key), "a string or null")
        return value

    def strs(self, key: str) -> tuple[str, ...]:
        items = self.list_(key)
        result: list[str] = []
        for index, item in enumerate(items):
            if not isinstance(item, str):
                raise _bad(f"{self._path(key)}[{index}]", "a string")
            result.append(item)
        return tuple(result)

    def list_(self, key: str) -> list[object]:
        value = self._get(key)
        if not isinstance(value, list):
            raise _bad(self._path(key), "a list")
        return value

    def objs(self, key: str, read: Callable[[_Obj], _T]) -> tuple[_T, ...]:
        path = self._path(key)
        return tuple(
            read(_Obj(item, f"{path}[{index}]"))
            for index, item in enumerate(self.list_(key))
        )

    def opt_obj(self, key: str, read: Callable[[_Obj], _T]) -> _T | None:
        value = self._get(key)
        if value is None:
            return None
        return read(_Obj(value, self._path(key)))

    def enum(self, key: str, kind: type[_E]) -> _E:
        text = self.str_(key)
        for member in kind:
            if member.value == text:
                return member
        allowed = ", ".join(str(m.value) for m in kind)
        raise _bad(self._path(key), f"one of {allowed}")

    def time(self, key: str) -> datetime:
        text = self.str_(key)
        try:
            time = datetime.fromisoformat(text)
        except ValueError:
            raise _bad(self._path(key), "an ISO 8601 UTC time") from None
        if time.tzinfo is None:
            raise _bad(self._path(key), "an ISO 8601 UTC time")
        return time.astimezone(UTC)


def _read_unit(obj: _Obj) -> Unit:
    return Unit(
        number=obj.int_("number", low=1),
        files=obj.strs("files"),
        kind=obj.enum("kind", UnitKind),
        state=obj.enum("state", UnitState),
        attempts=obj.int_("attempts", low=1),
    )


def _read_scan(obj: _Obj) -> ScanRecord:
    return ScanRecord(
        time=obj.time("time"),
        covered=obj.int_("covered", low=0),
        missed=obj.int_("missed", low=0),
        contradicts=obj.int_("contradicts", low=0),
        not_in_spec=obj.int_("not_in_spec", low=0),
    )


def _read_module(obj: _Obj) -> ModuleStatus:
    return ModuleStatus(
        name=obj.str_("name"),
        part=obj.str_("part"),
        depends=obj.strs("depends"),
        state=obj.enum("state", ModuleState),
        units=obj.objs("units", _read_unit),
        reference_tests=obj.bool_("reference_tests"),
        scan=obj.opt_obj("scan", _read_scan),
    )


def _read_pause(obj: _Obj) -> Pause:
    return Pause(
        reason=obj.str_("reason"), since=obj.time("since"), unit=obj.opt_str("unit")
    )


def _read_waiting(obj: _Obj) -> Waiting:
    return Waiting(
        module=obj.str_("module"), what=obj.str_("what"), since=obj.time("since")
    )


def _read_approval(obj: _Obj) -> Approval:
    return Approval(
        module=obj.str_("module"), note=obj.str_("note"), time=obj.time("time")
    )


def _read_plan_item(obj: _Obj) -> PlanItem:
    return PlanItem(name=obj.str_("name"), done=obj.bool_("done"))


def _read_plan(obj: _Obj) -> Plan:
    return Plan(label=obj.str_("label"), items=obj.objs("items", _read_plan_item))


def _read_track(obj: _Obj) -> Track:
    return Track(
        stage=obj.int_("stage", low=MIN_STAGE, high=MAX_STAGE),
        checkpoints=obj.strs("checkpoints"),
    )


def _read_feature(obj: _Obj) -> ActiveFeature:
    return ActiveFeature(
        slug=obj.str_("slug"),
        track=_read_track(obj),
        applied_contracts=obj.strs("applied_contracts"),
    )


def status_from_json(data: object) -> Status:
    """Read a `Status` from the JSON in `.bull/status.json`.

    Raises `FileFormatError` naming the field when anything is missing, wrongly typed, an
    unknown enum string or a bad time, or when `format`/`kind` are not the supported ones.
    """
    obj = _Obj(data, "")
    version = obj.int_("format")
    if version != FORMAT:
        raise _bad("format", f"{FORMAT} (this bull reads status format {FORMAT})")
    if obj.str_("kind") != KIND:
        raise _bad("kind", f'"{KIND}"')
    return Status(
        format=version,
        app=_read_track(obj),
        modules=obj.objs("modules", _read_module),
        pause=obj.opt_obj("pause", _read_pause),
        waiting=obj.opt_obj("waiting", _read_waiting),
        approvals=obj.objs("approvals", _read_approval),
        plan=obj.opt_obj("plan", _read_plan),
        feature=obj.opt_obj("feature", _read_feature),
        adoption=obj.opt_obj("adoption", _read_track),
    )
