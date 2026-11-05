# Fixture outline

The iOS stack's self-test app (`ios-pipeline stack test ios`). Keep it small: every case copies it.

## Purpose
A counter that only goes up. It exists to check the iOS gates give the right verdicts.

## User journeys
1. **App opens** — a user opens the app. Ends when its first screen is in the foreground.

## Screens and navigation
- **Content**: the template's first screen. Serves journey 1.

## Constraints
- Stack: ios
- Minimum platform version: iOS 18
- Offline: yes · Accounts: none · Sync: none · Third-party: none

## Out of scope
- Everything else.

## Data models
None.

## Build order
1. Counter (depends on: none)

## Modules
### Counter
- Purpose: a count that starts at a value and goes up by one.
- Depends on: none
- Files: CounterStore.swift, Counter.swift
- Protocol (draft; lives in `Contracts/`):
  ```swift
  protocol CounterStore: Sendable {
      func value() async -> Int
      func increment() async -> Int
  }
  ```
- Behavior spec:
  - value: a new counter → its start value (default 0)
  - increment: → the count plus one, which value() then returns
- Contract: see `docs/api/Counter.md` (generated; do not edit by hand)

## Decisions log
- 2026-10-31: fixture for the stack self-test — keeps the iOS gates honest — approved by the pipeline
