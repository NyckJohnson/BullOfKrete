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

**Target user:** developers in general who use Claude Code and want it to build and extend apps
through a disciplined, test-first, staged process, whatever the app's language. bull is open-sourced
after v2.0 is accepted, so it must install and make sense for strangers, not only for its author (who
has three v1 apps to migrate).

## Stack

**One part, stack `python_cli`** (Python 3.11+, uv, pytest + coverage.py, ruff, mypy --strict).
Selected 2026-11-05.

Why:
- v1 mixes Python (~3,900 lines: all logic) and shell (~1,250 lines: the `bin/` launcher, `gates.sh`
  per core and stack, shell-sourced `KEY="value"` config, two small hooks). The split is incidental,
  not principled: gate scripts call back into Python for anything hard, and shell config can't be
  validated and executes when loaded.
- v2 draws the line cleanly: **everything bull itself runs is Python**. Hooks and the status line are
  `bull` subcommands. Config is TOML (read natively, validatable; feeds roadmap item 5). A stack
  declares its gate steps as commands that bull runs and reads results from, instead of shell
  functions that get sourced.
- One set of gates and one coverage report covers all of bull's code.
- The two-part journey (7) is tested with a fixture app, not by making bull itself two parts.
- Rejected: two parts (`python_cli` + `bash_shell`): two setups, and parts can't call each other yet.

## Platforms

- macOS and Linux for the core. A stack may need a specific platform (the iOS stack: macOS with Xcode).

## Open questions (from the brief)

1. ~~One part or two?~~ One part, all Python (see Stack).
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

- Windows support: hooks, paths and git behave differently; macOS and Linux first.

## Constraints

## Out of scope

- Reading v1 app files or formats automatically: only three v1 apps; migrated by hand.
- Changes to v1 beyond bug fixes: v1 is frozen from memo approval on.
- Adopting a multi-part app: not needed yet; adoption of one-part apps comes first.
- Splitting a part into its own app: not needed yet.
- Interfaces shared between apps: not needed yet.
