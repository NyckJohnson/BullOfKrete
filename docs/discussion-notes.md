# BullOfKrete: discussion notes (Stage 1)

Running notes from `/discuss`, started 2026-11-05. The settled decisions in
`docs/bull-v2-brief.md` are not repeated here; these notes record what `/discuss` adds or settles.

## Purpose

BullOfKrete (`bull`) is version 2 of the agent pipeline: a Claude Code plugin that builds software in
six staged steps (discuss → outline → setup → skeleton → prototype → modules → verify), plus a feature
cycle and adoption of existing apps, using specialized subagents, automated gates and human
checkpoints. It does everything v1 does, rewritten from first principles from a spec, with a
stack-neutral core: every platform (iOS, Python, shell, …) is a stack, and stacks themselves are built
through the same staged loop as apps.

**Target user:** a solo developer who directs Claude Code to build and extend their own apps on a Mac
(today: the pipeline's author, with three v1 apps to migrate), and who wants the pipeline to work the
same way whatever the app's language.

## Stack

_Pending._

## Open questions (from the brief)

1. One part or two (Python + shell)?
2. Existing stacks: port as they are, or rebuild through the stack workflow?
3. Which roadmap items are in v2.0?
4. Where bull installs, and how it updates.
5. Status file: JSON? One file or several?
6. Plugin name and slash-command namespace.
7. Stack builds: where, how status/checkpoints are tracked, tags and branches?

## Core journeys

_Draft list in the brief; to be written out as concrete scenarios._

## MVP features

## Later features

## Constraints

## Out of scope

- Reading v1 app files or formats automatically: only three v1 apps; migrated by hand.
- Changes to v1 beyond bug fixes: v1 is frozen from memo approval on.
- Adopting a multi-part app: not needed yet; adoption of one-part apps comes first.
- Splitting a part into its own app: not needed yet.
- Interfaces shared between apps: not needed yet.
