# AI-Assisted iOS App Development Workflow

> **Version note (Oct 2026):** this guide is the original design. The template (README.md and CLAUDE.md in this project) has since changed. Where they disagree, the template wins:
> - Modules are **folders inside the app target** (`Modules/<Module>/` with `Contracts/`, `Mocks/`, `Views/`), not local Swift Packages. Tests live in one unit test target, a folder per module.
> - The Stage 5 loop works on **work units** (a module, or a group of files when a module is large; `MAX_FILES_PER_UNIT`), not single files. Retries cap at 3 per unit.
> - The contract snapshot covers only `Contracts/` (protocols plus shared models), not every `public` declaration.
> - A progress gauge (`units done/total`, plus a per-step plan) shows in the status line.
> - Create the Xcode project without its own git repo; gates fail if a nested `.git` exists under `App/`.
> - **Features after acceptance** (`/feature`): a backlog of ideas, added one at a time or from a file, each built through a scoped run of stages 1–6 on `feature/<slug>/main` and merged on acceptance. The memo marks changes with `Changes (<slug>):` / `Contract changes (<slug>):` lines; listed contract changes are approved with the memo. Ideas deferred in Stage 1 live in the memo's `Later features` section; at first acceptance the human tests on a device, feedback is split into fixes and features, and the deferred ideas are offered for the backlog.
> - **Stacks**: everything platform-specific (gates, contract scanner, coverage, setup, agent rules) lives in `stacks/<stack>/`; the stack is chosen in Stage 1. A `/setup` step between Stages 2 and 3 walks the human through the stack's manual project steps (the Xcode project, for iOS) and checks them. iOS is the only stack so far; see `ROADMAP.md`.
> - **Adopting existing apps** (`/adopt`): an app built outside the pipeline runs the same stages on `adopt/main` (detect and discuss, survey and memo, setup, baseline journey tests, scaffold, module-by-module adoption, verify with the Swift 6 switch) until no legacy code is left. See `docs/adopt.md`.
> - The pipeline is a **Claude Code plugin installed once**; each app is its own folder and repo (`ios-pipeline init`, `ios-pipeline open`). The workflow no longer lives in the app repo, so restoring an app's tag restores its memo, status and code but not the pipeline version (see "Rollback and retry").

## Overview

An app is built in six sequential stages by one agent at a time. Modules are built from the most foundational to the most dependent, and the human approves the work at four fixed checkpoints.

Stages run top to bottom. A failure in Stage 6 sends work back to the owning module in Stage 5.

**Core principles**

- **Sequential.** Only one agent works at a time. This avoids merge conflicts, keeps token use predictable, and lets decisions be made in order.
- **Foundational first.** Modules are built in dependency order, so each one is built against real code rather than stubs.
- **Strong encapsulation.** Each module is reached by others only through its protocols.
- **Contracts before code.** Models and protocols exist and compile before any implementation starts.
- **Tests define done.** A unit or module is done when it passes its automated gates, not when an agent says it is.
- **One source of truth.** The outline memo is the shared spec. Its public API section is generated from code, not written in prose.
- **Built for change.** Interfaces are complete and coherent. Anticipated operations are listed in the memo, and only cheap, obvious complements are implemented ahead of need.

**Human checkpoints**

1. Approve the outline memo (end of Stage 2).
2. Approve the UI prototype flow (end of Stage 4).
3. Approve any change to an already-written protocol (any time).
4. Accept the finished app (end of Stage 6).

## Stage 1: Discuss app considerations

The human and Claude settle what the app is for and what it must do, in one conversation. Nothing is built yet.

The discussion should produce:

- A one-paragraph purpose statement and the target user.
- The core user journeys, as many as the app needs, each written as a concrete scenario ("Maya opens the app, adds a habit, sets a 7 pm reminder").
- A feature list split into MVP and later.
- Constraints: minimum iOS version, offline use, accounts or sign-in, iCloud sync, third-party services.
- An explicit out-of-scope list.

These feed directly into the outline memo.

## Stage 2: Outline the app

Claude turns the discussion into the outline memo (template below), and the human approves it. This is **checkpoint 1**.

The outline is ready to build from when every box is ticked:

