---
description: Stage 1 — discuss the app's purpose, stack, journeys and constraints
argument-hint: "[one-line app idea]"
---

Start Stage 1 for this app idea: $ARGUMENTS

Run `ios-pipeline status stage 1`. Then lead a conversation with the human
that ends with all of the following agreed. Ask one or two questions at a time;
don't fire a questionnaire.

- Purpose: one paragraph, plus the target user.
- **Stack**: what the app is built with. Once the purpose is clear, run `ios-pipeline stacks` and offer
  the stacks it lists, with one line each on what they build and what they need; recommend the one that
  fits the purpose. Only listed stacks can be built. If the human wants something that isn't listed,
  say it isn't supported yet (adding stacks is on the pipeline's roadmap) and ask whether to continue
  with a listed one or stop here. On agreement, `ios-pipeline stack select <name>` and commit
  `chore: select <name> stack`. Every later question can then use that stack's terms.
  Offer `experimental` stacks only when asked or when no `verified` one fits, and say they are new.
- **Parts** (only if the app has pieces built with different stacks, e.g. a command-line tool beside an
  iPhone app): agree on each part's name, stack and folder, then `ios-pipeline part add <name> <stack>
  [--dir <folder>]` for each instead of `stack select` (`ios-pipeline part list` shows them). Parts
  can't call each other yet (interfaces between parts come with the first service stack); if they need
  to, say so and agree what to do. Record the parts under `## Stack`.
- Core user journeys, as many as the app needs. Each is a concrete scenario:
  a named user, a goal, the real steps (taps, screens, inputs) and the end state.
  Include failure paths where they matter.
- Features split into MVP and later. Whenever an idea is put off ("not for v1", "maybe later", "nice to
  have"), record it under later features rather than dropping it; after the first version is accepted the
  human is offered these as the feature backlog.
- Constraints: minimum platform version, offline use, accounts, sync, third-party services.
- Out of scope, each with a short reason.

Keep running notes in `docs/discussion-notes.md` as you go and commit them, so
nothing lives only in this conversation. Record the stack and why under `## Stack`. Give the notes `## Later features` and `## Out of scope`
sections with one list item per idea, `- <Title>: <description or reason>`, so they can be queued
as features later. When everything above is agreed, tell
the human to run `/outline`.
