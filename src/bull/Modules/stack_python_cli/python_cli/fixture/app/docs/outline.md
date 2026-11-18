# Counter CLI outline

## Purpose
A tiny command-line counter for the `python_cli` stack's self-test: `fixture_cli count` bumps a
count kept in the working folder and prints it. Its only job is to give the python_cli gates
something real to pass and fail on.

## User journeys
1. **Count** — run `fixture_cli count` twice in an empty folder: it prints `1`, then `2`, and exits 0 both times.

## Commands
- `fixture_cli count`: adds one to the count kept in the working folder and prints the new count (module `counter`).

## Constraints
- Stack `python_cli`: Python 3.11+, uv.
- Offline; no accounts; no third-party services or libraries.

## Build order
1. counter (depends on: none)

## Modules

### counter
- Purpose: holds a count in a file in the working folder and bumps it by one.
- Depends on: none
- Files: Contracts/__init__.py | counter.py
- Protocol (lives in `Contracts/`):
  ```python
  class CounterStore(Protocol):
      def value(self) -> int: ...
      def increment(self) -> int: ...


  @dataclass(frozen=True)
  class Count:
      value: int
  ```
- Behavior spec:
  - A new counter's value is its start value (default 0).
  - increment returns the count plus one, which value then returns, also from a new counter on the same folder.
- Reference tests: none

## Interfaces

### Count
- File: interfaces/count.json (json-schema)
- Provider: app / counter

## Decisions log
