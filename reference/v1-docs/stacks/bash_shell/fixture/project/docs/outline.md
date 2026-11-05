# Fixture outline

The bash_shell stack's self-test app (`ios-pipeline stack test bash_shell`). Keep it small: every
case copies it.

## Purpose
A counter the CLI can bump and print. It exists to check the bash_shell gates give the right
verdicts.

## Commands
1. **`fixture_cli count`** — adds one to the count kept in `.fixture_cli_count` in the current
   folder and prints the new count. Ends when the new count is written to stdout and the exit
   code is 0.

## Constraints
- Stack: bash_shell
- Minimum bash version: 3.2 (stock macOS /bin/bash)
- Offline: yes · Accounts: none · Sync: none · Third-party: none

## Out of scope
- Everything else.

## Data models
None.

## Build order
1. counter (depends on: none)

## Modules
### counter
- Purpose: a count kept in a state file, which only goes up.
- Depends on: none
- Files: counter.sh
- Contract (draft; lives in `Contracts/counter.sh`):
  ```bash
  # usage: counter::value <state file> -> stdout: the current count (0 if the file is missing)
  # usage: counter::increment <state file> -> stdout: the count plus one, also written to the file
  ```
- Behavior spec:
  - value: no state file → 0
  - increment: → the count plus one, which value then returns
- Contract: see `docs/api/counter.md` (generated; do not edit by hand)

## Decisions log
- 2026-11-04: fixture for the bash_shell stack self-test — keeps the gates honest — approved by
  the pipeline
