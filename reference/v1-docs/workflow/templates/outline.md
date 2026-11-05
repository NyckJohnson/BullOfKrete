# <App name> outline

<!--
Keep these headings and the "Build order" and "Files:" line formats exactly:
`ios-pipeline status init-modules` parses them.
"Files:" lists the module's files in build order. Split it into work units with "|"
(at most MAX_FILES_PER_UNIT files per unit, 4 by default); each unit gets its own
tests -> code -> gates -> review cycle. A short module is a single unit.

Features (after app-accepted) mark what they change inside each existing module they touch:
  - Changes (<slug>): <File>, …             files whose code changes; their units are rebuilt
  - Contract changes (<slug>): <what>       approved with the memo, applied in the feature's skeleton step
New files go in a new unit ("| <File>") so finished units stay done.

Adopting an existing app (/adopt) adds, and only then:
  - "## Legacy code" (below) with the app-shell allowlist `ios-pipeline status adopt legacy` reads;
  - per module: "- Legacy files:", "- Legacy tests:" and "- Callers to repoint:" lines (each module with
    a Legacy files line gets a final switch-over unit while the adoption runs);
  - "## Known issues": what the survey found wrong; each is fixed in the baseline or queued as a feature.
The behavior spec then describes what the app does today.

An app with several parts (`ios-pipeline part list`; docs/stacks.md in the pipeline) lists them under
Constraints, gives every module and journey a "- Part:" line, and keeps each module's dependencies
inside its own part. A one-part app can leave the Part lines out.

File names, the protocol language and model conventions follow the module's stack:
`ios-pipeline stack rules outline [--part <part>]`.
-->

## Purpose
One paragraph: what the app does and for whom.

## User journeys
1. **<Name>** — <user> wants to <goal>. <Steps: taps, screens, inputs.> Ends when <end state>.
   - Failure path: <what happens if …>
   - Part: <part whose UI tests carry this journey>  (apps with several parts)

## Screens and navigation
- **<Screen>**: <purpose>. Reached from <screen>. Serves journeys <n, m>.

## Constraints
- Stack: <stack name from `ios-pipeline stacks`>
- Parts: <part> (<stack>), <part> (<stack>)  (instead of Stack, in an app with several parts)
- Minimum platform version: …
- Offline: …
- Accounts: …
- Sync: …
- Third-party: …

## Out of scope
- <Title>: <reason>

## Later features
<!-- Put off during the discussion. Offered as the feature backlog when the app is accepted
(`/verify`); one list item per idea so `feature import --section` can read it. -->
- <Title>: <description>

## Data models
### <Model>
| Field | Type | Notes |
| --- | --- | --- |
| id | UUID | |

## Build order
1. <ModuleA> (depends on: none)
2. <ModuleB> (depends on: ModuleA)

## Modules
### <ModuleA>
- Part: <part>                                     (apps with several parts)
- Purpose: …
- Depends on: none
- Files: <File1>, <File2> | <File3>, <File4>        (file names with extension, in build order)
- Protocol (draft; lives in `Contracts/`):
  ```<language>
  <protocol in the stack's language>
  ```
- Behavior spec (one line per behavior the tests must cover):
  - <operation>: <input> → <result>; <error case> → throws `<Error>.<case>`
- Anticipated operations (not built yet): …
- Contract: see `docs/api/<ModuleA>.md` (generated; do not edit by hand)
- Legacy files: <legacy paths this module replaces>  (adoption only)
- Legacy tests: <old test files it replaces>         (adoption only)
- Callers to repoint: <legacy files that use it, or none>  (adoption only)
- Changes (<feature-slug>): <File2>                (features only)
- Contract changes (<feature-slug>): <what changes>  (features only)

## Legacy code
<!-- Adoption only. Paths relative to APP_SOURCE_DIR. Remove the section's other lines once adopted. -->
- App shell: <entry point>, <composition root>, <assets and app configuration files> (the stack's memo rules list what belongs here)
- App shell tests: <test files and folders that belong to the app shell, not a module, or none>  (paths relative to APP_TEST_DIR)
- Legacy folders: <folders the survey covered>
- Renames: <LegacyType> → Legacy<LegacyType>, … (legacy types whose names a contract takes; done in the scaffold)

## Known issues
<!-- Adoption only. What the survey found wrong, with where; fixed in the baseline or queued as a feature. -->
- <issue> — <file:line> — fixed in baseline | feature <slug>

## Features
<!-- Accepted features, oldest first. -->
- <YYYY-MM-DD>: <slug> — <one line> — tag `feature/<slug>/accepted`

## Decisions log
- <YYYY-MM-DD>: <decision> — <reason> — approved by <who>
