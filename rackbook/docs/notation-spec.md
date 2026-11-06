# Program Notation Spec (DRAFT v0.1)

Status: **draft for review — no code implements the new parts yet.**
Goal: one defined, program-agnostic notation for entering any training program as text. 5/3/1 is just one program written in it. Everything the parser accepts today stays valid.

Examples for Starr / Bridge-style programs below are **illustrative placeholders to show the notation, not the real prescriptions** of those programs.

---

## 0. The concept, as Claude understands it (2026-10-04; for the user to correct)

1. **A program is text the lifter keeps rewriting.** It says what to do per block, microcycle, day and exercise. It evolves as the lifter learns (e.g. volume cut from 5 to 3 sets in microcycle 2) and may keep evolving, including while a block is running. The text is the source of truth.
2. **A set is prescribed as reps plus a target RPE.** The RPE chart links reps + RPE to a percentage of e1RM, in both directions: plan (e1RM -> weight) and measure (weight + reps + RPE -> e1RM).
3. **Two numbers per lift.** The e1RM is a live estimate from logged sets and is never reduced. The TM is a stored max for the main lifts (squat, bench, deadlift, press): a percentage of an e1RM (e.g. `TM90`: e1RM 200 gives TM 180), updated when a set marked `TS` is logged.
4. **Where a planned weight comes from changes by phase.** Gauge weeks have no plan (weights by feel, RPE recorded) and seed the numbers. Later weeks plan from the TM (microcycle 3 Day 2 is the first, roughly TM x RPE%). A different program may plan from the e1RM instead. Some days may plan from the live e1RM. So the baseline is a per-program/per-block choice, and the exact formula is not settled.
5. **Logging records what actually happened.** Actual weight, reps and RPE (which can differ from target, e.g. 7.5 or 8.5) feed the e1RM. During a session, the next set's weight can be suggested from the updated e1RM; the lifter can always type something else.
6. **Everything else is ordinary.** Exercises without RPE have typed weights (pre-filled from last time). Myo-reps and density blocks are normal logged sets. Cardio is not logged. Weights are plated in kg, shown with lb; e1RM shows in lb. Sessions sync to Hevy. The UI shows when each day and exercise was last done.
7. **Not program-specific.** 5/3/1 pieces (Jokers, BBB, AMRAP anchoring) stay as options. Nothing is removed.

**Not yet known (deliberately not assumed):** the exact TM-to-weight formula and rounding rule; the user's own RPE table; how the next in-session set's e1RM is chosen; which days plan from the TM versus the live e1RM.

**Design consequences of "it keeps evolving":**
- Planning rules are replaceable strategies chosen by program text, not hard-coded paths.
- Planned weights are suggestions by default, so a wrong formula costs little.
- Unknown notation options should be kept and warned about, not rejected, so the notation can grow without breaking old programs.
- Editing a program mid-block must preserve logged history (bookmark E).
- The characterisation tests stay green while rules change.

## 1. Principles

1. **Backward compatible.** Every line that parses today keeps parsing to the same result. New syntax only adds.
2. **One shape per line.** A slot line is `Exercise - set-groups [load-source]`. No program-specific line types.
3. **The notation describes the prescription, not the formulas.** Rules like "how e1RM updates" or "how weight progresses" are named by tags; the math lives in code/config, not in the text.
4. **Pure and testable.** The parser stays pure (no DB, no HTTP). Every construct has a test.
5. **Unambiguous.** Each symbol means one thing. The current grammar breaks this in one place (`@` is RPE in `5@5,6,7` but a percentage in `@.65`); this spec fixes it without breaking old input (section 6).

---

## 2. Document structure

```
# comment (ignored)

{block}.{micro}.{day}[: Label]
Exercise Name - <set-groups> [load-source]
Exercise Name - <set-groups> [load-source]
```

- **Header** `{block}.{micro}.{day}`: three integers. Slots under it belong to that day until the next header. (Today a slot may also sit on the header line; that stays valid.)
- **Optional label** after `:` on a header, e.g. `1.1.1: Heavy`. *(new)*
- **Slot line**: `Exercise - groups [tag]`. Split on the **last** ` - `, so names containing ` - ` work.
- **Blank lines and `#` comments** are ignored.

---

## 3. Set groups

A slot has one or more groups joined by ` / `. Each group expands to one or more sets.

### 3.1 Group forms

