<!-- ios-pipeline:begin (managed by `ios-pipeline init`; do not edit this block) -->
@/Users/nicholasjohnson/Documents/Programs/ios-agent-pipeline/orchestrator.md
<!-- ios-pipeline:end -->

## App notes (BullOfKrete)
- Read docs/bull-v2-brief.md before /discuss and /outline; its decisions are settled.
- reference/ is read-only. Only legacy-test-scanner reads reference/v1-tests/; never list
  reference/ in a test-writer or code-writer brief.
- Reference tests: after each module's last unit and before coverage triage, run
  legacy-test-scanner on the module's `Reference tests:` line, as described in the brief.