- [ ] Purpose and all core user journeys are written down.
- [ ] The screen list and navigation flow are known (names and order, not visual detail).
- [ ] Every module has a purpose, a dependency list, and a draft public protocol.
- [ ] Data models are defined, with fields and types.
- [ ] The module build order is set, from no dependencies to most dependencies.
- [ ] Persistence, networking, and third-party choices are made.
- [ ] Out-of-scope items are listed.

**Final test:** could an agent build any one module from the memo alone, without asking a question? If not, the outline isn't ready.

## Stage 3: Set up the skeleton

One agent builds a project that compiles end to end but does nothing yet. Every later agent then builds against fixed contracts.

1. Create the app project by hand in Xcode, with synchronized folders so new files join their target without editing the `.pbxproj` file.
2. Create each module (originally a local Swift Package; now a folder in the app target), with a test target and Swift 6 language mode enabled.
3. Write the data models.
4. Write each module's protocol, as drafted in the memo.
5. Add a stub implementation and a mock implementation for every protocol. The stubs fail loudly; the mocks return sample data.
6. Add SwiftLint and swift-format configs, plus one `gates.sh` script that runs every automated gate.
7. Commit to `main` and tag it `skeleton`.

**Gate:** the project builds with no warnings, and `gates.sh` passes on the empty test suites.

## Stage 4: Build the UI prototype

The real SwiftUI screens are built against the mock implementations, so the human can try the app before any real logic exists. Problems are easier to see in hand than to describe in chat, and fixing them now is cheap.

1. Write a light UI description: screen list, navigation flow, and which journey each screen serves. Visual mockups are optional at this point.
2. One agent builds each screen and its view model against the mocks, with SwiftUI previews.
3. The human runs it in the simulator or on a phone and walks through each user journey.
4. Revise until the flow feels right. Changes to screens or flow update the memo; changes to an existing protocol need approval.
5. Merge to `main`.

This is **checkpoint 2**. Because the views depend only on protocols, they mostly survive Stage 5 unchanged: real implementations replace the mocks.

## Stage 5: Build each module

Modules are built one at a time in the memo's build order, and files within a module in their own dependency order. A module merges only when every file and the module as a whole pass the gates.

**For each module:**

1. Create branch `module/<name>` from `main`.
2. Read the memo: this module's spec, plus the public API of the modules it depends on. Nothing else.
3. For each file in the module:
   1. A **test agent** writes tests from the memo's spec, covering all intended functionality. It does not see any implementation.
   2. A **code agent** writes the file to make the tests pass, without editing the tests.
   3. Run `gates.sh`. On failure, return to step 2 with the output.
   4. A **review agent** runs the targeted LLM verification. On findings, return to step 2.
4. Run the module-level gates: all tests, coverage, and the module's public API checked against its memo protocol.
5. Merge into `main`, then run `gates.sh` on `main`.
6. Regenerate the memo's public API section for this module from its `public` declarations.
7. Set the module's status to `done` in the status file.

**Automated gates** (`gates.sh`)

| Gate | Passes when |
| --- | --- |
| Build | Builds in Swift 6 language mode (strict concurrency checking) with zero errors and zero warnings |
| Tests | All tests pass |
| Lint and format | SwiftLint and swift-format report nothing |
| Coverage | Every uncovered line is tested, marked exempt, or resolved with the human (see Coverage triage) |
| Encapsulation | Only memo-listed symbols are `public` |

**Coverage triage**

After a module's tests pass, every line they don't run is accounted for, not just enough to reach a percentage. SwiftUI views are excluded; the prototype review and XCUITests cover them.

1. `gates.sh` lists every uncovered line, skipping lines already marked exempt.
2. A **coverage subagent** examines each uncovered block against the spec and sorts it:

