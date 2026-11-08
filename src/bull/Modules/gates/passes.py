"""Gate-pass records in `.bull/passes/<sha>.json`."""

from __future__ import annotations

from collections.abc import Sequence

from bull.Modules.foundation.Contracts import AppLayout
from bull.Modules.gates.Contracts import PassRecord, PassRecords


class LivePassRecords(PassRecords):
    def record(
        self,
        app: AppLayout,
        sha: str,
        branch: str | None,
        command: str,
        parts: Sequence[str],
    ) -> None:
        raise NotImplementedError(f"{type(self).__name__}.record")

    def get(self, app: AppLayout, sha: str) -> PassRecord | None:
        raise NotImplementedError(f"{type(self).__name__}.get")
