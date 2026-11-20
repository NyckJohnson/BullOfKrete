# BullOfKrete feature ideas

Merged on 2026-11-19 from `docs/todobull.rtfd` (order and tiers), `docs/ROADMAP.md`, `docs/gui.md`
and the memo's `## Later features`; todobull and ROADMAP.md were then deleted, and this file and
the briefs in `docs/features/` replace them. ROADMAP.md and gui.md were written for v1 (`ios-pipeline`,
`.pipeline/`, shell config); each feature's discussion restates them in bull's terms. Parts that
v2.0 already built are left out: the iOS run hygiene (one simulator by UDID, no parallel testing,
diagnostics on failure, build output under `.bull/` with prune), the event log, `--json` output,
`bull config show/set` with per-agent models, and the provider seam.

Tiers from todobull: Immediate (1–8), Intermediate (9–15), Low (16–21), Limbo (22).

## Clear and resume in one command
A single command that does `/clear` and then `/bull:resume`, so starting a fresh session at a
handoff point is one step. The lightweight forerunner of "Automatic orchestrator restarts".
Open: whether a plugin command can clear the conversation itself, or this needs bull to restart the
session from outside.

## Accept tests for defensive error handling
When code-writer adds defensive error handling the memo never mentions (bad input, I/O errors,
unreadable files), coverage triage no longer stops to ask. The behavior is added to the spec, tested,
and each case is listed in the decisions log for the human to review afterwards. Anything that
changes visible behavior still asks. Changes the coverage-triage rule that `not-in-spec` always goes
to the human (decided 2026-11-19: auto-accept, logged).

## Faster gates for low-risk changes
Only test what changed until the end, e.g. stop running the full suite for visual changes. Conflicts
with today's rule that every module merge needs a recorded full-suite pass on a clean tree (the
merge guard). Discuss how far that relaxes, e.g. the full suite once per feature or before
acceptance instead of once per module (decided 2026-11-19: decide at this feature's discuss).

## GUI
A local GUI across all registered apps: the real coding-agent session in a terminal, each app's
progress at a glance, and doc review where feedback becomes change sets the orchestrator applies.
No approvals in the GUI. Design: `docs/gui.md` (agreed 2026-10-24/27 for v1; restate in bull terms).
It settles the memo's open question as a local web app (Python backend, plain HTML/JS, 127.0.0.1,
token and Origin checks, tmux-backed sessions, xterm.js). Prerequisites from gui.md not yet in bull:
an app registry (`bull apps`), a general "waiting for the human" state (today `status wait` covers
contract changes only), context use in `usage.json`, and the pending-edits queue with its
step-boundary check. gui.md plans six PRs; discuss may split this into several features. Open: how
the GUI itself is built (see "Stack for the GUI").

## Show subagents' context use
Show how much of its context window each subagent used, alongside the orchestrator session's context
use (gui.md's header shows the session's). Shown in the GUI and in `bull status`.

## Stack for the GUI
New stacks needed to build the GUI through bull itself: a web/service stack (Python HTTP backend,
HTML/JS frontend). Absorbs the memo's "Service stack" idea: a stack whose part runs as a service,
giving OpenAPI interfaces and running parts together their first real stack. If the GUI is built
through bull, this comes before the GUI.

## Settings page
One place to see and change settings instead of `bull config set`: every layer (bull defaults →
stack → user → app → part), showing which layer each value comes from, validated on write. Exposes
usage pause thresholds, max attempts, max files per unit, review mode, coverage exclusions, each
agent's model and the simulator. No AI-provider choice yet: that arrives with "Other AI providers"
(decided 2026-11-19). Open: a GUI page or its own screen.

## Phone notifications
Send pipeline updates to the user's phone when a session stops (waiting for the human, blocked,
paused with reset time, finished), naming the app and the reason, from the agent's Stop and
Notification hooks. Replies: plain text, `/clear`, `/bull:resume` or `/bull:status` only, typed into
the app's tmux session by a relay on the Mac. Security: outbound polling only, owner's account only,
input only while the session is idle. bull's first network service. Shares the waiting state and
tmux sessions with the GUI. Details: `docs/gui.md` § Related. Open: channel (Telegram bot preferred,
email the alternative); whether finished long steps also notify.

