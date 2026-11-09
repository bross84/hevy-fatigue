# AI proposals become inactive drafts only through an explicit save

The AI coach can describe a training week in a structured block, and the athlete can save it as a new inactive draft microcycle with one click. The AI never calls a write route; the browser does, and only on that click. A save never edits, activates, archives or completes an existing plan, sets a weight, or contacts Hevy.

## Why

Letting the model write plans directly would turn unreviewed, possibly wrong advice into the program that loads weights and drives logging. Chat text alone gave the athlete nothing to act on and no link between advice and later training. A draft is the smallest write that keeps the athlete's own review and activation step in the loop.

## Considered options

- **Auto-apply or auto-activate**: rejected. Model error would reach the logger unreviewed.
- **Edit the active plan in place**: rejected. It risks completed days and in-progress sessions, and the plan API guards them for a reason.
- **Copy and paste into the builder**: works today but loses structure and provenance.

## Consequences

- Proposals carry sets, reps and RPE only. Loads still come from TS/TM/RPE loading, and exact RPEs stay with logging.
- Movement ids must already exist locally; titles come from local records, not the model.
- A `plan_proposals` row links each draft to its conversation turn. The coach's outcome review now reads it (read-only) with the draft's completions to report what happened after each save.
- The logger cannot read host conversations, so the browser supplies the reply text. That text is validated again on save and only ever produces an inactive draft of the athlete's own data.
- Adding any path that applies or activates AI output would contradict this decision and should reopen it.
  [ADR 0002](0002-coach-plan-changes-need-a-tap.md) reopens it: plan changes may apply to an existing plan, and a weekly coaching call may make the next microcycle active, but only on the athlete's tap, with undo, and never to trained or skipped days.