| Form | Meaning | Status |
|---|---|---|
| `NxR` | N sets of R reps, no intensity (free) | exists |
| `NxR@I` | N sets of R reps at intensity I | exists (RPE only) |
| `R@I1,I2,I3` | one set per intensity, shared reps | exists (RPE only) |
| `R1@I1,R2@I2,R3@I3` | per-set reps and intensity (wave) | exists (RPE only) |
| `NxRJ +p1,p2,..` | Joker sets, jump percentages | exists |
| `NxR@65%` + load source | N sets of R reps at a percent of the baseline, e.g. `5x10@65% e1RM`. General form, not BBB-specific; the old `NxR @.65 e1RM` is a legacy alias that parses to the same thing | alias exists; `%` form new |

### 3.2 Intensity `I` (what follows `@`)

| Form | Meaning | Status |
|---|---|---|
| `@7`, `@7.5` | target RPE (weight derived from the RPE chart) | exists |
| `@75%` | percentage of the slot's **baseline** (the load source, section 4) | **new** |
| `@100kg`, `@225lb` | absolute weight | **new** |
| `@-10%` | percentage drop from the slot's **top set** (back-off) | **new** |

Rule: a bare number after `@` is RPE; a `%` or unit is explicit. This removes the `@.65` ambiguity.

### 3.3 Modifiers

- Trailing **`+`** on the last intensity = last set is AMRAP (`5@5,6,7+`, `1@85%+`). Unchanged.
- **`J`** marks Joker sets (unchanged).
- **`TS`** (new, chosen by user 2026-10-03) marks the **TM set**: the set whose e1RM becomes the next microcycle's TM. Case-insensitive. Goes after the intensity and after any `+`: `3@8TS`, `1@9+TS`. On a `NxR@ITS` group it marks the group's last set. At most one `TS` per slot (parse error if more). No `TS` means the TM does not change. Distinct from the `TM90` source tag.
- **Top set**: the heaviest non-Joker set is the "top set" automatically. `@-10%` back-offs are relative to it. *(new)*

---

## 4. Load source (the trailing tag)

Where the slot's baseline weight comes from. One tag per slot, at the end of the last group.

| Tag | Baseline | Status |
|---|---|---|
| `TM90` | training max x 0.90 | exists |
| `e1RM` | latest e1RM for the exercise | exists |
| `DDP` / `DDP+2.5` | last session's weight, plus increment | exists (stub) |
| *(none)* | free logging — no computed weight | exists |
| `LAST` | last session's top set weight (no increment) | **new, proposed** |

Percent intensities (`@75%`) multiply the baseline. RPE intensities use the baseline as an e1RM and look the percentage up in the RPE chart.

---

## 5. Rules attached to a slot (OPEN — needs your input)

Two things are not expressible yet: **how e1RM updates after logging** and **how weight progresses**. Proposed syntax: trailing `[key=value]` options, so the set groups stay clean.

```
Squat - 5@75%,80%,85%+ TM90 [e1rm=amrap]
Squat - 1@8 / 3x5@-10% e1RM [e1rm=rpe]
Squat - 5x5 LAST [inc=2.5]
```

Candidate keys (all optional, with defaults chosen so existing programs behave exactly as today):

| Key | Values | Default |
|---|---|---|
| `e1rm` | `amrap` (Epley, Joker band), `rpe` (any set with reps + RPE, via chart), `none` | `amrap` where an AMRAP exists, else `none` |
| `inc` | kg added to the baseline per session/week on success | none |
| `round` | rounding step in kg for this exercise (microloading) | `2.5` |
| `joker_band` | ±fraction | `0.05` |

I deliberately have **not** fixed the progression semantics (per session vs. per microcycle, on-success vs. always) — those are the rules I still need to hear from you.

---

## 6. Compatibility map (old -> canonical)

The parser accepts both; reconstruction (editor round-trip) emits the canonical form.

| Old | Canonical |
|---|---|
| `5x10 @.65 e1RM` | `5x10@65% e1RM` (same meaning; legacy alias only, no separate BBB concept in the notation. Internally the `bbb_pct` fields fold into the general percent-of-baseline path, covered by the characterisation tests) |
| `5@5,6,7+` | unchanged |
| `5@5,3@6,1@7+` | unchanged |
| `3x1J +10,15,20` | unchanged |
| `TM90`, `e1RM`, `DDP+2.5` | unchanged |

---

## 7. Examples

**5/3/1 BBB (all valid today)**
```
1.1.1
Squat - 5@5,6,7+ / 3x1J +10,15,20 TM90
Squat - 5x10 @.65 e1RM
Lying Leg Curl - 5x10
```

