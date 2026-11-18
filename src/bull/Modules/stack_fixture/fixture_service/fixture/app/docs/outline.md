# Counter service outline

## Purpose
A tiny counter service for the `fixture_service` stack's self-test: one module holds a count; the
service answers `GET /health` while it runs.

## User journeys
1. **Check the service** — start the service, see it answer `GET /health`, stop it.

## Build order
1. counter (depends on: none)

## Modules

### counter
- Purpose: holds a count and changes it by one.
- Depends on: none
- Files: Contracts/counter.fx, counter.fx

## Decisions log
