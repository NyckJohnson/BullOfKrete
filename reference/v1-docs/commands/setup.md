---
description: Setup — walk the human through the stack's manual steps, then check them (between outline and skeleton)
---

The project setup that only the human can do (for iOS: creating the Xcode project and its build
settings) happens here, after the outline is approved and before `/skeleton`. It does not change the
stage number; it ends with the `setup` checkpoint.

1. `ios-pipeline status usage-check` (stop if PAUSE). The memo must be approved
   (`outline-approved` in `ios-pipeline status summary`); if not, send the human back to `/outline`.
2. Run `ios-pipeline stack check` (it checks every part of an app with several parts, and
   `ios-pipeline part check` their folders). If it already passes, say so, skip to step 5.
3. Run `ios-pipeline stack setup` for the stack's guide (`--part <part>` for each part that needs it,
   one part at a time). Walk the human through it **one step at a
   time**: say exactly what to click or type, using the app's real names from the memo (app name,
   minimum version, capabilities the memo needs), and wait for them to say it's done before the next
   step. Skip steps the check already shows as done. If the guide says you may fill in
   `.pipeline/config.sh`, confirm the names with the human, then do it.
4. Run `ios-pipeline stack check` again. For each ❌, explain the fix in plain words and help the
   human through it; repeat until every item is ✅. If something can't be fixed now, stop and say what
   is missing; do not continue to `/skeleton`.
5. Commit `chore: project setup` (include the project files the human created), then
   `git tag setup` and `ios-pipeline status checkpoint setup`.
6. Tell the human the setup is done and to run `/skeleton`.
