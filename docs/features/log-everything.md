# Log everything

## Idea

Extend the event log (`.bull/events.jsonl`) so it records everything the reports need: time paused
for usage, time waiting on the human, simulator-busy retries, and subagent end events. Reading the
log must survive a torn non-UTF-8 write by skipping the damaged line; today `EventLog.read` fails on
the whole file (found in events review, 2026-11-08).

## Discussion notes

## Agreed scope
