---
description: Stage 4 — build the UI on mocks for the human to try (checkpoint 2)
---

Run `ios-pipeline status stage 4`.

Start the gauge: `ios-pipeline status plan prototype <one item per screen>`; `tick <screen>` after
each screen's commit; `plan prototype --clear` when the human approves.

For each screen in the memo's "Screens and navigation" section, one at a time:
1. `usage-check`; stop if PAUSE.
2. Delegate to **screen-builder** (with `PART:` for the screen's part, in an app with several parts): the screen's memo entry, the journeys it
   serves, and the protocols and mocks it depends on.
3. Run `ios-pipeline gates --all --skip-coverage`. Fix through the same subagent
   (max 3 attempts).
4. Commit `feat(ui): <Screen> prototype`.

Then ask the human to run the app (simulator or device) and walk through every
user journey. Collect their feedback as a list. For each item:
- Screen or flow change → screen-builder, then update the memo's screens section.
- Needs a protocol change → this is checkpoint 3. Explain the change, the reason
  and the affected modules; apply only after approval, memo first.

Repeat until the human approves the flow. Then commit, `git tag ui-approved`,
`ios-pipeline status checkpoint ui-approved`, and tell them to run `/build`.
