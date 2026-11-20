"""`bull statusline`: record the usage sample and print the one-line status."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import TextIO

from bull.Modules.claude_code.Contracts import Provider
from bull.Modules.foundation.Contracts import AppLayout, Layouts
from bull.Modules.status.Contracts import Progress
from bull.Modules.usage.Contracts import Usage, UsageSample

_SEPARATOR = " · "
_PLAIN = "bull"
_NO_CONTEXT = "ctx \u2013"


def run_statusline(
    raw: str,
    out: TextIO,
    err: TextIO,
    *,
    provider: Provider,
    layouts: Layouts,
    usage: Callable[[AppLayout], Usage],
    progress: Callable[[AppLayout], Progress],
) -> int:
    """Print one status line to `out` and return 0; never raises.

    `raw` is the provider's status-line input (stdin). The app is found from the input's
    `cwd`; outside an app the line is just `bull`. The input's usage sample is recorded with
    `Usage.record`; the line shows its 5-hour and weekly figures, or the latest recorded
    sample's when the input has none. A context-only input sample is merged with the saved
    sample's 5-hour, weekly and reset values before it is recorded. The final `ctx` part comes
    only from the input's sample (`ctx –` when it has no context figure).
    Anything that goes wrong prints `bull` (or the line without the failed part, when only
    recording failed) with the details on `err`: the status line must never break the session.
    """
    try:
        line = _line(raw, err, provider, layouts, usage, progress)
    except Exception as error:  # noqa: BLE001 - never fails: plain line
        _report(err, error)
        line = _PLAIN
    out.write(line + "\n")
    return 0


def _line(
    raw: str,
    err: TextIO,
    provider: Provider,
    layouts: Layouts,
    usage: Callable[[AppLayout], Usage],
    progress: Callable[[AppLayout], Progress],
) -> str:
    """The status line's text; raises when the input or the status cannot be read."""
    given = provider.parse_statusline(raw)
    app = layouts.find(given.cwd)
    if app is None:
        return _PLAIN
    # The sample is recorded first, so a broken status still stores it.
    sample = _sample(usage, app, given.usage, err)
    data = progress(app).as_json()
    context = given.usage.context if given.usage is not None else None
    return _SEPARATOR.join(
        [_PLAIN, *_status_parts(data), *_usage_parts(sample), _context_part(context)]
    )


def _sample(
    usage: Callable[[AppLayout], Usage],
    app: AppLayout,
    given: UsageSample | None,
    err: TextIO,
) -> UsageSample | None:
    """Record `given` (if any) and return the sample to show.

    A failed record or read (or a usage store that cannot be built) is reported on `err`;
    the line is still printed. A `given` sample with neither a 5-hour nor a weekly figure takes
    those figures and their resets from the latest saved sample (when there is one), so
    recording it never erases them.
    """
    try:
        store = usage(app)
    except Exception as error:  # noqa: BLE001 - no usage store: the usage parts are omitted
        _report(err, error)
        return given
    if given is not None:
        if given.five_hour is None and given.weekly is None:
            given = _merged(store, given, err)
        try:
            store.record(given)
        except Exception as error:  # noqa: BLE001 - recording is best effort; the line still shows
            _report(err, error)
        return given
    try:
        return store.latest()
    except Exception as error:  # noqa: BLE001 - no readable sample: the usage parts are omitted
        _report(err, error)
        return None


def _merged(store: Usage, given: UsageSample, err: TextIO) -> UsageSample:
    """`given` with the saved sample's 5-hour, weekly and reset values; `given` when none.

    A failed read is reported on `err` and `given` is kept as it is.
    """
    try:
        saved = store.latest()
    except Exception as error:  # noqa: BLE001 - no readable sample: record the input as is
        _report(err, error)
        return given
    if saved is None:
        return given
    return replace(saved, time=given.time, context=given.context)


def _status_parts(data: Mapping[str, object]) -> list[str]:
    """`stage N`, `feature <slug>`, `units d/t`, `<plan label> i/n`; missing ones omitted."""
    parts: list[str] = []
    stage = data.get("stage")
    if isinstance(stage, int):
        parts.append(f"stage {stage}")
    feature = data.get("feature")
    if isinstance(feature, Mapping):
        slug = feature.get("slug")
        if isinstance(slug, str) and slug:
            parts.append(f"feature {slug}")
    done, total = data.get("units_done"), data.get("units_total")
    if isinstance(done, int) and isinstance(total, int):
        parts.append(f"units {done}/{total}")
    plan = data.get("plan")
    if isinstance(plan, Mapping):
        label, items = plan.get("label"), plan.get("items")
        if isinstance(label, str) and isinstance(items, list):
            finished = sum(
                1
                for item in items
                if isinstance(item, Mapping) and item.get("done") is True
            )
            parts.append(f"{label} {finished}/{len(items)}")
    return parts


def _usage_parts(sample: UsageSample | None) -> list[str]:
    """`5h x%` and `wk y%`, each omitted when the sample lacks it."""
    if sample is None:
        return []
    parts: list[str] = []
    if sample.five_hour is not None:
        parts.append(f"5h {round(sample.five_hour)}%")
    if sample.weekly is not None:
        parts.append(f"wk {round(sample.weekly)}%")
    return parts


def _context_part(context: float | None) -> str:
    """`ctx z%` from the input's context figure, or `ctx –` when there is none."""
    if context is None:
        return _NO_CONTEXT
    return f"ctx {round(context)}%"


def _report(err: TextIO, error: Exception) -> None:
    """One line on `err` naming what went wrong."""
    err.write(f"bull statusline: {type(error).__name__}: {error}\n")
