---
description: "Stage 4 — build the UI on mocks for the human to try (checkpoint 2)"
---

# Stage 4: UI prototype

The prototype is every screen of the app, built on the modules' mocks so the human can try the flow
before any real behavior exists. The screen-builder agent writes one screen at a time; you brief it,
run the gates, and walk the human through the result.

1. Run `bull status usage-check`. If it reports `PAUSE`, follow the orchestrator's rule for a pause
   and stop.
2. Run `bull status stage 4`. If it is refused, tell the human which earlier step is missing and
   stop.
3. Read the memo's screens section. If the memo has no screens (the app is a tool or a service),
   skip to **No screens** at the end of this file.
4. Set the progress gauge, with one item per screen in the memo:
   `bull status plan prototype <screen>…`. Mirror the items as a task list.
5. Build the screens one at a time, in the memo's order. Per screen:
   1. Run `bull status usage-check`. If it reports `PAUSE`, follow the orchestrator's rule for a
      pause and stop.
   2. Brief the **screen-builder** in the orchestrator's brief shape. In an app with parts, add the
      screen's `PART: <name> (<stack>)` line. `READ ONLY THESE:` lists the screen's memo entry, the
      journeys that pass through it, and the protocols and mocks of the modules it uses (their
      `docs/api/<M>.md` snapshots and mock files).
   3. When it returns `done`, run `bull gates --all --skip-coverage`. On a failure, give the same
      agent the failing output as a `PREVIOUS FAILURE` and try again; each try counts as one
      attempt. If the gates still fail after `max_attempts` attempts, or the agent returns
      `blocked`, ask the human (following **Asking the human** in the orchestrator instructions)
      and stop.
   4. Run `bull status tick <screen>`.
   5. Commit `feat(ui): <Screen> prototype`.
6. Ask the human to try the app the stack's way (running it, or looking at its previews) and to go
   through every journey in the memo, screen by screen. Collect their feedback as a numbered list.
   For each item:
   - **A screen or flow change**: brief the screen-builder for the screens it touches, run the gates
     as in step 5, and update the memo's screens section to match.
   - **A protocol change** (a module's contract has to change): this is checkpoint 3. Explain the
     change, the reason for it and the affected modules, following **Asking the human**. Apply it
     only after approval, memo first: update the memo, then the contract, then the screens.
7. Repeat step 6 until the human approves the flow. Then:
   1. Run `bull status checkpoint ui-approved`.
   2. Run `bull status plan prototype --clear`.
   3. Commit `chore: prototype approved`.
   4. Run `git tag ui-approved`.
8. Tell the human that the prototype is approved and that the next step is to run `/bull:build`.
   This is a good point to start a fresh session; they can run `/bull:resume` there.

## No screens

If the memo has no screens (a command-line tool or a service), there is nothing to prototype.

1. Tell the human so, and ask for their OK to skip this stage.
2. With their OK, add a line to the memo's decisions log recording the skip and the reason.
3. Run `bull status checkpoint ui-approved`.
4. Commit `docs: no screens, prototype skipped`.
5. Run `git tag ui-approved`.
6. Tell the human that the next step is to run `/bull:build`.
