# Roadmap

Planned upgrades, in the intended order. Done: the feature backlog and cycle (`/feature`), the
stack seam (`stacks/`, `/setup`), adopting apps built outside the pipeline (`/adopt`,
`docs/adopt.md`; the first real adoption will shake it out), several stacks per app (`docs/stacks.md`
parts), the self-test (`stack test`, including an iOS fixture that passes all 12 cases on a Mac),
`/new-stack`/`stacks/_template/`, and the second stack it built, `python_cli` (below).

## 1. Adding new stacks
The seam exists, and so does the whole process for adding a stack — **done** (`docs/stacks.md` PRs
2-6, merged):
- **Parts** (2026-10-31 decision): an app is one or more parts, each with its own folder and
  stack, talking to each other only through interface files.
- **Self-test** (`ios-pipeline stack test <name>`): a stack's gates run against a small fixture
  with known cases (a failing test, a lint error, a contract change, an uncovered line, an
  exemption, a clean pass); a stack counts only when every case gives the right verdict, because
  gates that pass everything would make every module "done". Plus `--static`: the same check's
  shape (required files, manifest filled in, `cases.json`'s required ids, `gates.sh`'s required
  functions, `rules.md`'s required sections) with no toolchain needed.
- **`/new-stack`**: `ios-pipeline stack new <name>` scaffolds `stacks/<name>/stack.sh` and
  `DESIGN.md` only; every other file is written fresh for the new language from
  `stacks/README.md`'s interface spec (never copied from `stacks/ios/` or a template), so nothing
  assumes another stack's toolchain. `.claude/commands/new-stack.md` runs the six steps (discuss →
  scaffold → fixture/cases until `--static` passes → write the stack until `stack test` passes →
  rules → land it) and can resume from `DESIGN.md`'s checklist.
- **Journeys are capability-gated, not kind-gated**: whether `gates --app-ui-tests` and the
  adoption journey step run comes from `gates.sh` defining `stack_ui_tests`, not from
  `STACK_KIND`. A `tool` stack with an end-to-end layer gets journeys for free; `STACK_KIND` stays
  informational.
- **Maturity**: `experimental` until one real app has been built with it, then `verified`.
  `/discuss` offers verified stacks by default and experimental ones only on request.
