# Accept tests for defensive error handling

## Idea

When code-writer adds defensive error handling the memo never mentions (bad input, I/O errors,
unreadable files), coverage triage no longer stops to ask. The behavior is added to the spec, tested,
and each case is listed in the decisions log for the human to review afterwards. Anything that
changes visible behavior still asks. Changes the coverage-triage rule that `not-in-spec` always goes
to the human (decided 2026-11-19: auto-accept, logged).

## Discussion notes

## Agreed scope
