"""Stage, checkpoint, unit and attempt transitions and their rules.

Each function is pure: it takes the current `Status` first, then the store method's
arguments, then keyword-only context, and returns the new `Status` (or raises
`StatusError` on refusal). `LiveStatusStore` calls them through this module.
Implemented in unit 3.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from bull.Modules.status.Contracts import Approval, Status, Unit, UnitState


def set_stage(status: Status, stage: int) -> Status:
    raise NotImplementedError("transitions.set_stage")


def checkpoint(status: Status, name: str) -> Status:
    raise NotImplementedError("transitions.checkpoint")


def set_unit(status: Status, name: str, number: int, state: UnitState) -> Status:
    raise NotImplementedError("transitions.set_unit")


def attempt(
    status: Status, name: str, number: int, *, max_attempts: int
) -> tuple[Status, Unit]:
    raise NotImplementedError("transitions.attempt")


def unblock(status: Status, name: str, number: int) -> Status:
    raise NotImplementedError("transitions.unblock")


def pause(status: Status, reason: str, *, now: datetime) -> Status:
    raise NotImplementedError("transitions.pause")


def resume(status: Status) -> Status:
    raise NotImplementedError("transitions.resume")


def wait(status: Status, module: str, what: str, *, now: datetime) -> Status:
    raise NotImplementedError("transitions.wait")


def approve(status: Status, module: str, note: str, *, now: datetime) -> Status:
    raise NotImplementedError("transitions.approve")


def take_approval(status: Status, module: str) -> tuple[Status, Approval | None]:
    raise NotImplementedError("transitions.take_approval")


def record_scan(
    status: Status,
    module: str,
    covered: int,
    missed: int,
    contradicts: int,
    not_in_spec: int,
    *,
    now: datetime,
) -> Status:
    raise NotImplementedError("transitions.record_scan")


def set_plan(status: Status, label: str, items: Sequence[str]) -> Status:
    raise NotImplementedError("transitions.set_plan")


def tick(status: Status, item: str) -> Status:
    raise NotImplementedError("transitions.tick")


def clear_plan(status: Status) -> Status:
    raise NotImplementedError("transitions.clear_plan")


def start_feature(status: Status, slug: str) -> Status:
    raise NotImplementedError("transitions.start_feature")


def end_feature(status: Status) -> Status:
    raise NotImplementedError("transitions.end_feature")


def mark_contract_applied(status: Status, module: str) -> Status:
    raise NotImplementedError("transitions.mark_contract_applied")


def start_adoption(status: Status) -> Status:
    raise NotImplementedError("transitions.start_adoption")


def finish_adoption(status: Status) -> Status:
    raise NotImplementedError("transitions.finish_adoption")


def abandon_adoption(status: Status) -> Status:
    raise NotImplementedError("transitions.abandon_adoption")
