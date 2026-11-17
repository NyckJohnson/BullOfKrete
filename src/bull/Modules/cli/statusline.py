"""`bull statusline`: record the usage sample and print the one-line status."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TextIO

from bull.Modules.claude_code.Contracts import Provider
from bull.Modules.foundation.Contracts import AppLayout, Layouts
from bull.Modules.status.Contracts import Progress
from bull.Modules.usage.Contracts import Usage, UsageSample

_SEPARATOR = " · "
_PLAIN = "bull"


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
    `Usage.record`; the line shows it, or the latest recorded sample when the input has none.
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
    data = progress(app).as_json()
    sample = _sample(usage(app), given.usage, err)
    return _SEPARATOR.join([_PLAIN, *_status_parts(data), *_usage_parts(sample)])


def _sample(usage: Usage, given: UsageSample | None, err: TextIO) -> UsageSample | None:
    """Record `given` (if any) and return the sample to show.

    A failed record or read is reported on `err`; the line is still printed.
    """
    if given is not None:
        try:
            usage.record(given)
        except Exception as error:  # noqa: BLE001 - recording is best effort; the line still shows
            _report(err, error)
        return given
    try:
        return usage.latest()
    except Exception as error:  # noqa: BLE001 - no readable sample: the usage parts are omitted
        _report(err, error)
        return None


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


def _report(err: TextIO, error: Exception) -> None:
    """One line on `err` naming what went wrong."""
    err.write(f"bull statusline: {type(error).__name__}: {error}\n")
