# Fixture outline

The python_cli stack's self-test app (`ios-pipeline stack test python_cli`). Keep it small: every
case copies it.

## Purpose
A counter the CLI can bump and print. It exists to check the python_cli gates give the right
verdicts.

## Commands
1. **`fixture_cli count`** — prints the current count, then increments it. Ends when the new
   count is written to stdout and the exit code is 0.

## Constraints
- Stack: python_cli
- Minimum Python version: 3.11
- Offline: yes · Accounts: none · Sync: none · Third-party: none

## Out of scope
- Everything else.

## Data models
None.

## Build order
1. counter (depends on: none)

## Modules
### counter
- Purpose: a count that starts at a value and goes up by one.
- Depends on: none
- Files: counter.py
- Protocol (draft; lives in `Contracts/`):
  ```python
  class CounterStore(Protocol):
      def value(self) -> int: ...
      def increment(self) -> int: ...
  ```
- Behavior spec:
  - value: a new counter → its start value (default 0)
  - increment: → the count plus one, which value() then returns
- Contract: see `docs/api/counter.md` (generated; do not edit by hand)

## Decisions log
- 2026-11-03: fixture for the python_cli stack self-test — keeps the gates honest — approved by
  the pipeline
