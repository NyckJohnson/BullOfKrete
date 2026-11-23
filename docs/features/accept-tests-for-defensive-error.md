# Accept tests for defensive error handling

## Idea

When code-writer adds defensive error handling the memo never mentions (bad input, I/O errors,
unreadable files), coverage triage no longer stops to ask. The behavior is added to the spec, tested,
and each case is listed in the decisions log for the human to review afterwards. Anything that
changes visible behavior still asks. Changes the coverage-triage rule that `not-in-spec` always goes
to the human (decided 2026-11-19: auto-accept, logged).

## Discussion notes

- 2026-11-23: where the rule lives today: `orchestrator.md` Stage 5 loop step 4 ("`not-in-spec`:
  ask the human…"), `agents/coverage-analyst.md` (classes missed / exempt / not-in-spec),
  `commands/build.md` step 7 (coverage findings that need the human). All in module plugin_text;
  `PluginText` contract unchanged (Markdown only). Tests pinning the wording:
  `tests/plugin_text/test_orchestrator.py`, `tests/plugin_text/test_agents_checkers.py`.
- Precedent: every coverage-triage decisions-log entry since 2026-11-08 kept and specified the
  not-in-spec code (damaged files → `FileFormatError`, failing tool → not ok, unreadable inputs…);
  none was removed.
- 2026-11-23, human: the goal — the most common stop is "code-writer added error handling the spec
  doesn't mention and no test covers it; recommend adding it to the spec and testing it". These
  should be auto-approved as long as there is no downside.
- 2026-11-23, agreed: "no downside" means all five hold, otherwise bull asks as today:
  1. it runs only when something is already wrong (damaged or unreadable file, failing command, bad
     argument); normal input behaves exactly as before;
  2. it fails cleanly: raises an error type the module already uses (a new message is fine), or
     skips the broken item;
  3. it never writes, deletes or overwrites anything;
  4. it changes no contract;
  5. it is cheap (human's addition): no retry loops, waits or timeouts, no extra programs or network
     calls, no re-reading or scanning large files.
- First proposal (superseded where the agreed points differ):
  - coverage-analyst gets a fourth class, `defensive`: code reached only when an input or the
    environment is bad (malformed or unreadable file, I/O or subprocess failure, an argument of the
    wrong shape), whose only effect is to fail cleanly through an error the module already uses, or
    to skip the bad item. Everything else stays `not-in-spec`.
  - The orchestrator adds each `defensive` case to the module's behavior spec as a "Guards
    (defensive, auto-accepted)" line, briefs test-writer from the spec, and logs it.
  - Still asks: new or changed output on a success path, a new error the caller can't already get,
    a contract change, anything that writes, deletes or overwrites, refusing an input that used to
    work.
  - Scope: coverage triage only. Reference-scan and adoption-scan `not-in-spec` still ask.

## Agreed scope
