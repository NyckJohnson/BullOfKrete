# Counter outline

## Purpose
A tiny counter for the `fixture` stack's self-test: one module counts, another shows the count.

## User journeys
1. **Count up and down** — start at zero, count up, count down.

## Build order
1. counter (depends on: none)
2. display (depends on: none)

## Modules

### counter
- Purpose: holds a count and changes it by one.
- Depends on: none
- Files: Contracts/counter.fx, counter.fx

### display
- Purpose: shows the counter's value.
- Depends on: none
- Files: Contracts/display.fx, display.fx

## Interfaces

### Count
- File: interfaces/count.json (json-schema)
- Provider: app / counter
- Consumers: app / display

## Decisions log
