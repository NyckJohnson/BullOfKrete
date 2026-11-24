# Module tag and branch share a name

## Idea

a module's finished tag has the same name as its branch, so git picks the tag on a re-merge after a verify fix and silently merges nothing (hit 2026-11-23 in accept-tests-for-defensive-error); give tags a distinct name, refuse ambiguous merge names, or use a fresh branch for verify fixes

## Discussion notes

## Agreed scope
