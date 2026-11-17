---
description: "Show pipeline progress and plan usage"
---

# Status

Report where the pipeline stands, in a few lines. Change nothing.

1. Run `bull status` and `bull status usage-check`.
2. Report in a few lines:
   - the stage, and the last checkpoint reached;
   - modules done/total (and units, from stage 5 on);
   - the current or next step;
   - anything blocked, or waiting for the human's approval;
   - plan usage, and when it resets if it reports `PAUSE`.
3. Add a line for each of these that applies:
   - **an active feature**: its slug and its stage;
   - **an adoption** in progress: its stage;
   - **a backlog**: how many features are queued and the first one, from `bull feature list`.

In a stack repo, `bull status` reports the stack instead: give its stage, the checkpoints it has
reached, and its next step.