**Ramped 5x5 with a weekly increment (illustrative)**
```
1.1.1: Heavy
Squat - 5@50%,62%,75%,87%,100% LAST [inc=2.5]
1.1.2: Light
Squat - 4@50%,62%,75%,80% LAST
```

**RPE top set + back-offs (illustrative)**
```
1.1.1
Squat - 1@8 / 3x5@-10% e1RM [e1rm=rpe]
```

---

## 8. Decisions made

1. **Ramps / intensity style (2026-10-03):** RPE is the primary way to write intensity, one RPE per set: `5@6,7,8` = three sets of 5 at RPE 6, 7, 8 (Starr day 1). `3x5@7` (same RPE every set) also works. Percent and absolute-weight forms stay in the spec as optional extras.
2a. **Within-session re-planning (2026-10-03):** for RPE slots, each logged set (weight, reps, actual RPE) updates the e1RM, and the *next set's* planned weight is recomputed from the updated e1RM at its own target RPE. NOT implemented today: session weights are currently fixed at session load. Needs a frontend recompute and a rule for which sets count (e.g. ignore a set with no actual RPE).
2. **e1RM update (2026-10-03):** no stated preference, so all four behaviours stay available per slot (`amrap`, `rpe`, fixed increment, manual). Defaults: slots with an AMRAP set keep `amrap` (5/3/1 unchanged); RPE slots default to `rpe`; free slots do nothing.

