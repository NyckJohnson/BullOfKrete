---
description: "Setup — walk the human through the stack's manual steps, then check them (between outline and skeleton)"
---

# Setup

Some steps of a new project only the human can do, for example creating the project files the
stack's tools need. You walk them through those steps, then check that everything is in place
before the skeleton is built.

1. Run `bull status usage-check`. If it reports `PAUSE`, follow the orchestrator's rule for a pause
   and stop.
2. Run `bull status` and check that the `outline-approved` checkpoint is recorded. If it is not,
   the memo is not approved yet: tell the human to run `/bull:outline` first, and stop.
3. Run `bull stack check`, for every part if the app has parts, and `bull part check` as well. If
   every check is passing, go straight to step 5.
4. Walk the human through the stack's setup guide:
   1. Show the guide with `bull stack setup`. In an app with parts, go one part at a time with
      `bull stack setup --part <name>`.
   2. Go one step at a time. Fill in the memo's real names (the app, its modules, its folders)
      instead of the guide's placeholders. After each step, wait for the human to say "done"
      before giving the next one.
   3. Skip any step that the check already shows as done.
   4. When the guide says a setting must be set, confirm the value with the human first, then run
      `bull config set <key> <value>` (with `--part <name>` for a part's setting).
   5. When the steps are done, re-check with `bull stack check` (and `bull part check`). Repeat
      until every line is ✅. For each ❌, explain in plain words what it means and how to fix it,
      and walk the human through the fix.
   6. If a ❌ cannot be fixed, stop: tell the human what is failing and why, and don't continue to
      the next stage.
5. When every check passes:
   1. Run `bull status checkpoint setup`.
   2. Commit `chore: project setup`.
   3. Run `git tag setup`.
6. Tell the human that setup is done and that the next step is to run `/bull:skeleton`.
