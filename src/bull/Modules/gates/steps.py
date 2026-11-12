"""A gate step: the stack's argv with placeholders filled, run from the part folder."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from bull.Modules.events.Contracts import EventKind, EventLog
from bull.Modules.foundation.Contracts import AppLayout, Files, Runner
from bull.Modules.gates.Contracts import Gate, StepResult, Verdict
from bull.Modules.parts.Contracts import Part
from bull.Modules.settings.Contracts import Settings
from bull.Modules.stacks.Contracts import Stack

PLACEHOLDERS: tuple[str, ...] = (
    "python",
    "stack_dir",
    "app_root",
    "part_root",
    "results",
    "module",
    "module_src",
    "module_tests",
    "port",
    "failed_ids",
)

_FAILED_IDS = "{failed_ids}"
_PLACEHOLDER_RE = re.compile(
    "\\{(" + "|".join(re.escape(name) for name in PLACEHOLDERS) + ")\\}"
)
_FAIL_PREFIX = "bull-fail:"
_TAIL_LINES = 40


def fill(
    argv: Sequence[str],
    values: Mapping[str, str],
    failed_ids: Sequence[str] = (),
) -> list[str]:
    """Fill a manifest argv's placeholders.

    An argument that is exactly `{failed_ids}` becomes one argument per id (none: removed).
    Every other known `{name}` inside an argument is replaced from `values` (missing: "");
    any other text, braces included, is kept as is.
    """
    out: list[str] = []
    for arg in argv:
        if arg == _FAILED_IDS:
            out.extend(failed_ids)
            continue
        out.append(_PLACEHOLDER_RE.sub(lambda m: values.get(m.group(1), ""), arg))
    return out


def step_env(
    base: Mapping[str, str],
    app: AppLayout,
    part: Part,
    stack: Stack,
    results: Path,
    settings_json: str,
    adopt: bool,
    scope_module: str | None,
) -> dict[str, str]:
    """`base` plus the `BULL_*` variables every gate step gets (paths absolute)."""
    env = dict(base)
    env.update(
        {
            "BULL_PART": part.name,
            "BULL_PART_ROOT": str(part.root.absolute()),
            "BULL_APP_ROOT": str(app.root.absolute()),
            "BULL_RESULTS": str(results.absolute()),
            "BULL_STACK_DIR": str(stack.home.absolute()),
            "BULL_ADOPT_MODE": "1" if adopt else "0",
            "BULL_SCOPE_MODULE": scope_module or "",
            "BULL_SETTINGS": settings_json,
        }
    )
    return env


def settings_json(settings: Settings, part: str | None) -> str:
    """The part's resolved settings as JSON: keys sorted, tuples as lists."""
    data: dict[str, object] = {}
    for row in settings.show(part):
        value = row.value
        data[row.key] = list(value) if isinstance(value, tuple) else value
    return json.dumps(data, sort_keys=True)


@dataclass(frozen=True)
class StepOutput:
    """What running one gate step produced."""

    exit: int
    labels: tuple[str, ...]
    tail: str
    seconds: float


class LiveSteps:
    """Runs gate steps and reports their results as `gate_step` events."""

    def __init__(self, runner: Runner, events: EventLog, files: Files) -> None:
        self._runner = runner
        self._events = events
        self._files = files

    def execute(
        self,
        step: str,
        argv: Sequence[str],
        cwd: Path,
        env: Mapping[str, str],
        results: Path,
    ) -> StepOutput:
        """Run `argv` in `cwd`, keep its output in `results/<step>.log`, collect labels."""
        run = self._runner.run(argv, cwd, env, None)
        log = _join_output(run.stdout, run.stderr)
        self._files.write_atomic(results / f"{step}.log", log)
        labels = tuple(
            line[len(_FAIL_PREFIX) :].strip()
            for line in run.stdout.splitlines()
            if line.startswith(_FAIL_PREFIX)
        )
        if run.returncode != 0 and not labels:
            labels = (f"{step} failed (exit {run.returncode})",)
        tail = "\n".join(log.splitlines()[-_TAIL_LINES:])
        return StepOutput(
            exit=run.returncode, labels=labels, tail=tail, seconds=run.seconds
        )

    def result(
        self,
        gate: Gate,
        part: str,
        module: str | None,
        verdict: Verdict,
        labels: Sequence[str],
        seconds: float,
        tail: str,
    ) -> StepResult:
        """Build a step's result and append its `gate_step` event."""
        self._events.append(
            EventKind.GATE_STEP,
            gate=gate.value,
            part=part,
            module=module,
            verdict=verdict.value,
            seconds=seconds,
        )
        return StepResult(
            gate=gate,
            part=part,
            module=module,
            verdict=verdict,
            labels=tuple(labels),
            seconds=seconds,
            output_tail=tail,
        )


def _join_output(stdout: str, stderr: str) -> str:
    """stdout then stderr, with a line break between them when stdout lacks one."""
    if stdout and stderr and not stdout.endswith("\n"):
        return f"{stdout}\n{stderr}"
    return stdout + stderr
