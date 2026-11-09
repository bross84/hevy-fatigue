# AI coach plan changes apply only when the athlete taps to accept

Status: accepted and implemented 2026-11-09: step 1 (plan changes from AI Coach chat, Accept and Undo) and
step 2 (the weekly coaching call, Accept as next week, Run it back and their Undo).
Reopens and partly supersedes
[ADR 0001](0001-ai-proposals-become-drafts.md).

Planning happens in a **weekly coaching call**: one AI Coach session that starts by itself when a microcycle rolls over to day 1, whenever that falls on the calendar. It replaces the separate opening and closing reviews. The coach reviews the microcycle that just ended and lays out the next one, either unchanged, with a few changes, or as something new with its reasons. The athlete sees exactly what changes, day by day, and taps Accept or asks for changes. Accept makes that microcycle the active one immediately. "Run it back" repeats the last microcycle unchanged without waiting on the AI. Between calls, the plan changes only if the athlete asks the coach in chat, and that **plan change** also applies only on a tap.

Every write comes from the browser, and only on the athlete's tap; the AI never calls a write route. An accepted change can be undone with one tap. Days already trained or skipped are never changed, weights are never set, and Hevy is never contacted.

## Why

The athlete wants a check-in like a remote coach (or MacroFactor's weekly check-in): review, adjust, train, with no trip to the builder in between. Their training weeks don't follow the calendar, so the trigger is the microcycle rolling over to day 1, not a weekday. Under ADR 0001 every suggestion became a separate inactive draft that then had to be found, compared and activated. A copy of a started microcycle also didn't carry its completed days, which split the history. Seeing the exact change and tapping to accept it is real review. The extra copy and activation steps added friction, not safety.

## What stays from ADR 0001

- The AI only advises. The athlete decides, and may ignore advice.
- Loads still come from TS/TM/RPE loading. Exact RPEs stay with logging.
- A new microcycle becomes active only through the athlete's Accept or Run it back tap, never by the AI alone.
- Reply text is untrusted: it is validated again on accept, and movement titles come from local records.

## Considered options

- **Drafts only (ADR 0001 as written)**: rejected. Several rounds of refining produced piles of copies, and the athlete still had to activate the result elsewhere.
- **Load the change into the builder as unsaved edits**: workable, but every check-in would need a trip to another page.
- **Coach applies changes without a tap**: rejected. A confused or prompt-injected reply would change training with nobody checking.
- **Daily automatic adjustments from check-ins**: deferred. Daily check-ins feed the next call but change nothing on their own for now.

## Consequences

- A change is tied to the plan version it was written against. If the plan changed in the meantime, accepting it is refused and the athlete is asked to refresh.
- Each accepted change keeps the previous version so it can be undone, and is linked to its conversation turn so later calls can see what was changed and why.
- Later refinements in the same call or chat build on the latest accepted version, not on separate copies.
- When the athlete declines or ignores advice, the coach raises it again only if training shows something new.
- The coach raises "time for a new stimulus" in the weekly call when the evidence warrants it, giving the idea and its reasons first and building the program once the athlete agrees.
- Plans carry no ME/RE labels. The coach judges from reps, RPE and check-ins.
- The coach may use any movement in the local exercise library, not only ones trained before. Creating new custom movements is a later, separate change.
