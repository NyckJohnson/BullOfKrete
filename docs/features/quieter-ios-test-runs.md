# Quieter iOS test runs

## Idea

In limbo: the simulator audio crackling went away before the planned experiments ran. Remaining
experiments: shut down simulators after every run (conflicts with reusing one booted simulator),
report orphaned simulators at the start of a run, keep screenshots out of Photos and Spotlight
(Spotlight Privacy as a manual setup step), `XCTAttachment.lifetime = .deleteOnSuccess` in the UI
test rules. Open: whether reusing one booted simulator conflicts with clean-state launches; the
speed cost of no parallel testing for large suites.

## Discussion notes

## Agreed scope
