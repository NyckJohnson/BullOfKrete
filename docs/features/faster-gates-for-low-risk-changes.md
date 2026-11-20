# Faster gates for low-risk changes

## Idea

Only test what changed until the end, e.g. stop running the full suite for visual changes. Conflicts
with today's rule that every module merge needs a recorded full-suite pass on a clean tree (the
merge guard). Discuss how far that relaxes, e.g. the full suite once per feature or before
acceptance instead of once per module (decided 2026-11-19: decide at this feature's discuss).

## Discussion notes

## Agreed scope
