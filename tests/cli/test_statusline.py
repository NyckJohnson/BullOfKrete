"""Tests for `bull.Modules.cli.statusline`: record usage and print the one-line status."""

from __future__ import annotations

import io
from datetime import UTC, datetime
from pathlib import Path

from bull.Modules.claude_code.Contracts import StatusLineInput
from bull.Modules.claude_code.mocks import MockProvider
from bull.Modules.cli.statusline import run_statusline
from bull.Modules.foundation.Contracts import AppLayout
from bull.Modules.foundation.mocks import MockLayouts, sample_layout
from bull.Modules.status.Contracts import Progress
from bull.Modules.status.mocks import MockProgress
from bull.Modules.usage.Contracts import Usage, UsageSample
from bull.Modules.usage.mocks import MockUsage

_NOW = datetime(2026, 11, 7, 12, 0, 0, tzinfo=UTC)


def _sample(
    five: float | None, weekly: float | None, context: float | None = None
) -> UsageSample:
    return UsageSample(
        time=_NOW,
        five_hour=five,
        weekly=weekly,
        five_hour_resets=None,
        weekly_resets=None,
        context=context,
    )


class _Provider(MockProvider):
    """A provider whose statusline input is set by the test."""

    def __init__(self, cwd: Path, usage: UsageSample | None) -> None:
        super().__init__()
        self.cwd = cwd
        self.sample = usage

    def parse_statusline(self, raw: str) -> StatusLineInput:
        self.calls.append(("parse_statusline", (raw,)))
        return StatusLineInput(cwd=self.cwd, usage=self.sample)


class _BrokenProvider(MockProvider):
    def parse_statusline(self, raw: str) -> StatusLineInput:
        raise ValueError("not a statusline payload")


class _Progress(MockProgress):
    def __init__(self, data: dict[str, object]) -> None:
        super().__init__()
        self.data = data

    def as_json(self) -> dict[str, object]:
        self.calls.append(("as_json", ()))
        return self.data


class _BrokenProgress(MockProgress):
    def as_json(self) -> dict[str, object]:
        raise RuntimeError("status file unreadable")


class _BrokenUsage(MockUsage):
    def record(self, sample: UsageSample) -> None:
        raise OSError("disk full")


def _status(
    stage: int = 5,
    done: int = 1,
    total: int = 3,
    feature: str | None = None,
    plan: tuple[str, int, int] | None = None,
) -> dict[str, object]:
    data: dict[str, object] = {
        "format": 1,
        "kind": "app",
        "stage": stage,
        "units_done": done,
        "units_total": total,
        "plan": None,
        "feature": None,
    }
    if feature is not None:
        data["feature"] = {
            "slug": feature,
            "stage": stage,
            "checkpoints": [],
            "applied_contracts": [],
        }
    if plan is not None:
        label, finished, count = plan
        data["plan"] = {
            "label": label,
            "items": [{"name": f"item{n}", "done": n < finished} for n in range(count)],
        }
    return data


class _Run:
    def __init__(
        self,
        *,
        provider: MockProvider | None = None,
        usage: MockUsage | None = None,
        progress: Progress | None = None,
        in_app: bool = True,
    ) -> None:
        self.provider = provider or _Provider(Path("/tmp/apps/tally"), _sample(92, 40))
        self.usage = usage or MockUsage()
        self.progress = progress or _Progress(_status())
        self.layouts = MockLayouts()
        if not in_app:
            self.layouts.found = None
        self.out = io.StringIO()
        self.err = io.StringIO()
        self.usage_apps: list[AppLayout] = []
        self.progress_apps: list[AppLayout] = []
        self.code = run_statusline(
            '{"payload": 1}',
            self.out,
            self.err,
            provider=self.provider,
            layouts=self.layouts,
            usage=self._usage,
            progress=self._progress,
        )

    def _usage(self, app: AppLayout) -> Usage:
        self.usage_apps.append(app)
        return self.usage

    def _progress(self, app: AppLayout) -> Progress:
        self.progress_apps.append(app)
        return self.progress

    @property
    def line(self) -> str:
        return self.out.getvalue()