| Finding | Action |
| --- | --- |
| In the spec, but the tests missed it | The test subagent writes the test from the spec, not from the code |
| Infeasible to test (e.g. a system callback, an unrecoverable `fatalError` path, an OS failure that can't be simulated) | Mark it in the code with `// coverage-exempt: <reason>`; the review pass checks the reason holds |
| Not in the spec | The orchestrator asks the human: remove the code, or update the spec and have the test subagent write the test |

3. Rerun the gates. The module passes when nothing uncovered is left unexplained.

The exemption lives next to the code it covers, so it moves with the code in a refactor and is visible to anyone reading it. Future scans skip marked lines; if the code changes, the review pass checks the exemption still applies.

**Targeted LLM verification** checks what the gates can't. Each category runs as its own focused review pass, because one pass covering everything tends to be shallow.

| Category | The reviewer checks |
| --- | --- |
| Correctness and edge cases | Logic matches the spec; empty, nil, zero, maximum and boundary inputs; dates and time zones; invalid state transitions |
| Error handling | Errors are thrown or surfaced, never swallowed; no force unwraps or `try!`; failures leave state consistent; messages are useful |
| Security | Secrets in the Keychain, never in logs or UserDefaults; input validated; HTTPS only; file protection set; only needed permissions requested |
| Concurrency and resources | UI work on the main actor; no data races or unchecked `Sendable`; tasks cancel cleanly; no retain cycles in closures; files, observers and timers are released |
| Spec and API design | Matches the memo protocol; follows the Swift API Design Guidelines; no internal detail leaks through the public API |

**Retries:** each file gets 3 attempts across steps 3.2–3.4. After that, the pipeline stops and asks the human.

## Stage 6: Test and verify the full app

The app is verified against the user journeys from Stage 1, then handed to the human. This is **checkpoint 4**.

1. Confirm the app uses the real implementations everywhere, with mocks left only in tests and previews.
2. Write one XCUITest per user journey and run them in the simulator.
3. Run a whole-app review: consistency across modules, accessibility labels, Dynamic Type, dark mode, and launch time.
4. Failures go back to the module that owns them, which reruns its Stage 5 loop. A failure caused by the design goes back to the memo, with human approval.
5. The human tests on a real device and accepts the app.

Shipping (signing, App Store Connect, TestFlight) is a separate step after this. Fastlane can script most of it.

## Rules

These apply at every stage.

- **Protocol changes need approval.** An agent that needs to change an already-written protocol stops and asks the human. It explains the change, why it's needed, and which modules it affects. Approved changes update the memo first, then the code.
- **Agents don't edit the memo freely.** Agents propose memo changes; the orchestrator or the human applies them. Public API sections are only ever regenerated from code.
- **Failures escalate after 3 attempts.** Because work is sequential, the pipeline stops and waits for the human.
- **Progress lives in files.** A status file records each module's state (`pending`, `in progress`, `done`, `blocked`), so a crashed or paused run can resume.
- **Branch per module.** Every module merges as a unit, so any module can be reverted on its own.
- **No speculative code.** Anticipated operations are listed in the memo. Only cheap, obvious complements are built ahead of need.

## Agents and handoffs

One orchestrator runs the whole pipeline and hands each unit of work to a fresh subagent. Only the orchestrator talks to the human, edits the memo, and merges to `main`.

| Stage | Who does the work | Subagent receives | Subagent returns |
| --- | --- | --- | --- |
| 1. Discuss | Orchestrator, with the human | — | — |
| 2. Outline | Orchestrator | — | — |
| 3. Skeleton | Skeleton subagent | Full memo | Green build, list of files created |
| 4. UI prototype | One screen subagent at a time | Screens section, protocols, mocks | Screen, view model, previews |
| 5. Each file | Test subagent | That file's spec only | Tests |
| 5. Each file | Code subagent | Spec, tests, public API of dependencies | Implementation |
| 5. Each file | Review subagent | Spec, tests, diff | Findings, or a pass |
| 5. Merge | Orchestrator | — | — |
| 6. Full app | UI-test subagent, then review subagent | User journeys, full app | XCUITests; whole-app findings |

**Handoff rules**

- **Every subagent starts cold.** It gets a written brief: the task, the exact files and memo sections to read, the acceptance criteria, and what to return. It knows nothing else.
- **Every subagent returns a short report:** done or blocked, files changed, and any questions.
- **Questions go up, not out.** A subagent that needs a decision, such as a protocol change, returns blocked with its question. The orchestrator asks the human.
- **The orchestrator runs the gates and merges.** Subagents never merge or edit the memo.
- **The orchestrator hands off too.** When its context gets long, at the latest at the end of each stage, a new orchestrator session starts from the memo, the status file, and the git log. Nothing important lives only in the conversation.

## Rollback and retry

Any checkpoint can be restored and the run tried again, with a changed workflow if needed. This works because the code, the memo, the status file, and the workflow itself all live in the same repo.

**What's in the repo**

- App code and tests.
- `docs/outline.md` (the memo) and the status file.
- `workflow/`: the subagent briefs, `gates.sh`, lint configs, and the orchestrator's instructions (`CLAUDE.md`).

Restoring a point restores all of these together, so the code never disagrees with the memo or the workflow that built it.

**Tags at each checkpoint**

| Tag | Set when |
| --- | --- |
| `outline-approved` | Checkpoint 1 passes |
| `skeleton` | Stage 3 gate passes |
| `ui-approved` | Checkpoint 2 passes |
| `module/<name>` | That module merges to `main` |
| `app-accepted` | Checkpoint 4 passes |

**To retry from a point**

1. Branch from the tag instead of resetting `main`, so the first attempt stays for comparison: `git switch -c attempt-2 ui-approved`.
2. Change what needs changing: the memo, a subagent brief, a gate threshold.
3. Commit that change with a message saying why, then restart the orchestrator from the status file.
4. Compare the attempts afterward with `git diff main attempt-2`.
5. Keep the better attempt by merging it, and delete the other branch.

Git doesn't cover things outside the repo, such as Xcode's DerivedData and simulator app data. Clear both before a retry.

## Running on Claude Pro

The pipeline runs in Claude Code on a Pro subscription and pauses when the usage limit is reached. Nothing is billed per token.

**How the limits work**

- There are two limits: a rolling 5-hour session window and a weekly cap. The weekly cap is the real ceiling, so expect one app to take several days.
- Claude Code, claude.ai chat, and the desktop app share one usage pool. Keep chat use light during a run.
- At the limit, Claude Code stops until the window resets. Leave extra usage (pay-as-you-go credits) off, so the pipeline pauses rather than charges.
- If an `ANTHROPIC_API_KEY` environment variable is set, Claude Code bills that API key instead of the plan. Make sure it is unset.
- `/usage` in Claude Code shows session and weekly usage.

**Pause-safe design**

- Commit after every completed step (tests written, gates passed, review passed), so a pause loses at most one step.
- On resume, the orchestrator reads the status file, discards uncommitted changes in the current file, and restarts that step.
- When usage is near the limit, finish the current step and stop at the step boundary rather than starting a new one.

**Early pause**

The pipeline pauses itself before hitting the hard limit, so it always stops at a clean step boundary.

1. **Capture usage.** Claude Code pipes the plan's usage to the status line script: `rate_limits.five_hour` and `rate_limits.seven_day`, each with `used_percentage` and `resets_at`. The script writes these to `.pipeline/usage.json`.
2. **Check before each step.** The orchestrator reads the file before starting any step. Above the threshold, it commits, sets the status file to `paused` with the reset time, and stops.
3. **Enforce with a hook.** A hook that runs before each subagent launch reads the same file and blocks the launch when usage is over the threshold, so the pause doesn't depend on the orchestrator remembering.

| Window | Pause at |
| --- | --- |
| 5-hour | 85% used |
| Weekly | 95% used |

- The file only updates while Claude Code is responding, so it lags slightly. The margin leaves room for the current step to finish.
- `rate_limits` has been missing in some Claude Code versions. Confirm it appears before relying on it; the hard limit remains the backstop.

**Stretching the budget**

- Start with one combined review pass per file instead of one per category. Split them later where quality needs it.
- Use a lighter, cheaper model for subagents where quality allows.
- Keep subagent briefs tight: each reads only its listed files and memo sections.

## Outline memo template

The memo lives in the repo as `docs/outline.md` and is read by every agent. Copy this structure (the current template in `workflow/templates/outline.md` adds `Owner`/`Shared` lines on data models and allows `|` to split a module's files into work units):

```markdown
# <App name> outline

## Purpose
One paragraph: what the app does and for whom.

## User journeys
1. <Name>: <concrete scenario>

## Screens and navigation
- <Screen>: <purpose>, reached from <screen>

## Constraints
Min iOS: … · Offline: … · Accounts: … · Sync: … · Third-party: …

## Out of scope
- …

## Data models
### <Model>
| Field | Type | Notes |

## Build order
1. <Module> (depends on: none)
2. <Module> (depends on: …)

## Modules
### <Module>
- Purpose: …
- Depends on: …
- Files: <File>.swift (purpose), …
- Protocol (draft):
  protocol <Name> { … }
- Anticipated operations (not yet built): …
- Public API (generated from code; do not edit by hand):
  …

## Decisions log
- <date>: <decision>, <reason>, approved by <who>
```
