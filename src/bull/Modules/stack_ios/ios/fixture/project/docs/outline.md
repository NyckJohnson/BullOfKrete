# Fixture outline

## Purpose
A counter that only goes up, for the `ios` stack's self-test. Its only job is to give the iOS gates
something real to pass and fail on, so `bull stack test ios` can check they give the right
verdicts.

## User journeys
1. **App opens** — a user opens the app; ends when its first screen is in the foreground.

## Screens and navigation
- **Content**: the template's first screen; serves journey 1.

## Constraints
- Stack `ios`: SwiftUI, Swift 6, Swift Testing, XCUITest.
- Minimum iOS 18.0.
- Offline; no accounts; no sync; no third-party services or libraries.

## Out of scope
- Everything else.

## Data models
None.

## Build order
1. Counter (depends on: none)

## Modules

### Counter
- Purpose: holds a count that only goes up.
- Depends on: none
- Files: Contracts/CounterStore.swift | Counter.swift
- Protocol (lives in `Contracts/`):
  ```swift
  protocol CounterStore: Sendable {
      func value() async -> Int
      func increment() async -> Int
  }
  ```
- Behavior spec:
  - A new counter's value is its start value (default 0).
  - increment returns the count plus one, which `value()` then returns.
- Reference tests: none
- Contract: see `docs/api/Counter.md` (generated; do not edit by hand)

## Decisions log
