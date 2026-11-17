---
description: "Stage 1 — discuss the app's purpose, stack, journeys and constraints"
argument-hint: "[one-line app idea]"
---

# Stage 1: Discuss

You are starting a new app. The human's idea, if they gave one: $ARGUMENTS

1. Run `bull status usage-check`. If it reports `PAUSE`, follow the orchestrator's rule for a pause
   and stop.
2. Run `bull status stage 1`.
3. Lead a conversation about the app. Ask one or two questions at a time and build on the answers.
   Never hand the human a questionnaire. Push back gently when an answer is vague, and suggest
   options when they are unsure.
4. Keep running notes in `docs/discussion-notes.md` as you go, and commit them after each topic is
   settled, so nothing lives only in this conversation.
5. By the end of the conversation, agree on each of these:
   - **Purpose and target user.** What the app is for, who uses it, and what problem it solves for
     them.
   - **Stack.** Run `bull stacks` and tell the human, in one line each, what every listed stack
     builds and what it needs. Recommend one, with a reason.
     - Offer only stacks that `bull stacks` lists.
     - Offer an `experimental` stack only when the human asks for it or no `verified` stack fits,
       and say plainly that it is new.
     - If the human wants a stack that is not listed, say that it can be built as a new stack: the
       human runs `bull init --stack <path>` to start a stack repo, then `/bull:stack` in that repo.
       Then ask whether to continue with a listed stack or stop here.
     - When you agree, run `bull stack select <name>` and commit `chore: select <name> stack`.
   - **Parts**, only when pieces of the app need different stacks (for example a command-line
     tool and a web page). Instead of `bull stack select`, run
     `bull part add <name> <stack> [--dir <folder>]` for each part. Parts talk to each other only through interfaces, so agree
     which interfaces exist, the file format of each, and which part provides it and which parts
     consume it.
   - **Journeys.** For each one: the named user, their goal, the real steps they take, the end
     state, and the failure paths (what goes wrong and what the user sees then).
   - **MVP and later features.** What the first version must do, and what can wait. Anything put
     off goes on the later features list. Never drop an idea.
   - **Constraints.** The minimum platform or runtime version, offline use, accounts, sync, and any
     third-party services.
   - **Out of scope.** What the app will not do, each with a reason.
6. Give the notes these sections, so the outline and later steps can read them:
   - `## Stack`: the stack, the parts if there are any, and why they were chosen.
   - `## Later features`: one `- <Title>: <description>` item per feature.
   - `## Out of scope`: one `- <Title>: <reason>` item per entry.

   The item format matters: `bull feature import` reads these lists to queue features later.
7. Read the notes back to the human and fix anything they correct. Commit the final notes.
8. Tell the human that the discussion is done and that the next step is to run `/bull:outline`.
