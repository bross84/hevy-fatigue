# Plan: retire the model trial v0 and start v1

Status: draft for Brian's review, revised 2026-11-26 after measuring his history.
Nothing implemented.

## Why

The current trial (`shared-trial-v0`) asks a good question: does the pre-workout
check-in predict a below-usual lifting day better than assuming every day is normal?
It cannot answer it for how Brian trains. A session only counts when three earlier
sessions had the same top-set reps, RPE within 1 and the same exercise position. Top
sets move between 1, 2 and 3 reps, so after about six weeks every movement has 0 of
12 eligible predictions, and that will not change.

## What the history shows (read-only, 2026-11-26)

Source: the app's own read-only pages (RPE charts fit, movement trend, daily check-in
history). No Hevy calls, no database copy, nothing written.

### 1. Almost all training is below RPE 8

| Table | Sets RPE 5–7.5 | Sets RPE 8+ |
| --- | --- | --- |
| Squat | 55 | 4 |
| Bench | 34 | 5 |
| Deadlift | 19 | 4 |
| General | 35 | 7 |

A trial built on heavy sets would ignore about 90% of the training, even now, before
any future volume block.

### 2. Brian's RPE 5–7.5 calls are about as consistent as his heavy ones

Spread of single sets around that session's fitted estimated max:

| Table | RPE 5–6 | RPE 6.5–7.5 | RPE 8+ |
| --- | --- | --- | --- |
| Squat | 2.5% | 2.6% | 1.4% (4 sets) |
| Bench | 1.7% | 1.7% | 1.9% (5 sets) |
| Deadlift | 2.8% | 0.7% (5 sets) | 3.7% (4 sets) |
| General | 1.2% | 1.8% | 2.3% (7 sets) |

Caveat: the app reports averaged cells rather than single sets, so true single-set
spread is somewhat larger. The heavy band has too few sets to trust. There is no sign
that lighter sets are much noisier for Brian, so separate RPE bands are not needed.

### 3. Normal session-to-session swing is 2–3%

Each session's estimated max against the middle of the previous three:

- Squat, low bar (9 comparisons): -4.2, +1.9, +1.2, +1.2, -0.1, -1.8, -4.4, +2.6, +5.2.
  Typical swing about 3.2%. A fixed 3% cutoff would call 2 of 9 normal days bad.
- Bench, close grip (9): +4.0, -1.3, -0.3, -1.1, +2.7, -0.2, -0.7, -2.9, +1.5.
  Typical swing about 2.2%.

### 4. The check-in rule almost never fires

On every lifting day with a check-in, tiredness and recovery were 0 or 1. The v0 rule
needs 3 or more (or pre-movement soreness 2 or more), so it nearly always guesses
"normal". It cannot beat "always normal" because it is nearly the same guess. Check-ins
exist for 37 of the last 120 days.

## What stays the same

- The question: does the check-in predict a below-usual day?
- Blinding: the result is hidden until the workout is saved.
- Prospective timing: a snapshot after the first working set, or 18 hours after the
  start, does not count.
- Scoring against "always normal" and the recovery shadow capture.
- The trial never changes a workout, weight or plan.

## Part 1: retire v0

- v0 records stay exactly as recorded; nothing is recalculated or deleted.
- New snapshots are recorded as `shared-trial-v1`.
- A v0 snapshot still waiting for its save completes under v0's rule.
- History and the dashboard label v0 "Retired: the matching rule could not score
  changing top sets" and drop its review dates.

## Part 2: v1 scoring

1. **The day's strength:** one estimated max per movement per session, fitted from
   every working set with an RPE (any RPE), using the lift's personal RPE table. This
   is the per-workout estimate the RPE charts page already calculates. Marked top sets
   count like any other rated set. Volume days, heavy days and peaks all count.
2. **Usual:** the middle of that movement's previous three scored sessions within 56
   days. No matching of reps, RPE or exercise position.
3. **Bad-day cutoff:** per movement, 1.5 times that movement's own typical swing over
   its earlier sessions, never below 3%. At today's numbers: squat about 5%, bench
   about 3.3%. Frozen into each snapshot with the table used.
4. **Uncertain:** fewer than three earlier scored sessions in 56 days, no rated working
   sets today, or a missing check-in.
5. Hypertrophy-mode (same-weight first set) snapshots end with v0.

## Part 3: the check-in guess (decided 2026-11-26: personal usual range)

Guess "below usual" when today's tiredness, recovery or that movement's pre-movement
soreness is above Brian's own usual range; otherwise "near usual".

- Usual range per rating: the 10th–90th percentile of that rating over the previous
  84 days, the same method the Fatigue Trend chart uses for the combined score.
  Above usual means above the 90th percentile. Recomputed at each snapshot and frozen
  into it, so it follows changes in how he uses the scale.
- Needs 14 earlier check-ins spanning 28 days; otherwise the guess is "uncertain".
  Pre-movement soreness needs the same coverage for that movement.
- At today's numbers (37 check-ins in 84 days): tiredness 0 ×11, 1 ×19, 2 ×5, 3 ×2;
  recovery 0 ×14, 1 ×17, 2 ×6. Usual is 0–1, so a 2 or more counts as above usual.
- Rejected: fixed thresholds (3+ tiredness/recovery, 2+ soreness). With his ratings
  they almost never fire, so the guess would match "always normal".
- The "check-in only" comparison arm uses the same personal-range rule without the
  lifting history, as in v0.

## Part 4: judging results

- Per movement: 12 eligible predictions with both outcomes seen; review six weeks
  after the first.
- Combined across all movements: the question is about the check-in, so pooling is
  fair. Rough timing at the recent pace: several scored movements a week, so the
  combined score could reach 12 in about 3–6 weeks if check-ins are entered before
  lifting.

## Screens (mockup first)

Text changes on the Log trial panel, Settings trial history and the dashboard: retired
label, v1 cohort names, the combined score. Brian sees a before/after mockup before
any screen changes.

## Not in this plan

- The trend tracker ("Collecting baseline 1/12"). The same per-session estimate would
  fix it; separate decision.
- Using personal RPE tables for loading weights.

## Verification

- Python and rackbook unit tests, every rackbook/tests/*.cjs, Docker build/startup,
  mocked browser checks via tools.preview_app. No real databases.
- New tests: v0 records unchanged; varied top sets and volume-only days score; fewer
  than three earlier sessions stay uncertain; table and cutoff frozen per snapshot;
  combined score counts.
- Update docs/hevy-context.md, rackbook context, release evidence and cutover notes.
- No commit, push or deployment without Brian's go-ahead.
