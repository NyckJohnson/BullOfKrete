# Pipeline GUI (`ios-pipeline gui`)

Design for roadmap item 1: a local web GUI across all apps. Agreed with the user on 2026-10-24;
remote access and rollout added 2026-10-27. Status: designed, not started (built in several PRs,
listed at the end).

## Goal

One browser window to work on any registered app: the real Claude Code session in a terminal, the
app's progress at a glance, and the app's docs to review, with feedback turned into edits the
orchestrator applies. The GUI adds no second way to drive the pipeline: approvals and decisions still
happen in the orchestrator session, and the GUI reads state only through `ios-pipeline`.

## Decisions

| Topic | Decision |
| --- | --- |
| Form | Local web app: Python backend, plain HTML/JS frontend, served on `127.0.0.1` |
| Scope | Monitor + console + doc review. No GUI approvals; checkpoints are answered in the terminal |
| Terminal | The real `claude` session in xterm.js, backed by one `tmux` session per app |
| App selector | Switches between registered apps only; creating and adopting stay in the CLI |
| Doc edits | Never written directly. A feedback agent drafts change sets; the orchestrator applies them |
| Applying edits | Automatic at the next step boundary, unless an edit is unclear or conflicts (see below) |
| Consistency | Every app doc goes through the queue, including inactive feature briefs and discussion notes |
| Alerts | Blocked units, waiting checkpoints, pauses and pending edits stand out |
| Remote access | Not through the GUI. Notifications and replies go through a messaging relay (roadmap item 2) |
| Rollout | Developed in a separate checkout; PRs land one at a time, at a natural pause (see Rollout) |

## Layout

```
┌──────────────────────────────────────────────────────────────────────┐
│ [Tally ▾]  5h 42% · 7d 61%  ctx 38% (2 min ago)  ⚠ 1  ✎ 2   Console | Docs │
├────────────────────────────────────────────┬─────────────────────────┤
│                                            │ Console: progress        │
│  Console: claude terminal                  │ Docs: feedback agent     │
│  Docs:    document reader                  │                          │
└────────────────────────────────────────────┴─────────────────────────┘
```

- **Header:** app selector; plan usage (5-hour, 7-day) and the session's context use, each with its
  age (the data only updates while a session responds); alert badges (⚠ blocked or waiting,
  ✎ pending edits); the Console / Docs switch.
- **Console mode:** terminal on the left, progress panel on the right.
- **Docs mode:** document reader on the left, feedback conversation on the right.

## Prerequisites in the pipeline

These land first and are useful without the GUI.

### App registry

- `ios-pipeline init` adds the app's absolute path to `~/.ios-pipeline/apps.json` (rerunning is a
  no-op; moving an app means rerunning `init`).
- `ios-pipeline apps [--json]` lists registered apps, marking missing paths;
  `ios-pipeline apps forget <path>` removes one.

### Read API

- `ios-pipeline status --json` prints everything the GUI shows: stage and checkpoints, modules, units
  and attempts, blocked units, pause and reset time, the active feature or adoption, the plan gauge,
  usage, waiting state and pending edits. It carries a `schema_version`; the GUI reads nothing else
  from `.pipeline/`, so internal file formats can change freely.
