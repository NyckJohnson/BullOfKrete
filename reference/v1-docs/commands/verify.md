---
description: Stage 6 — test and verify the full app (checkpoint 4)
---

Run `ios-pipeline status stage 6`.

Before starting, set up the progress gauge so the status line shows done/total:
`ios-pipeline status plan verify mocks-check <one item per user journey, named after it> app-review fixes device-test backlog`
(also mirror it as a task list with TaskCreate). After each item finishes, run
`ios-pipeline status tick <item>` and mark the task complete. When the stage ends,
`ios-pipeline status plan verify --clear`.

1. Confirm the app uses real implementations everywhere; mocks may remain only
   in tests and previews. Search for mock types used outside those places.
2. `usage-check`, then delegate to **ui-test-writer**: one UI test per user
   journey in the memo (in an app with several parts, one brief per part with UI tests, with `PART:` and
   the journeys whose `- Part:` line names it). Run `ios-pipeline gates --app-ui-tests`.
3. `usage-check`, then delegate to **reviewer** with `SCOPE: whole app` (with several parts, the brief
   lists every part, and the reviewer reads each part's rules):
   consistency across modules, accessibility labels, Dynamic Type, dark mode,
   launch time, and anything that only shows up once modules are combined.
4. Route each failure or finding to the module that owns it and rerun that
   module's Stage 5 loop for the unit that owns the affected file. If the design is wrong, propose
   a memo change to the human first.
5. **Device test and feedback.** Ask the human to install the app on a real device, walk through every
   user journey, and tell you everything they notice. Collect it as a numbered list and go through it
   with them; for each item agree one of:
   - **Fix now**: a bug, or the app not doing what the memo says → route it as in step 4.
   - **Later**: new or changed behavior → queue it:
     `ios-pipeline status feature add "<Title>: <what they said>"`.
   - **Drop**.
   After the fixes, ask them to retest those items. Repeat until nothing is left to fix now, then ask
   them to accept the app.

On acceptance: commit, `git tag app-accepted`, `ios-pipeline status checkpoint app-accepted`.

6. **Offer the deferred features.** Show what the discussion set aside, from the memo:
   - `ios-pipeline status feature import docs/outline.md --section "Later features" --dry-run`
   - `ios-pipeline status feature import docs/outline.md --section "Out of scope" --dry-run`
   Present them as two short lists: the later features (planned for after the first version) and the
   out-of-scope items (only if the human now wants any of them), plus whatever step 5 queued. Ask which
   to add to the backlog and in what order. Queue the chosen ones with the same command, without
   `--dry-run`, plus `--only "<Title>" …`; reorder with `ios-pipeline status feature move`. Commit
   `docs: queue features after first release`.
   Then show `ios-pipeline status feature list` and ask whether to start the first one now (`/feature`,
   ideally in a fresh session) or later. If the human wants none, say `/feature` is there when they do.

During an adoption, `/adopt` stage 6 replaces this command. During a feature, `/feature` stage 6 replaces this command (its device test collects feedback the same way).