def test_statusline_prints_every_part_in_order() -> None:
    run = _Run(progress=_Progress(_status(plan=("build", 2, 4))))

    assert (
        run.line == "bull · stage 5 · units 1/3 · build 2/4 · 5h 92% · wk 40% · ctx –\n"
    )
    assert run.code == 0


def test_statusline_shows_the_active_feature_between_stage_and_units() -> None:
    run = _Run(progress=_Progress(_status(feature="dark-mode")))

    assert (
        run.line
        == "bull · stage 5 · feature dark-mode · units 1/3 · 5h 92% · wk 40% · ctx –\n"
    )


def test_statusline_without_plan_or_feature_omits_them() -> None:
    run = _Run()

    assert "feature" not in run.line
    assert run.line.count("·") == 5


def test_statusline_shows_plan_progress_as_done_over_total_items() -> None:
    run = _Run(progress=_Progress(_status(plan=("verify", 0, 3))))

    assert " · verify 0/3 · " in run.line


def test_statusline_omits_weekly_when_the_sample_has_none() -> None:
    run = _Run(provider=_Provider(Path("/tmp/apps/tally"), _sample(10, None)))

    assert run.line == "bull · stage 5 · units 1/3 · 5h 10% · ctx –\n"


def test_statusline_omits_five_hour_when_the_sample_has_none() -> None:
    run = _Run(provider=_Provider(Path("/tmp/apps/tally"), _sample(None, 25)))

    assert run.line == "bull · stage 5 · units 1/3 · wk 25% · ctx –\n"


def test_statusline_without_any_usage_omits_both_usage_parts() -> None:
    usage = MockUsage()
    usage.sample = None

    run = _Run(provider=_Provider(Path("/tmp/apps/tally"), None), usage=usage)

    assert run.line == "bull · stage 5 · units 1/3 · ctx –\n"


def test_statusline_records_the_sample_from_the_input() -> None:
    usage = MockUsage()
    sample = _sample(92, 40)

    _Run(provider=_Provider(Path("/tmp/apps/tally"), sample), usage=usage)

    assert [c for c in usage.calls if c[0] == "record"] == [("record", (sample,))]


def test_statusline_records_nothing_when_the_input_has_no_sample() -> None:
    usage = MockUsage()
    usage.sample = None

    _Run(provider=_Provider(Path("/tmp/apps/tally"), None), usage=usage)

    assert [c for c in usage.calls if c[0] == "record"] == []


def test_statusline_falls_back_to_the_latest_recorded_sample() -> None:
    usage = MockUsage()
    usage.sample = _sample(61, 12)

    run = _Run(provider=_Provider(Path("/tmp/apps/tally"), None), usage=usage)

    assert run.line.endswith("5h 61% · wk 12% · ctx –\n")


def test_statusline_passes_the_raw_input_to_the_provider() -> None:
    run = _Run()

    assert ("parse_statusline", ('{"payload": 1}',)) in run.provider.calls


def test_statusline_finds_the_app_from_the_input_cwd() -> None:
    cwd = Path("/tmp/apps/tally/src")

    run = _Run(provider=_Provider(cwd, _sample(1, 2)))

    assert ("find", (cwd,)) in run.layouts.calls


def test_statusline_builds_its_collaborators_for_the_app_found() -> None:
    run = _Run()

    assert run.usage_apps and run.usage_apps[0] == sample_layout()
    assert run.progress_apps and run.progress_apps[0] == sample_layout()


def test_statusline_outside_an_app_prints_just_bull() -> None:
    usage = MockUsage()

    run = _Run(usage=usage, in_app=False)

    assert run.line == "bull\n"
    assert run.code == 0
    assert usage.calls == []
    assert run.usage_apps == []
    assert run.progress_apps == []


def test_statusline_unreadable_input_prints_a_plain_line_and_details_on_stderr() -> (
    None
):
    run = _Run(provider=_BrokenProvider())

    assert run.line == "bull\n"
    assert run.code == 0
    assert "not a statusline payload" in run.err.getvalue()


def test_statusline_unreadable_status_prints_a_plain_line_and_details_on_stderr() -> (
    None
):
    run = _Run(progress=_BrokenProgress())

    assert run.line == "bull\n"
    assert run.code == 0
    assert "status file unreadable" in run.err.getvalue()