3. **Units (2026-10-03):** weights are kg (plates are kg) and stored as kg, rounded to 2.5 kg. Every weight is shown with its lb equivalent beside it; e1RM is shown in lb (matches the user's spreadsheet). Text may use `kg` or `lb` suffixes; a bare number is kg.
4. **Real-world shape (from user's spreadsheet, 2026-10-03):** a lift is typically 5 sets of 5 where the first sets are a ramp with no RPE (weight only) and only the last 1-2 sets carry a target RPE (e.g. 3 ramp sets, then RPE 7 and 8). e1RM is computed on the RPE sets only. This already parses today as `3x5 / 5@7,8 e1RM` (free group + RPE group).

5. **Current program shape (user's Micro 3 sheet, 2026-10-03):** main lifts and variations are RPE-prescribed, each with its own e1RM: `5@6,7,8`, `8@5,6,7`, `5@6,3@7,1@8`, and top sets plus a back-off (`5@6,5@7,3@8,8@6`). All of these parse today. Free sets (e.g. Pendlay row `4x5`) have typed weights, pre-filled from last session (default, not yet confirmed). Actual RPE is logged and can differ from plan (7.5, 8.5). A TM per main lift (Squat/Bench/Deadlift/Press) is shown at the top of the microcycle.
6. **Does NOT parse today (corrected by user, 2026-10-03):** GPP day comes from the BBM Bridge template: 30 min steady-state cardio, modality varies (row or walk), so it is a duration, not sets x reps. Dips and Incline DB Curl are either myo-reps or density blocks (5 min, 6-10 reps or failure). Pull-ups are `3x5 / 1x3 / 1x8` (parses today as groups) and follow the "BS Method" = Bill Starr 5x5 shape (ramp of 5s, a heavier set of 3, a lighter back-off set of 8). The same shape appears in the RPE lifts as `5@6,5@7,3@8,8@6`. The weekly progression rule is still unknown. Bare `TM` (no number) is also invalid; today the tag is `TM90`.

7. **TM progression (user, 2026-10-03):** the progression is the TM update. The top set of 3 from Day 3 sets next microcycle's TM; for the 5/3/1+ lift the Day 3 AMRAP does the same. No fixed weekly increment is used. SUPERSEDED by decision 10: the percentage comes from the TM tag, not a per-lift factor. The sheet shows Deadlift day-3 e1RM 407 vs TM 405, but Squat 357 vs TM 316 and Bench 276 vs TM 257; those TMs may predate this day.
9. **Which set drives the TM (user, 2026-10-03):** Squat and Bench: the fixed top set of 3 at RPE 8 (e1RM via the RPE chart). Deadlift: the Day 3 AMRAP, run up to RPE 9, so the reps achieved decide the number (`1@9+`). User then pointed out this will not always be the case, so the TM set is designated explicitly with a `TS` marker (section 3.3), not inferred.

8. **Pull-up progression (user, 2026-10-03):** linear, small (microloaded) weight added each week to the Starr-shape sets `3x5 / 1x3 / 1x8`. Uses the `[inc=...]` option. Consequence: the global 2.5 kg rounding rule must become a per-exercise rounding step (default 2.5 kg, overridable to e.g. 0.5 or 1.0 kg for microloaded lifts), otherwise small increments round away.

10. **TM definition (user, 2026-10-03):** a TM is a max that is a percentage reduction of the e1RM. e1RM 200 with `TM90` gives TM 180. The e1RM itself is never reduced or overwritten by this; the TM is a separate number. TMs apply to main movements only; every other exercise (variations, accessories) plans from its own e1RM history. Where the percentage lives (tag vs block) and whether the TM is frozen at the `TS` set or recomputed live is part of bookmark A.
11. **Own history (user, 2026-10-03):** each exercise, including variations, plans from its own e1RM history, not its parent lift's.
12. **No real data exists (user, 2026-10-03):** the app has never been used for a real session, so there is nothing to migrate; the schema may change freely.
13. **Non-set lines (user, 2026-10-03):** cardio is not logged and is out of scope for now. Myo-reps and density blocks are logged like any other exercise (normal weight/reps sets, open-ended count). Proposed syntax: `free` = no prescribed set count, optional `[note]` text shown on the day, e.g. `Dips - free [5 min density block, 6-10 reps or failure]`. The user's own log shorthand for a myo-rep set is weight-first: `20x15 20x5 20x5x3 20x3x2 20x2` (weight x reps [x sets]); note this is the opposite order to the prescription form `NxR` (sets x reps).
14. **Build order (delegated to Claude, 2026-10-03):** (1) parser changes, (2) session engine (e1RM from any RPE set, in-session re-planning, TM), (3) UI, (4) schema cleanup and rename. Spec review before each step, one small commit per change.

15. **Round 3 answers (user, 2026-10-03):** quick-entry log shorthand wanted, but after the session engine (bookmark C). Dates stay out of the program text; the UI should instead show "last done" dates from the logged_at timestamp on each logged set (not shown anywhere today). Day labels (`1.3.4: Label`) stay optional and low priority. Cross-day references: not needed now, maybe in future, deferred. Project rename: at the end of step 4.
16. **RPE chart check (2026-10-03):** the app's chart (`data/rpe_chart.csv`) with `e1RM = weight / chart% x 2.2046 lb` reproduces 20 of 26 e1RMs in the user's sheet within 1.5 lb; the other 6 differ by 1.6-2.6 lb (e.g. squat 132.5 kg x5 @8: app 351.9, sheet 354). The sheet probably uses a slightly different table.

17. **TM in the current program (user, 2026-10-04, CORRECTED):** TMs exist for Squat, Bench, Deadlift and Press, and next week's numbers ARE based off the TM (Claude's earlier "tracking only" reading was wrong). A TM changes when a set marked `TS` is logged. The user may later run a program that plans from the e1RM instead of a TM, so the baseline source (TM or e1RM) must be selectable per program/block; bookmark A is a real requirement, not a future nicety. Exactly how a TM becomes a set's weight is NOT yet understood (see bookmark D).
18. **Last-done layout (user, 2026-10-04):** option C, the day shows "last done <date>" and each exercise shows last time's weight and RPE.
19. **RPE history (user, 2026-10-04):** when the program started, weights were chosen by feel and RPE was only documented, so early sheet e1RMs are readouts of what was lifted, not plans. The user has their own RPE table and will provide it; load it in place of `data/rpe_chart.csv`.

20. **Gauge week (user, 2026-10-04):** after a long layoff the first microcycle's numbers were "gauge sets": weights chosen by feel with an RPE logged, used to find the starting e1RMs/TMs. Notation needs no new syntax for this: RPE sets with no load-source tag (`5@6,7,8`) are free sets with an RPE target, so the app plans no weight and the logged weight + reps + RPE produce the e1RM. Later microcycles plan from the TM. (How the TM becomes a weight is still bookmark D.)

21. **The program evolves mid-block (user, 2026-10-04):** the current program is a work in progress. Volume was too fatiguing, so from microcycle 2 Day 1 was cut to 3x5 (Pendlay rows dropped by one set) while Days 2 and 3 stayed the same. Consequences: (a) volume can differ per microcycle, which the `block.micro.day` header already expresses; (b) the user must be able to edit the program text while a block is active. TODAY THIS IS NOT POSSIBLE: `POST /programs/{id}/import` returns 400 while the program has an active block, because import deletes and re-inserts every slot, which would orphan logged history. (c) Because the program is in flux, the Micro 3 weights are weak evidence of a fixed formula; bookmark D's reverse-engineering should not be treated as settled.

22. **Architecture (user, 2026-10-05):** this app is a FRONT END for Hevy: a program builder, plus a mobile-friendly logging screen that recalculates planned weights live as sets are entered (what the user's spreadsheet does, without the spreadsheet's mobile awkwardness), and it pushes finished workouts to Hevy. Hevy is the backend and system of record for exercises (every exercise must come from Hevy's templates, 100% tie-in) and for workout history. Local storage keeps only what Hevy cannot hold: program text, TM/e1RM state, the RPE table, in-progress drafts, and RPE values Hevy cannot store (below 6, or 6.5). An AI-plus-MCP workflow without this app was considered and rejected because it cannot recalculate live. See `docs/hevy-api.md`.
23. **The spreadsheet is the reference implementation (user, 2026-10-05):** its formulas define the live calculation. The plan is to read the formulas directly from an exported .xlsx instead of reverse-engineering from screenshots; this resolves bookmarks B and D.
24. **Build order (updated 2026-10-05):** 0) fix the Hevy write-back to match the spec and make exercise matching strict, 1) parser changes, 2) calculation engine matching the spreadsheet, 3) mobile UI with live recalculation, 4) schema cleanup and rename.

