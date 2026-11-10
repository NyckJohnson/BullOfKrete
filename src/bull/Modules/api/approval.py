"""The approval rule for writing a changed snapshot."""

from __future__ import annotations

from collections.abc import Mapping

from bull.Modules.api.Contracts import ApprovalNeeded
from bull.Modules.status.Contracts import Mode, StatusStore


def authorize(
    name: str,
    approved: str | None,
    store: StatusStore,
    contract_changes: Mapping[str, str],
) -> None:
    """Allow writing the changed snapshot of `name`, or raise `ApprovalNeeded`.

    Called only when the snapshot changed. Checked in order:
    1. an `approved` note: recorded through `store.approve` (which logs the `decision`
       event), then consumed with `store.take_approval`;
    2. an approval already stored for `name` (consumed);
    3. FEATURE mode, the active feature's slug listed in `contract_changes`, and `name` not
       yet in its `applied_contracts`: marked applied, so the pre-approval covers one write.
    """
    if approved is not None:
        store.approve(name, approved)
        store.take_approval(name)
        return
    if store.take_approval(name) is not None:
        return
    if store.mode() is Mode.FEATURE:
        feature = store.load().feature
        if (
            feature is not None
            and feature.slug in contract_changes
            and name not in feature.applied_contracts
        ):
            store.mark_contract_applied(name)
            return
    raise ApprovalNeeded(
        f"the {name} contract changed; the human must approve "
        f'(bull status approve {name} "<note>")',
        f'run `bull status approve {name} "<note>"` after the human agrees, then write again',
    )