def test_statusline_still_prints_one_line_when_recording_fails() -> None:
    run = _Run(usage=_BrokenUsage())

    assert run.code == 0
    assert run.line.startswith("bull")
    assert run.line.count("\n") == 1
    assert "disk full" in run.err.getvalue()


def test_statusline_writes_nothing_else_to_stderr_on_success() -> None:
    run = _Run()

    assert run.err.getvalue() == ""


def test_statusline_records_the_sample_even_when_the_status_cannot_be_read() -> None:
    usage = MockUsage()
    sample = _sample(92, 40)

    run = _Run(
        provider=_Provider(Path("/tmp/apps/tally"), sample),
        usage=usage,
        progress=_BrokenProgress(),
    )

    assert [c for c in usage.calls if c[0] == "record"] == [("record", (sample,))]
    assert run.line == "bull\n"
    assert run.code == 0
    assert "status file unreadable" in run.err.getvalue()


def test_statusline_records_the_sample_even_when_building_the_status_raises() -> None:
    usage = MockUsage()
    sample = _sample(10, 20)
    out, err = io.StringIO(), io.StringIO()

    def broken_progress(app: AppLayout) -> Progress:
        raise RuntimeError("cannot build progress")

    code = run_statusline(
        "{}",
        out,
        err,
        provider=_Provider(Path("/tmp/apps/tally"), sample),
        layouts=MockLayouts(),
        usage=lambda app: usage,
        progress=broken_progress,
    )

    assert code == 0
    assert out.getvalue() == "bull\n"
    assert [c for c in usage.calls if c[0] == "record"] == [("record", (sample,))]
    assert "cannot build progress" in err.getvalue()


class _UnbuildableUsage:
    """A `usage` factory that cannot build the store."""

    def __call__(self, app: AppLayout) -> Usage:
        raise OSError("usage dir unreadable")


def _run_with_usage_factory(
    factory: object, sample: UsageSample | None
) -> tuple[str, str, int]:
    out, err = io.StringIO(), io.StringIO()
    layouts = MockLayouts()
    code = run_statusline(
        "{}",
        out,
        err,
        provider=_Provider(Path("/tmp/apps/tally"), sample),
        layouts=layouts,
        usage=factory,  # type: ignore[arg-type]
        progress=lambda app: _Progress(_status()),
    )
    return out.getvalue(), err.getvalue(), code


def test_statusline_with_unbuildable_usage_store_reports_and_keeps_input_usage() -> (
    None
):
    line, err, code = _run_with_usage_factory(_UnbuildableUsage(), _sample(92, 40))

    assert code == 0
    assert line == "bull · stage 5 · units 1/3 · 5h 92% · wk 40% · ctx –\n"
    assert "usage dir unreadable" in err


def test_statusline_with_unbuildable_usage_store_and_no_input_usage_omits_usage() -> (
    None
):
    line, err, code = _run_with_usage_factory(_UnbuildableUsage(), None)

    assert code == 0
    assert line == "bull · stage 5 · units 1/3 · ctx –\n"
    assert "usage dir unreadable" in err


def test_statusline_when_latest_raises_reports_and_omits_usage_parts() -> None:
    class _LatestBroken(MockUsage):
        def latest(self) -> UsageSample | None:
            raise RuntimeError("corrupt usage file")

    run = _Run(provider=_Provider(Path("/tmp/apps/tally"), None), usage=_LatestBroken())

    assert run.line == "bull · stage 5 · units 1/3 · ctx –\n"
    assert "corrupt usage file" in run.err.getvalue()
    assert run.code == 0


def _ctx_part(line: str) -> str:
    return line.rstrip("\n").split(" · ")[-1]


def test_statusline_ends_with_the_context_part_after_weekly() -> None:
    run = _Run(provider=_Provider(Path("/tmp/apps/tally"), _sample(92, 40, 38)))

    assert run.line == "bull · stage 5 · units 1/3 · 5h 92% · wk 40% · ctx 38%\n"