25. **TM percentage (user, 2026-10-08):** a TM is the e1RM of the top set times a percentage. The default is 95% and the user can change it. This matches the user's Hevy history (4 of 4 lifts at about 0.95 of the last microcycle's top-set e1RM). It supersedes the earlier `TM90` example; if a percentage is written next to the `TS` marker it overrides the default (`TS` = 95%, `TS90` = 90%). e1RM and TM are separate numbers: the e1RM is never reduced, and the RPE table converts reps and RPE into a percentage of an e1RM, not of a TM. e1RM and TM are calculated by this app from the user's own RPE table and top set, never from Hevy's displayed e1RM. How a TM becomes a planned set weight is still undecided.

## Bookmarked discussions (not decided; come back to these)

- **E. Editing a program while a block is active.** Needs edit-in-place for slots (match by day + exercise) that preserves slot ids and logged history, or versioning. Design before the schema work in step 4.

- **A. TM / block-level baseline.** How to say "this whole block plans from the TM". Candidate: a block line `1 [base=TM90]` with slot tags overriding. Also unresolved: where the percentage lives (tag vs block), whether the TM is a snapshot frozen at the `TS` set or recomputed live, and whether a TM change applies from the next microcycle only.
- **B. In-session e1RM rule.** Which e1RM feeds the next set in a session (latest set, average, highest) and what is stored at the end. User wants a detailed answer here; the sheet shows e1RMs 343, 352, 354 across a 6/7/8 RPE ramp, each next set planned from the one before.
- **D. How the user actually turns TM + RPE into a set weight (BLOCKING on the user's RPE table).** Correction (user, 2026-10-04): nothing was TM-based until microcycle 3 Day 2, which is not completed yet, so the Day 2 and Day 3 rows in the sheet are PLANNED weights, not logs. The earlier `(TM / 0.9) x chart%` idea came from Day 1 numbers that were not TM-based and is WITHDRAWN. Test of `TM x chart%` against the planned rows (app chart): HB squat Day 2 matches exactly (95 / 97.5 / 102.5 kg, rounding unclear); Deadlift Day 3 is 0-2.5 kg above it; Overhead press Day 2 is 0-2.7 kg above it (plan 37.5 / 40 / 42.5 vs 37.1 / 38.2 / 39.8). Most likely the sheet's RPE table differs slightly from the app's. Next step: load the user's table, then re-test. Also open: Day 3 squat and bench plans (e1RM about 357 and 278) sit well above their TMs (316, 257); they may plan from Day 1's live e1RM, not the TM.
- **C. Quick-entry log shorthand.** Whether the workout UI should accept `weight x reps [x sets]` strings (see decision 13).

## 9. Open decisions

1. **Percent-of-baseline vs. percent-of-top-set** for ramps. The Starr example above treats the ramp as percentages of the top set's weight, which `LAST` supplies. Is that how you think about it?
2. **Light/medium days as a function of the heavy day** (e.g. 80% of Monday's top set). Needs a cross-day reference (`@80% of 1.1.1`?) or can the numbers just be typed per day?
3. **Progression semantics** for `inc` and `e1rm=rpe`: your rules.
4. **Units**: the DB stores kg. Accept `lb` in the text and convert, or kg only?
5. **Day label syntax** (`1.1.1: Heavy`) — fine, or different?
