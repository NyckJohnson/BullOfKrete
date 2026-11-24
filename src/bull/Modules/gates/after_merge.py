"""After a merge: record without rerunning when the merge holds the gated code."""

from __future__ import annotations

from collections.abc import Sequence

from bull.Modules.foundation.Contracts import AppLayout, BullError
from bull.Modules.gates.Contracts import PassRecord, PassRecords
from bull.Modules.gitrepo.Contracts import Git


def after_merge_skip(
    app: AppLayout,
    branch: str,
    git: Git,
    passes: PassRecords,
    bookkeeping: Sequence[str],
) -> PassRecord | None:
    """The branch head's pass record when the merge changed only bookkeeping paths.

    Returns None when the branch head was never gated or any path changed between the
    branch head and HEAD lies outside `bookkeeping`. Raises `BullError` for an unknown
    branch, or for a name that is both a branch and a tag (`refs/heads/<name>` is never
    ambiguous and is accepted).
    """
    if git.branch_exists(app.root, branch) and branch in git.tags(app.root, branch):
        raise BullError(
            f"{branch} names both a branch and a tag", f"use `refs/heads/{branch}`"
        )
    head = git.head(app.root, branch)
    if head is None:
        raise BullError(f"no branch {branch}")
    record = passes.get(app, head)
    if record is None:
        return None
    changed = git.changed_paths(app.root, head, "HEAD")
    if all(_is_bookkeeping(path, bookkeeping) for path in changed):
        return record
    return None


def _is_bookkeeping(path: str, bookkeeping: Sequence[str]) -> bool:
    """An entry ending in `/` matches paths under it; any other the path itself or under it."""
    for entry in bookkeeping:
        if entry.endswith("/"):
            if path.startswith(entry):
                return True
        elif path == entry or path.startswith(f"{entry}/"):
            return True
    return False