def test_statusline_context_is_rounded_like_five_hour_and_weekly() -> None:
    both = _Run(provider=_Provider(Path("/tmp/apps/tally"), _sample(91.6, 39.6, 37.6)))
    low = _Run(provider=_Provider(Path("/tmp/apps/tally"), _sample(10.2, 20.2, 37.2)))

    assert both.line.endswith("5h 92% · wk 40% · ctx 38%\n")
    assert low.line.endswith("5h 10% · wk 20% · ctx 37%\n")


def test_statusline_shows_en_dash_context_when_the_input_has_no_sample() -> None:
    usage = MockUsage()
    usage.sample = None

    run = _Run(provider=_Provider(Path("/tmp/apps/tally"), None), usage=usage)

    assert _ctx_part(run.line) == "ctx –"


def test_statusline_shows_en_dash_context_when_the_sample_context_is_none() -> None:
    run = _Run(provider=_Provider(Path("/tmp/apps/tally"), _sample(92, 40, None)))

    assert _ctx_part(run.line) == "ctx –"


def test_statusline_context_never_falls_back_to_the_saved_sample() -> None:
    usage = MockUsage()
    usage.sample = _sample(61, 12, 77)

    run = _Run(provider=_Provider(Path("/tmp/apps/tally"), None), usage=usage)

    assert run.line.endswith("5h 61% · wk 12% · ctx –\n")
    assert "77" not in run.line


def test_statusline_context_ignores_the_saved_context_when_input_lacks_one() -> None:
    usage = MockUsage()
    usage.sample = _sample(61, 12, 77)

    run = _Run(
        provider=_Provider(Path("/tmp/apps/tally"), _sample(5, 6, None)), usage=usage
    )

    assert run.line.endswith("5h 5% · wk 6% · ctx –\n")


def test_statusline_context_only_input_still_shows_saved_five_hour_and_weekly() -> None:
    usage = MockUsage()
    usage.sample = _sample(61, 12, 77)

    run = _Run(
        provider=_Provider(Path("/tmp/apps/tally"), _sample(None, None, 38)),
        usage=usage,
    )

    assert run.line == "bull · stage 5 · units 1/3 · 5h 61% · wk 12% · ctx 38%\n"


def test_statusline_context_only_without_saved_usage_shows_context_alone() -> None:
    usage = MockUsage()
    usage.sample = None

    run = _Run(
        provider=_Provider(Path("/tmp/apps/tally"), _sample(None, None, 38)),
        usage=usage,
    )

    assert run.line == "bull · stage 5 · units 1/3 · ctx 38%\n"


def test_statusline_records_a_context_only_sample_merged_with_the_saved_one() -> None:
    usage = MockUsage()
    five_resets = datetime(2026, 11, 7, 15, 0, 0, tzinfo=UTC)
    week_resets = datetime(2026, 11, 12, 9, 0, 0, tzinfo=UTC)
    usage.sample = UsageSample(
        time=datetime(2026, 11, 7, 11, 0, 0, tzinfo=UTC),
        five_hour=61.0,
        weekly=12.0,
        five_hour_resets=five_resets,
        weekly_resets=week_resets,
        context=77.0,
    )

    _Run(
        provider=_Provider(Path("/tmp/apps/tally"), _sample(None, None, 38)),
        usage=usage,
    )

    recorded = [c[1][0] for c in usage.calls if c[0] == "record"]
    assert len(recorded) == 1
    sample = recorded[0]
    assert isinstance(sample, UsageSample)
    assert sample.five_hour == 61.0
    assert sample.weekly == 12.0
    assert sample.five_hour_resets == five_resets
    assert sample.weekly_resets == week_resets
    assert sample.context == 38


def test_statusline_records_a_context_only_sample_as_is_when_nothing_is_saved() -> None:
    usage = MockUsage()
    usage.sample = None
    sample = _sample(None, None, 38)

    _Run(provider=_Provider(Path("/tmp/apps/tally"), sample), usage=usage)

    assert [c for c in usage.calls if c[0] == "record"] == [("record", (sample,))]


def test_statusline_outside_an_app_has_no_context_part() -> None:
    run = _Run(
        provider=_Provider(Path("/tmp/apps/tally"), _sample(92, 40, 38)), in_app=False
    )

    assert run.line == "bull\n"
