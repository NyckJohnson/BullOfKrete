# Store readiness

## Idea

Check that an accepted app is ready for its store. Generic: an optional stack release hook, run
after acceptance and at the end of each feature; stacks without it skip. iOS checks: privacy
manifest with required-reason APIs found in the source, data types and tracking domains; the 1024
app icon (and dark/tinted variants); a specific usage-description string for every permission used.
A reviewer "store guidelines" category (account deletion, Sign in with Apple, in-app purchase,
placeholder content, dead buttons, unexplained permissions). A manual checklist (privacy labels, age
rating, screenshots, support and privacy URLs, export compliance). Open (ROADMAP item 7): blocking or
advisory; its own command or part of verify; keep the iOS checklist dated and recheck it against
Apple's current guidelines.

## Discussion notes

## Agreed scope
