"""Gate-pass records in `.bull/passes/<sha>.json`."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime

from bull.Modules.foundation.Contracts import AppLayout, Clock, Files
from bull.Modules.gates.Contracts import PassRecord, PassRecords

_FORMAT = 1
_TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class LivePassRecords(PassRecords):
    """Pass records as `{format: 1, sha, branch, command, time, parts}` JSON files."""

    def __init__(self, files: Files, clock: Clock) -> None:
        self._files = files
        self._clock = clock

    def record(
        self,
        app: AppLayout,
        sha: str,
        branch: str | None,
        command: str,
        parts: Sequence[str],
    ) -> None:
        now = self._clock.now()
        # A naive clock time is taken to be UTC; an aware one is converted to UTC.
        now = now.replace(tzinfo=UTC) if now.tzinfo is None else now.astimezone(UTC)
        doc: dict[str, object] = {
            "format": _FORMAT,
            "sha": sha,
            "branch": branch,
            "command": command,
            "time": now.strftime(_TIME_FORMAT),
            "parts": list(parts),
        }
        self._files.write_json(app.passes_dir / f"{sha}.json", doc)

    def get(self, app: AppLayout, sha: str) -> PassRecord | None:
        """The record for `sha`, or None when it is missing or malformed (never raises)."""
        text = self._files.read_text(app.passes_dir / f"{sha}.json")
        if text is None:
            return None
        try:
            doc: object = json.loads(text)
        except ValueError:
            return None
        return _parse(doc)


def _parse(doc: object) -> PassRecord | None:
    if not isinstance(doc, dict):
        return None
    fmt = doc.get("format")
    if type(fmt) is not int or fmt != _FORMAT:
        return None
    sha = doc.get("sha")
    command = doc.get("command")
    time_text = doc.get("time")
    parts = doc.get("parts")
    if "branch" not in doc:
        return None
    branch = doc["branch"]
    if not isinstance(sha, str) or not isinstance(command, str):
        return None
    if branch is not None and not isinstance(branch, str):
        return None
    if not isinstance(time_text, str):
        return None
    if not isinstance(parts, list) or not all(isinstance(p, str) for p in parts):
        return None
    try:
        time = datetime.strptime(time_text, _TIME_FORMAT).replace(tzinfo=UTC)
    except ValueError:
        return None
    return PassRecord(
        sha=sha,
        branch=branch,
        command=command,
        time=time,
        parts=tuple(str(p) for p in parts),
    )