## Log everything
Extend the event log (`.bull/events.jsonl`) so it records everything the reports need: time paused
for usage, time waiting on the human, simulator-busy retries, and subagent end events. Reading the
log must survive a torn non-UTF-8 write by skipping the damaged line; today `EventLog.read` fails on
the whole file (found in events review, 2026-11-08).

## Time report
`bull status time` totals by stage, module, unit (by step and attempt), agent and gate step, plus
the slowest items and where retries cost time; `--feature <slug>` scopes it; `/bull:status` shows a
one-line total. From the event log. Open (ROADMAP item 4): wall-clock or active time (overnight gaps
and pauses as their own lines); human wait time in totals or separate; backfill from git timestamps
or start fresh; usage per step alongside time; build on LangSmith or Claude Code's OpenTelemetry for
the agent side, or emit bull's events as OpenTelemetry (trade-off: dependency and lock-in to one
coding agent vs. building it).

## Token report
Tokens used per stage, module, unit and agent.

## Kaizen review
A review that reads the logs, time and token reports to find efficiency improvements in the
pipeline itself, e.g. slow gate steps, units that often need retries, agents that use the most
context.

## Other AI providers
Run bull on other coding agents behind the existing provider seam, Claude Code on a Claude plan
staying the default; adds the provider choice to the settings page. What's Claude Code-specific:
launching, plugin format (commands, agents with model/tools frontmatter, hooks), the hooks the
safeguards rely on, the instruction files and settings, usage pausing from the status line, model
names. Open (ROADMAP item 6): which providers first and whether they have subagents; keeping the
safeguards without hooks (git hooks, checks in gates); usage pausing where usage is reported
differently; mixed setups (a different model for reviewers).

## Store readiness
Check that an accepted app is ready for its store. Generic: an optional stack release hook, run
after acceptance and at the end of each feature; stacks without it skip. iOS checks: privacy
manifest with required-reason APIs found in the source, data types and tracking domains; the 1024
app icon (and dark/tinted variants); a specific usage-description string for every permission used.
A reviewer "store guidelines" category (account deletion, Sign in with Apple, in-app purchase,
placeholder content, dead buttons, unexplained permissions). A manual checklist (privacy labels, age
rating, screenshots, support and privacy URLs, export compliance). Open (ROADMAP item 7): blocking or
advisory; its own command or part of verify; keep the iOS checklist dated and recheck it against
Apple's current guidelines.

## Automatic orchestrator restarts
Restart the orchestrator session automatically at module boundaries so context stays small: bull
drives the coding agent from outside. Needs its own design.

## Windows support
Hooks, paths and git behave differently on Windows. v2.0 avoided needless POSIX-only assumptions.

## Detect when an app should be split
Tell when an app has grown large enough that it should be separated into several apps.

## Spin modules off into their own apps
Move a module (or a part) into its own app. Was out of scope for v2.0 ("splitting a part into its
own app"), together with interfaces shared between apps, which this likely needs.

## Adopt and translate
Adopt an existing app while moving it to another stack (e.g. rewrite it in another language),
using its legacy tests as reference tests, as the v2 rewrite did.

## python_cli adoption support
`detect` and `inventory` for the python_cli stack, so existing Python apps can be adopted (journey 5
uses the fixture stack today).

## bash_shell stack
Rebuild the bash_shell stack through the stack workflow.

## Quieter iOS test runs
In limbo: the simulator audio crackling went away before the planned experiments ran. Remaining
experiments: shut down simulators after every run (conflicts with reusing one booted simulator),
report orphaned simulators at the start of a run, keep screenshots out of Photos and Spotlight
(Spotlight Privacy as a manual setup step), `XCTAttachment.lifetime = .deleteOnSuccess` in the UI
test rules. Open: whether reusing one booted simulator conflicts with clean-state launches; the
speed cost of no parallel testing for large suites.