- `ios-pipeline status waiting "<what>"` / `status waiting --clear`: the orchestrator sets it when it
  stops for the human (a checkpoint, a blocked unit's question, a contract change) and clears it on
  the answer. Today nothing records "waiting for the human", so the GUI could not flag it.
- The status line also writes the session's context-window use to `usage.json`, if Claude Code
  passes it to the status line. If it doesn't, the header leaves context out.

## Console

- Each app's session runs in `tmux` session `pipeline-<app folder name>`, started with
  `ios-pipeline open <app>`. The backend attaches to it through a PTY and streams it over a
  websocket to xterm.js (resize and keyboard pass through).
- Switching apps re-attaches the terminal; closing the browser detaches. Sessions keep running, and
  `tmux attach -t pipeline-<app>` works from any terminal.
- An app without a session shows **Open session** and **Continue last session** (`--continue`).
- One `tmux` session per app means one orchestrator per app.
- `tmux` starts behind an option (`ios-pipeline open --tmux`) and becomes the default only once
  Claude Code's interface has been tried inside it. Until then, the console attaches only to
  sessions started with the option.

## Progress panel

- Stages 1–6 (with setup) as a checklist. Stage 5 expands to modules, then units, then the unit's
  steps (tests, code, done) with attempts (`2/3`).
- During a feature or an adoption, the panel shows that run's stages under a header
  (`Feature: streak-reminders`, `Adopting`), with the backlog count below.
- **Stand out:** blocked units (red, with the question if recorded), waiting checkpoints (amber,
  "Waiting for you: approve the outline"), pause (with reset time). Each also raises the header badge.
- Updates by polling `status --json` every few seconds.

## Docs mode

### Reader

- Tree of the app's docs: `docs/outline.md`, `docs/discussion-notes.md`, `docs/features/`,
  `docs/api/` (marked generated). Rendered Markdown, with a source view.
- Pending change sets appear inline as diffs on the document they change.

### Feedback agent

- A conversation in the right panel. Each turn is a headless Claude Code run (`claude -p`, resuming
  the same session for follow-ups) in the app folder, with a dedicated agent definition
  (`agents/doc-feedback.md`, model `sonnet`).
- It reads the app's docs and `status --json`, and asks when feedback is unclear. It never edits
  docs: its only output is a **change set** in `.pipeline/pending-edits/<id>.md`: the target file,
  a unified diff against the current commit, and the reasoning. A hook enforces that write scope, in
  the same way as the test-protection hook.
- `docs/api/` is never a target; it is regenerated from code.
- Every turn runs `ios-pipeline status usage-check` first and stops on `PAUSE`, like any step: the
  agent draws on the same plan.
- You review each change set's diff, then **Queue** or **Discard** it. Only queued change sets reach
  the orchestrator.

### Applying edits

Why the queue: documents must not change mid-step (subagents build from the memo, a dirty tree voids
the merge guard's recorded gate pass, and resume discards uncommitted changes), and only the
orchestrator edits the memo (golden rule 4).

- `.pipeline/pending-edits/` is git-ignored (written by `init`), so queued edits never dirty the tree.
- `ios-pipeline edits list | check | done <id> | reject <id> "<reason>"`.
- **When:** at every step boundary, after `usage-check`, the orchestrator runs `edits check`. In
  stages 1–2 (no subagent steps), it checks at the start of each reply. With no session running,
  edits wait; the session-start hook announces them.
- **Applied automatically** when the diff applies cleanly and only touches work not yet started:
  the orchestrator applies it, adds a Decisions log entry if the memo was approved, commits
  `docs: apply edit <id>` and marks it done.
- **Raised with the human** (in the terminal; the waiting state flags it in the GUI) when:
  - the diff no longer applies, or two queued edits conflict;
  - it contradicts another part of the memo, or its intent is unclear;
  - it changes the spec or contract of a module in progress or done (units would reopen or rebuild);
    golden rule 5 still applies to contract changes;
  - it targets the brief of the active feature in a way that changes agreed scope.
- A rejected edit keeps its reason, shown on the change set in the GUI.

## Server and security

- `ios-pipeline gui [--port N]` starts the server on `127.0.0.1` and opens the browser.
- A random token is generated at start and passed in the opening URL; every request and websocket
  must carry it. The `Origin` header is checked; no CORS. It serves a shell, so nothing else on the
  machine may reach it.
- The backend runs commands only through `ios-pipeline`, `tmux` and `claude`.
- New requirements: `tmux` (`brew install tmux`) and the `websockets` Python package. `ios-pipeline gui`
  checks both and prints the install command if missing. xterm.js and the Markdown renderer are
  vendored, so the GUI works offline.

## Related: remote notifications and replies (roadmap item 2)

Checking on progress and giving input away from the Mac is a separate roadmap item, not part of the
GUI: a messaging channel is simpler and safer than exposing a server that serves a shell. Summary of
what was agreed:

- **Notify** when a session stops (waiting for the human, blocked, paused with reset time, finished),
  from Claude Code's `Stop` and `Notification` hooks. The message names the app and the reason and
  includes the session's last message.
- **Reply** with a plain-text answer, `/clear`, `/pipeline-resume` or `/pipeline-status`; nothing
  else (no other slash commands, no shell, no permission approvals). A relay on the Mac polls the
  channel and types the reply into the app's `tmux` session.
- **Security:** outbound polling only (no open ports); only the owner's account is accepted; input is
  delivered only while the session is idle; a reply goes to the app whose message it answers.
- **Shared with the GUI:** `status waiting` (PR 1) and sessions in `tmux` (PR 3).
- **Open:** channel (Telegram bot preferred; email the alternative), and whether finished long steps
  also notify.

## Rollout

Every app uses the installed pipeline, with no per-app pinning, so each PR reaches apps in progress
(such as an adoption) at their next session.

| PR | Process change | Risk to an app in progress |
| --- | --- | --- |
| 1 | Additive; the orchestrator gains one instruction (`waiting`) | Low, if a missing `waiting` field reads as unset |
| 2 | `edits check` at every step boundary; session-start hook reports pending edits; no-op with an empty queue | Medium: changes the orchestrator loop; needs `init` rerun for `.gitignore` |
| 3 | Sessions in `tmux`, behind `--tmux` | Medium once it is the default; none while optional |
| 4–5 | None; the GUI only reads state | Low, if the feedback agent's write-scope hook applies only to that agent |

Rules for upgrading while another app is being built:

- **Develop in a separate clone or `git worktree`**, never in the installed folder
  (`~/Developer/ios-agent-pipeline`): switching branches there changes what every app runs.
- **Upgrade at a module tag**, with a clean tree and nothing waiting; not mid-module.
- **Tag the installed pipeline before pulling** (`git -C ~/Developer/ios-agent-pipeline tag pre-gui-<n>`)
  so rollback is one checkout.
- **One PR at a time.** After each: the pipeline's unit tests, `ios-pipeline init <app>` and commit,
  then `/hooks`, `/pipeline-status` and `ios-pipeline status summary`.
- **Try each PR on a scratch app first** (`ios-pipeline init ~/Developer/Scratch`).
- During an adoption, PRs 1, 4 and 5 can land at any pause. Hold PR 2 and making `tmux` the default
  until the adoption finishes, or at least until it is between modules. Until then the GUI monitors
  the adopting app but doesn't run its console.

## Build plan

| PR | Contents |
| --- | --- |
| 1 | App registry (`init`, `apps`), `status --json` with `schema_version`, `status waiting`, context use in `usage.json`; orchestrator sets `waiting` |
| 2 | Pending edits: `.pipeline/pending-edits/`, `ios-pipeline edits`, orchestrator rules (step-boundary check, auto-apply and raise conditions), session-start announcement, `.gitignore` |
| 3 | `ios-pipeline gui`: server, token, `tmux` sessions (`open --tmux`), PTY websocket, header with app selector and usage, console mode |
| 4 | Progress panel, alerts and badges |
| 5 | Docs mode: reader, `doc-feedback` agent and its write-scope hook, change-set review (queue, discard) |
| 6 | README, `ROADMAP.md` (item done) and orchestrator docs |

Scripts get unit tests as usual (registry, JSON schema, edits). The server gets tests for the token
and origin checks.

## Open

- Whether the status line receives context-window data in the installed Claude Code version
  (checked in PR 1).
- How the feedback agent's write-scope hook identifies its session (likely an environment variable
  set by the GUI backend).
- How the GUI itself is built: with Claude Code in its own checkout, or through the pipeline.
- When `tmux` becomes the default for `ios-pipeline open`.