- **`python_cli` stack** (PR 6, #35): the first real use of `/new-stack` and the first
  `STACK_KIND="tool"` with journeys — Python 3.11+, `uv`, `pytest`/`coverage.py`, `ruff`,
  `mypy --strict` (part of the build gate, not lint), contracts read with Python's own `ast`
  module rather than a line scanner, journeys as real subprocess runs of the installed console
  script. All 12 self-test cases pass against the real toolchain, entirely in this Linux
  container — no Mac handoff, unlike iOS. `experimental` until pipeline v2 (below) ships with it.
- The command is still named `ios-pipeline`; rename when a second stack lands.

**Next**: **build pipeline v2 with the pipeline**, on the new `python_cli` stack. Use the
pipeline's own process to produce a better-built version of itself.
  - **Builder and build stay apart**: the installed pipeline (v1) drives the work in a separate
    folder and repo, and you switch to v2 only once it is accepted. App sessions already never edit
    files outside their own folder.
  - **Open: rebuild or adopt.** Starting at `/discuss` gives the cleanest structure but no usable v2
    until the end. `/adopt` on the current repo improves it feature by feature and keeps a working
    pipeline throughout.
  - **Regression net**: the existing `tests/` suite, plus journeys such as "init an app", "run the
    gates", "build a feature" and "adopt an app", which v2 must keep passing.
  - Building v2 is the real app that moves the Python stack from `experimental` to `verified`.

## 2. Quieter iOS test runs (simulator audio)
Running the iOS gates causes audio problems on the Mac: crackling and long beeps that can linger
after a run. iOS stack only (`stacks/ios/gates.sh`); other stacks are unaffected. Suggestions from a
separate investigation, to test one at a time and keep what helps:
- **Today's behavior** (likely contributors): every `xcodebuild test` targets the simulator by
  *name*, not UDID; parallel testing and diagnostics collection are left at Xcode's defaults
  (parallel UI testing clones simulators, each with its own audio device); simulators are shut down
  only on the busy-simulator retry; result bundles go to `.pipeline/results/` but DerivedData grows
  in `~/Library/Developer/Xcode/DerivedData`.
- **Reuse one simulator**: boot one device once and pass `-destination 'id=<UDID>'`, instead of
  letting runs boot their own. **Done** (#27): `stack_preflight` picks the simulator by udid and
  waits for `simctl bootstatus`; a busy retry waits and checks again instead of shutting simulators
  down (the old retry's shutdown was itself making "Busy" likely, by forcing a fresh boot right
  before the next launch).
- **Turn off parallel testing**: `-parallel-testing-enabled NO` (or
  `-parallel-testing-worker-count 1`), and confirm only one `-destination` is ever passed. **Done**
  (#26): `ios_xcodebuild_test` always passes `-parallel-testing-enabled NO` and one `-destination`.
- **Less diagnostics work**: `-collect-test-diagnostics on-failure` (or `never`).
- **Fewer screenshots**: UI test screenshots only on failure (scheme or test plan setting, which
  belongs in `/setup` and `stack check`), and `XCTAttachment.lifetime = .deleteOnSuccess` in the
  ui-test-writer rules.
- **Shut down cleanly**: `xcrun simctl shutdown all` after every gate run, not only on a retry, so
  the simulator's audio device closes cleanly instead of being left to `coreaudiod`. Report
  orphans (`xcrun simctl list devices | grep -i booted`, stray `launchd_sim` / `CoreSimulator`
  processes) at the start of a run.
- **Keep output out of Photos and Spotlight**: make sure screenshots never land where Photos imports
  from; prune old DerivedData and `.xcresult` bundles (e.g. a per-app `-derivedDataPath` under
  `.pipeline/`, cleaned by a command); add the test-output and DerivedData folders to Spotlight
  Privacy (a manual `/setup` step).
- **Open questions**: which change actually fixes it (try in this order: one simulator, no parallel
  testing, shutdown after runs, then the rest); whether reusing one booted simulator conflicts with
  the clean-state launch option the journey tests rely on; and the speed cost of turning off
  parallel testing for large test suites.

## 3. GUI
A view across all apps. Comes after new stacks and pipeline v2 (item 1): the pipeline can then build
the GUI itself with a new stack (a macOS or web stack; the iOS stack builds iPhone apps only), and
the GUI reads v2's settled state instead of chasing a rewrite. Ideally v2 offers a machine-readable
surface (e.g. `ios-pipeline status --json`) so the GUI is a thin reader.
- Reads `status.json`, the backlog, git tags and usage; stack-neutral.
- Open questions: native macOS app or local web dashboard; monitor only, monitor plus launcher
  (new app, open, resume), or full control (drives the orchestrator; approvals in the GUI).

## 4. Time tracking
Show how long the pipeline takes and what the time goes to, so slow spots can be fixed instead of guessed.
Comes after the GUI (item 3), which should show this data too.
- **Record events** in an append-only `.pipeline/timing.jsonl` (machine-local, git-ignored like
  `usage.json`), each with a start, an end and what it was:
  - stages, `/setup`, checkpoints and features, from `ios-pipeline status` changes;
  - modules and work units, split by step (tests, code, gates, review) and by attempt, so retries show;
  - subagent runs by agent type, likely via Claude Code hooks (the PreToolUse hook on `Agent|Task`
    already exists; a matching end event is needed);
  - gate runs and each gate step inside them (build/test, lint, api, coverage, UI tests), from
    `workflow/gates.sh`, including simulator-busy retries;
  - time paused for usage limits, and time waiting on the human at checkpoints.
- **Report**: `ios-pipeline status time` prints totals by stage, module, unit, agent and gate step,
  plus the slowest items and where retries cost time. `--feature <slug>` scopes it to one feature.
  The summary and `/pipeline-status` show a one-line total.
- **Open questions**:
  - Wall-clock or active time? Overnight gaps and usage pauses shouldn't count as work; they
    should show as their own lines.
  - Should human wait time count in totals, or be reported separately?
  - Backfill existing apps from git commit and tag timestamps (coarse), or start fresh?
  - Track plan usage per step alongside time? The status line already records usage.
- **Option: existing tracing tools.** Part of this already exists outside the pipeline; decide
  whether to build on it, which may make the step easier or harder.
  - **LangSmith** has a Claude Code plugin (`langsmith-tracing`): it traces every turn, tool call and
    subagent run with timing, model and tokens, and adds agent-level debugging (what a subagent read,
    ran and decided). It doesn't know stages, modules, units or attempts, and it shows a gate run as
    one long shell command. It sends prompts, code and tool output to LangSmith's cloud, and needs a
    LangSmith account and key. It can be tried on one app with no pipeline changes.
  - **Claude Code's built-in OpenTelemetry** exports token and cost metrics, active time, and subagent
    attributes to any OTel backend, including self-hosted ones. Its beta traces pass a `TRACEPARENT` to
    shell commands, so `gates.sh` could emit its own spans (build, lint, coverage) nested in the agent
    trace, and `OTEL_RESOURCE_ATTRIBUTES` could tag sessions with the app and stack.
  - Trade-off: the pipeline's own events (stages, units, attempts, gate steps, pauses, waits on the
    human) are needed either way. Using a tracing tool for the agent side saves building that part,
    but adds a dependency and is tied to Claude Code, which matters for item 6 (AI-agnostic).
    Emitting the pipeline's events as OpenTelemetry would let LangSmith or any other backend show
    them.
  - Sources: [LangSmith: trace Claude Code](https://docs.langchain.com/langsmith/trace-claude-code),
    [Claude Code: monitoring usage](https://code.claude.com/docs/en/monitoring-usage).

## 5. Settings page
One place to see and change the pipeline's settings instead of editing `KEY="value"` files by hand.
- Covers the three layers that exist today: pipeline defaults (`workflow/defaults.sh`), stack defaults
  (`stacks/<stack>/defaults.sh`) and each app's overrides (`.pipeline/config.sh`), showing which layer
  each value comes from.
- Settings to expose: usage pause thresholds, `MAX_ATTEMPTS`, `MAX_FILES_PER_UNIT`, `REVIEW_MODE`,
  coverage exclusions, the model each agent uses (today the `model:` line in `agents/*.md`), the
  simulator, and, once item 6 exists, the AI provider.
- Validates values and writes them in the shell-compatible form the parser expects, so a bad edit
  can't silently change a setting.
- Open questions: a page in the GUI (item 3) or its own screen; whether per-agent model choice should
  move from the agent files into settings so the pipeline update doesn't overwrite it.

## 6. AI-agnostic pipeline
Let the pipeline run on other AI tools, with Claude Code on a Claude Pro plan as the default.
Which other providers to support is TBD.
- Follows the stack seam's pattern: a **provider** folder (e.g. `providers/claude-code/`) holds
  everything tied to one tool, and a `PROVIDER` setting chooses it (default `claude-code`).
- What is Claude Code-specific today:
  - launching: `ios-pipeline open` runs `claude --plugin-dir`;
  - the plugin format: commands, agents (Markdown with `model:`, `tools:` and `disallowedTools:`
    frontmatter) and `hooks/hooks.json`;
  - the hooks the safeguards rely on: SessionStart (state on start), and PreToolUse for the usage
    guard, merge guard and test protection;
  - instructions: the app's `CLAUDE.md` importing `orchestrator.md`, and `.claude/settings.json`
    (permissions, status line, foreground subagents);
  - usage pausing: the status line reads Claude Pro/Max rate limits (`5h` / `7d`);
  - model names (`sonnet`, `inherit`) in agent files.
- The process, memo, status, gates, stacks and feature cycle are already tool-neutral.
- Open questions:
  - Which providers first, and whether each supports subagents. Without them, the orchestrator runs
    each agent role itself, one at a time.
  - How to keep the safeguards on a tool without hooks; the git-side checks (merge guard as a git
    hook, test protection in gates) may need to replace them.
  - How usage pausing works on plans or APIs that report usage differently, or not at all.
  - Mixed setups, e.g. a different model for reviewers than for builders.

## 7. Store readiness after verify
Check that an accepted app is ready to submit to its store, not just working. This is
**stack-specific**: the generic pipeline gets an optional "release readiness" step, and each stack
supplies its own checks or none (a backend or a Python tool has no store).
- **Generic part**: an optional stack hook (e.g. `stacks/<stack>/release.md` plus a `release_check.py`
  that returns `[(ok, item, fix)]`, like `check.py`). It runs after `/verify` acceptance and again at the
  end of each feature, since a feature can add a permission or a new data use. Stacks without the hook
  skip the step.
- **iOS checks**, automated where a script can tell:
  - **Privacy manifest**: `PrivacyInfo.xcprivacy` exists in the app target, and declares a reason for
    each required-reason API the code uses (found by scanning the source, e.g. `UserDefaults`, file
    timestamps, system boot time, disk space), plus the data types collected and tracking domains.
  - **Icons**: the `AppIcon` asset has its 1024×1024 image (and dark and tinted variants if the
    project uses them), with no placeholder.
  - **Permission strings**: every API that needs one (camera, microphone, photos, location, contacts,
    calendars, Bluetooth, motion, tracking…) has its `NS…UsageDescription` key, and the text is
    specific, not empty or "TODO".
- **iOS review pass**: a reviewer run with a "store guidelines" category for issues a script can't
  see, such as:
  - account creation without account deletion;
  - third-party sign-in without Sign in with Apple, where the guidelines require it;
  - digital goods sold outside in-app purchase;
  - placeholder or test content, dead buttons, or links that go nowhere;
  - a feature that needs a permission without explaining why.
- **Manual checklist** for the human, which the pipeline can't verify: App Store Connect privacy
  labels matching the manifest, age rating, screenshots, the support URL and privacy policy URL, and
  the export compliance answer.
- **Open questions**:
  - Blocking (acceptance waits for a clean check) or advisory (a report with fixes routed like
    `/verify` findings)?
  - A separate command (e.g. `/store-ready`) or a final part of `/verify`?
  - Apple's guidelines and requirements (such as the minimum Xcode or SDK version) change. Keep the
    iOS checklist dated, and recheck it against Apple's current guidelines whenever the step is worked on.
