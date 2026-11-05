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

## Stacks in v2.0

A v2 stack is a self-contained folder: a TOML manifest declaring its build, test, lint, `--fast` and
`--failed` commands (bull runs them and reads their results), plus Python files for the contract
reader, coverage reader, `check` and optional `detect`. All its code is Python, like the core.

- **Shipped in v2.0, built now as ordinary bull modules** through the Stage 5 loop, with each stack's
  self-test (fixture + cases) part of its tests:
  - `python_cli`: needed so bull itself is the real app that makes it `verified`.
  - `ios`: needed to migrate the v1 apps.
- **`bash_shell` is rebuilt through v2's own stack workflow** once the core works: the real run of
  journey 6 and the workflow's first real test. If it isn't done when the rest of v2.0 is, it moves to
  later features rather than holding up v2.0.
- Rejected: building all three as modules (the stack workflow would only ever see a fixture); building
  only python_cli now (blocks migrating the iOS apps).

**Where stacks are built** (decided 2026-11-05):
- A stack is loadable from bull's built-in set or from a path or package (`bull stack install <path>`),
  so others can add stacks without forking bull.
- The stack workflow runs in the stack's **own git repo**, created by `bull init --stack`, with its own
  status file. Stages: discuss → scaffold → fixture and cases → gate code → review. Checkpoints:
  `design-approved` (DESIGN.md) and `rules-approved` (rules.md). Branches and tags like modules'
  (`stack/<step>`). Accepted stacks are `experimental` until one real app is accepted with them.
- A stack joins the built-in set by a PR to bull after passing `bull stack test`.
- Rejected: building stacks only inside the bull repo, tracked in bull's status file.

## Roadmap items (decided 2026-11-05)

In v2.0, as foundations that would be hard to add later:
- **Machine-readable output** (item 3's prerequisite): `--json` on status, backlog, usage and tags.
- **Event log** (item 4): append-only `.bull/events.jsonl` (git-ignored, machine-local), written by
  status changes, gate runs (per gate step) and subagent start/end hooks. No report yet.
- **Settings basics** (item 5): layered TOML (bull defaults → stack → user `~/.config/bull/` → app →
  part), validated on load and on write; `bull config show` (value and the layer it came from) and
  `bull config set`. Per-agent model is a setting. Expect settings to keep growing after v2.0; keep the
  schema easy to extend.
- **Provider seam** (item 6): everything Claude Code-specific (plugin files, hooks, launching,
  status-line usage, model names) in one `providers/claude_code` module behind an interface. Only
  Claude Code implemented.
- **iOS stack run hygiene** (from item 2, common-sense parts): one simulator chosen by UDID; no
  parallel testing, one destination; test diagnostics collected only on failure; UI test screenshots
  kept only on failure; build output and results under the app's `.bull/` instead of the global
  DerivedData, with a prune command.

## Open questions (from the brief)

1. ~~One part or two?~~ One part, all Python (see Stack).
2. ~~Existing stacks?~~ See Stacks in v2.0.
3. ~~Roadmap items?~~ See Roadmap items.
4. Where bull installs, and how it updates.
5. Status file: JSON? One file or several?
6. Plugin name and slash-command namespace.
7. ~~Stack builds?~~ See Stacks in v2.0.

## Core journeys

_Draft list in the brief; to be written out as concrete scenarios._

## MVP features

## Later features

- Windows support: hooks, paths and git behave differently; macOS and Linux first.
- GUI: a view across all apps, reading `--json` output (roadmap item 3); native macOS app or local web dashboard is open.
- Time report: `bull status time` totals by stage, module, unit, agent and gate step, from the event log (roadmap item 4).
- Settings page: GUI or screen for settings, beyond `bull config show/set` (roadmap item 5).
- Other AI providers: implementations behind the provider seam (roadmap item 6).
- Store readiness: optional stack release hook plus the iOS checks (privacy manifest, icons, permission strings, store-guidelines review) (roadmap item 7).
- Token report: tokens per stage, module, unit and agent (roadmap item 8).
- Automatic orchestrator restarts at module boundaries: bull drives `claude` from outside; needs its own design.
- Quieter iOS test runs (in limbo): simulator audio crackling seemed to resolve itself before the planned experiments ran. Remaining experiments: shut down simulators after every run (conflicts with reusing one booted simulator), report orphaned simulators at start, keep screenshots out of Photos and Spotlight (Spotlight Privacy as a manual setup step); open questions on clean-state launches and the speed cost of no parallel testing (roadmap item 2).

## Constraints

## Out of scope

- Reading v1 app files or formats automatically: only three v1 apps; migrated by hand.
- Changes to v1 beyond bug fixes: v1 is frozen from memo approval on.
- Adopting a multi-part app: not needed yet; adoption of one-part apps comes first.
- Splitting a part into its own app: not needed yet.
- Interfaces shared between apps: not needed yet.
