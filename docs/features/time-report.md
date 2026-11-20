# Time report

## Idea

`bull status time` totals by stage, module, unit (by step and attempt), agent and gate step, plus
the slowest items and where retries cost time; `--feature <slug>` scopes it; `/bull:status` shows a
one-line total. From the event log. Open (ROADMAP item 4): wall-clock or active time (overnight gaps
and pauses as their own lines); human wait time in totals or separate; backfill from git timestamps
or start fresh; usage per step alongside time; build on LangSmith or Claude Code's OpenTelemetry for
the agent side, or emit bull's events as OpenTelemetry (trade-off: dependency and lock-in to one
coding agent vs. building it).

## Discussion notes

## Agreed scope
