# Stage-Gated Implementation Plan

This document locks implementation to strict stage gates and dependency order.

## Execution Rules

1. Only implement one stage at a time.
2. Do not begin the next stage until all tests for the current stage pass.
3. Keep changes scoped to files required by the active stage.
4. Preserve existing API contracts unless a stage explicitly changes them.
5. Use compute-on-demand where chosen, so corrected mappings update historical outputs retroactively.

## Dependency Order

1. Stage 1 (COMPLETE)
2. Stage 2 (COMPLETE)
3. Stage 4 (COMPLETE)
4. Stage 3 (COMPLETE)
5. Stage 5 (COMPLETE)
6. Stage 6 (COMPLETE)
7. Stage 7

## Stage 1 - Full Body Classification Baseline - COMPLETE


Goal: Reclassify full-body movements using existing percentage fields.

Scope:
- Update classifier rules so `thruster`, `box jump`, and `burpee` are not conditioning.
- Map those to 0.30 / 0.30 / 0.20 / 0.20 using existing percentage columns.
- No schema changes.

Gate tests:
- These exercises classify as non-conditioning.
- Pattern stress reflects split distribution.

### Stage 1 Completion Summary (for review before Stage 2)

Status: COMPLETE and committed on `v2`.

Implemented changes:
- Reclassified `thruster`, `box jump`, and `burpee` from conditioning to full-body mixed patterns.
- Added explicit full-body mappings for `burpee`, `burpees`, `thruster`, `barbell thruster`, `dumbbell thruster`, `box jump`, and `box jumps`.
- Applied split values: `pct_quad_dom=0.30`, `pct_posterior=0.30`, `pct_upper_push=0.20`, `pct_upper_pull=0.20`, `is_conditioning=False`.
- Removed `burpee`, `thruster`, and `box jump` from conditioning explicit mappings.
- Removed `burpee`, `thruster`, and `box jump` from `CONDITIONING_KEYWORDS` to prevent fallback misclassification.

Gate evidence (passed):
- Core exercises (`thruster`, `box jump`, `burpee`) classify as non-conditioning with 30/30/20/20 distribution.
- Variants (`barbell thruster`, `dumbbell thruster`, `box jumps`, `burpees`) classify with the same distribution.
- True conditioning examples (`assault bike`, `jump rope`, `treadmill`, `amrap workout`, `metcon`) remain conditioning.
- Assertion suite completed with all checks passing.

Files changed in Stage 1:
- `exercise_classifier.py`
- `docs/stage-gated-plan.md`

## Stage 2 - Session Model + Modality Verification - COMPLETE

Goal: Introduce session-level records with verification flow.

Schema (`workout_sessions`):
- `hevy_workout_id` (unique)
- `workout_date`
- `workout_title`
- `start_time`
- `end_time`
- `duration_minutes`
- `modality` (`strength|hypertrophy|conditioning|cardio`)
- `modality_confidence`
- `verification_status` (`pending|verified`)
- `verified_at`
- `srpe` (nullable)
- `created_at`
- `updated_at`

Keying and linkage:
- Use `hevy_workout_id` as the session key.
- Link set rows via existing `workout_logs.workout_id`.
- No `session_id` backfill in this phase.

Verification policy:
- Strength/Hypertrophy: auto-verify only when confidence >= 0.80, else pending.
- Conditioning/Cardio: never auto-verify, always pending for human confirmation + required sRPE.
- Pre-select detected modality in UI to reduce friction.

Duration safety guard:
- If `start_time` or `end_time` is null, set `duration_minutes = null`, force `pending`, and prompt manual duration.
- If computed duration <= 0 or > 480 minutes, set `duration_minutes = null` and force `pending`.

Gate tests:
- Pending/verified flows work.
- Sessions persist with durations where valid.
- Workout rows remain linked by `workout_id`.

### Stage 2 Completion Summary (for review before Stage 4)

Status: COMPLETE and ready for commit on `v2`.

Implemented changes:
- Added `WorkoutSession` ORM model and `workout_sessions` table schema in `database.py`.
- Extended importer sync in `importer.py` to upsert session rows keyed by `hevy_workout_id`.
- Added duration parsing and duration safety guard logic:
	- missing `start_time`/`end_time` -> `duration_minutes = null`
	- computed duration `<= 0` or `> 480` -> `duration_minutes = null`
- Added modality inference and confidence assignment in importer.
- Enforced Stage 2 auto-verify policy at import time:
	- `strength`/`hypertrophy` auto-verify only when confidence `>= 0.80` and duration valid
	- `conditioning`/`cardio` never auto-verify
- Added verification API endpoints in `main.py`:
	- `GET /api/workout-sessions`
	- `GET /api/workout-sessions/pending`
	- `PUT /api/workout-sessions/{hevy_workout_id}/verify`
	- `PUT /api/workout-sessions/{hevy_workout_id}/status`
- Added server-side verification guards in `main.py`:
	- verified status requires valid `duration_minutes` (1..480)
	- `conditioning`/`cardio` require `srpe` before verification

Gate evidence (passed):
- Duration guard behavior validated for null, invalid, and valid durations.
- Modality-specific auto-verify behavior validated (`strength`/`hypertrophy` threshold, no auto-verify for `conditioning`/`cardio`).
- Pending queue retrieval validated via session endpoints.
- Conditioning verification without `srpe` correctly rejected.
- Conditioning verification with valid `srpe` correctly accepted.
- Manual status transitions (`pending` <-> `verified`) validated.

Files changed in Stage 2:
- `database.py`
- `importer.py`
- `main.py`

## Stage 4 - sRPE Collection - COMPLETE

Goal: Capture session sRPE required for conditioning/cardio pathways.

Scope:
- Add UI/API to collect and edit `workout_sessions.srpe`.
- Conditioning/cardio sessions cannot be marked verified without valid sRPE and valid duration.

Gate tests:
- sRPE can be captured, edited, and retrieved per session.

### Stage 4 Completion Summary (for review before Stage 3)

Status: COMPLETE and committed on `v2`.

Implemented changes:
- Added Session Verification Queue card to the Workouts tab in `static/index.html`.
- `loadSessionVerificationQueue()`: fetches `GET /api/workout-sessions/pending?days=45` and renders one card per session with modality select, duration input, and conditional sRPE input.
- `_toggleSessionSrpe(card)`: shows/hides the sRPE field based on selected modality — visible only for `conditioning` and `cardio`.
- `verifySessionFromCard(btn)`: validates inputs client-side (duration 1–480, sRPE required for conditioning/cardio), sends `PUT /api/workout-sessions/{id}/verify`, refreshes queue on success.
- `_modalityOption()` helper for select rendering.
- `loadWorkouts()` now calls `loadSessionVerificationQueue()` on entry.
- CSS added: `.verify-list`, `.verify-item`, `.verify-head`, `.verify-title`, `.verify-meta`, `.verify-fields`, `.verify-field`, `.verify-status`.

Gate evidence (passed — `stage4_gate.py`):
- Conditioning verify without sRPE correctly rejected.
- Cardio verify without sRPE correctly rejected.
- Conditioning verify with `sRPE=7.5` accepted; value persisted and status set to `verified`.
- sRPE retrievable via `GET /api/workout-sessions`.
- sRPE editable (7.5 → 8.0) via status endpoint.
- Strength verify without sRPE accepted.
- Verify without duration correctly rejected.

Files changed in Stage 4:
- `static/index.html`

## Stage 3 - Stress Pathway Dispatcher - COMPLETE

Goal: Route stress computation by modality.

Pathways:
- Pathway 1: Strength/Hypertrophy via existing per-set stress math.
- Pathway 2: Conditioning using normalized `sRPE × duration` with pattern distribution.
- Pathway 3: Cardio using normalized `sRPE × duration` without pattern distribution.

Scope note:
- Keep stress-lock behavior unchanged except for improved stress inputs.

Gate tests:
- All pathways produce expected stress in controlled fixtures.

### Stage 3 Completion Summary (for review before Stage 5)

Status: COMPLETE and ready for commit on `v2`.

Implemented changes:
- Added `_CONDITIONING_SCALING_DEFAULT = 29.0` constant in `main.py`.
- Added `_get_conditioning_scaling_factor(db)` helper — reads `conditioning_stress_scaling_factor` from `app_settings`, falls back to 29 if absent or invalid.
- Extended `calculate_stress_scores(target_date, db)` with two new pathways after the existing Pathway 1 logic:
  - **Pathway 2 (conditioning):** queries `WorkoutSession` rows for the date where `modality='conditioning'`, `verification_status='verified'`, `srpe` and `duration_minutes` are not null. Computes `raw = (srpe × duration_minutes) / scaling_factor`. Derives central/peripheral weights from `ExerciseMapping` averages across the session's `WorkoutLog` rows: `central_weight = Σ avg_pct_i²`, `peripheral_weight = Σ avg_pct_i`. Falls back to equal 4-pattern distribution (0.25 each) if no mappings found.
  - **Pathway 3 (cardio):** same `raw` formula. Flat 30% central / 70% peripheral split. No pattern distribution.
  - Unverified or missing-sRPE sessions contribute zero stress (silent, no error).
  - Multiple sessions on the same date are summed.
- `_compute_training_load` unchanged — benefits automatically from the improved `calculate_stress_scores` return values.

Gate evidence (passed — `stage3_gate.py`):
- Pathway 1: strength set produces non-zero central and peripheral stress (3.444 / 4.150).
- Pathway 2 (unverified): pending conditioning session adds zero stress.
- Pathway 2 (verified): conditioning central Δ=7.169 and peripheral Δ=10.862 match formula exactly.
- Pathway 3: cardio central Δ=3.725 and peripheral Δ=8.690 match 30/70 split exactly.
- Custom `scaling_factor=10` overrides default 29 and produces proportionally higher stress.
- Multi-session same day: second cardio session stacks correctly onto the daily total.

Files changed in Stage 3:
- `main.py`

## Stage 5 - Pattern EWMA Tracking

## Stage 5 - Pattern EWMA Tracking - COMPLETE

Goal: Maintain pattern ATL/CTL/TSB for knee/hip/push/pull.
Scope:
- Extend training-load loop with parallel EWMAs using existing `k_atl` and `k_ctl`.
- Compute on demand and return via `/api/training-load`.
- Do not create a materialized pattern table in this phase.
- Unassigned exercises contribute to total stress, not to pattern buckets.

Gate tests:
- Squat-heavy day elevates knee ATL.
- Deadlift day elevates hip ATL.
- Thruster session distributes to all four pattern ATLs.
- Pure cardio leaves pattern ATLs unchanged.
- Pattern values are returned per day.

### Stage 5 Completion Summary (for review before Stage 6)

Status: COMPLETE and ready for commit on `v2`.

Implemented changes:
- Extended `calculate_stress_scores(target_date, db)` to return four additional keys: `knee`, `hip`, `push`, `pull`.
	- **Pathway 1 (strength):** for each working set, accumulates `(central_i + peripheral_i) × pct_p` into the corresponding pattern bucket. `ExerciseMapping` pct values fetched in a single query per date.
	- **Pathway 2 (conditioning):** distributes `raw × avg_pct_p` to each pattern bucket using the same `ExerciseMapping` averages already computed for central/peripheral weights. Fallback to equal 0.25 distribution if no mappings found.
	- **Pathway 3 (cardio):** contributes zero to all four pattern buckets.
- Extended `_compute_training_load(days, db)` to run four parallel EWMAs (knee/hip/push/pull) using the same `k_atl` and `k_ctl` as the main EWMA. Pattern stress is sourced from `calculate_stress_scores` results without any additional DB queries. Each history item now includes `"pattern_loads": {"knee": {atl, ctl, tsb}, ...}`.
- Extended `GET /api/training-load` response: `today.pattern_loads` contains the last history item's pattern ATL/CTL/TSB values.
- No new database table. All pattern history is computed on demand — correcting an `ExerciseMapping` immediately changes retroactive pattern output.

Gate evidence (passed — `stage5_gate.py`):
- Gate 1: Squat day (quad=0.80) → knee=6.076, push=0.190, pull=0.190 (knee dominates).
- Gate 2: Deadlift day (post=0.85) → hip=4.219 dominates over knee=0.248.
- Gate 3: Thruster conditioning (30/30/20/20) → knee=2.483, hip=2.483, push=1.655, pull=1.655 matching `raw × pct` exactly.
- Gate 4: Pure cardio → knee=hip=push=pull=0.000, central/peripheral still non-zero.
- Gate 5: `_compute_training_load` history items contain `pattern_loads` with `atl`/`ctl`/`tsb` for all four patterns.
- Gate 6 (compute-on-demand): Changing squat mapping from quad=0.80 to quad=0.10 instantly changed knee 6.076 → 0.759 and hip rose to 6.455 — no recompute step required.

Files changed in Stage 5:
- `main.py`

## Stage 6 - Recommendation Engine v2 - COMPLETE

Goal: Add pattern-aware recommendations while preserving Layer 1 fatigue tiers.

Scope:
- Keep existing fatigue-tier mapping (Layer 1).
- Add Layer 2 analysis from per-pattern ATL/CTL and same-day soreness fields.
- Add output at `/api/training-load -> today.recommendation_v2`.

Defaults:
- `combined_signal > 0.75` -> stressed
- `0.50 <= combined_signal <= 0.75` -> neutral
- `combined_signal < 0.50` -> available

Other requirements:
- Persist threshold values in calibration settings for future user tuning.
- Include edge handling when pattern CTL is zero.
- Reasoning string must name specific stressed and available patterns when present.

Gate tests:
- JSON is complete and valid for rest-day, all-fresh, single-pattern stress, and all-stressed cases.

### Stage 6 Completion Summary (for review before Stage 7)

Status: COMPLETE and ready for commit on `v2`.

Implemented changes:
- Extended calibration settings model and storage in `main.py` with persisted Stage 6 thresholds:
	- `v2_threshold_stressed` (default `0.75`)
	- `v2_threshold_neutral` (default `0.50`)
	- Stored in `app_settings` as `fatigue_v2_threshold_stressed` / `fatigue_v2_threshold_neutral`.
- Added Stage 6 recommendation engine helpers in `main.py`:
	- `_resolve_v2_thresholds(calibration)`
	- `_pattern_soreness_signals(checkin)`
	- `_pattern_load_signal(atl, ctl)` with explicit CTL=0 edge handling
	- `_state_from_signal(signal, thresholds)`
	- `_build_recommendation_v2(today_pattern_loads, checkin, calibration)`
- Added `today.recommendation_v2` to `/api/training-load` response with:
	- overall `status` and `combined_signal`
	- active v2 `thresholds`
	- per-pattern (`knee`/`hip`/`push`/`pull`) ATL/CTL/TSB + load/soreness/combined signals + state
	- reasoning string constrained to model-honest pattern language
- Kept Layer 1 behavior unchanged (`fatigue_score`, `recommendation_adjusted`, and legacy fields are preserved).

Reasoning language constraints enforced:
- Uses only pattern-level claims such as:
	- `[Pattern] stress is elevated`
	- `[Pattern] load is high relative to baseline`
	- `[Pattern] is fresh / available`
	- `Overall fatigue is elevated`
- Avoids any pattern-level references to CNS/central or muscular/peripheral claims.

Gate evidence (passed — `stage6_gate.py`):
- Rest-day fixture returns valid JSON and all patterns available.
- All-fresh fixture returns valid JSON with available pattern states.
- Single-pattern stress fixture marks the stressed pattern correctly and names it in reasoning.
- All-stressed fixture marks all patterns stressed and includes overall-elevated reasoning.
- V2 thresholds persist correctly via calibration save/get flow.
- `/api/training-load` includes complete `today.recommendation_v2` payload.

Files changed in Stage 6:
- `main.py`

## Stage 7 - Dashboard UI Restructure

Goal: Present recommendation output clearly with Today-first UX.

Scope:
- Keep existing custom CSS system (no Tailwind migration in this pass).
- Default landing view is Today.
- Today: fatigue score, tier, reasoning, soreness/pattern status, check-in status, pending verification badge, modality CTA.
- Today state machine: after submit, replace editable form with read-only status panel; restore form on edit/delete.
- Trend: ATL/CTL/TSB chart + recommendation bands + range selector (6w/3m/6m), plus per-pattern ATL chart.
- Move existing stress chart to Trend view.
- Promote Workouts tab into Session Log with expandable session diagnostics.

Gate tests:
- Today fallback states render correctly.
- Trend charts handle low-data windows (<7 days) without breaking.
- Session log handles missing RPE gracefully.
- App loads to Today by default and all views are navigable.

## Decisions Locked

- Full-body via existing percentage fields (no `is_full_body` column).
- Primary modality approximation for mixed sessions in this phase.
- Compute-on-demand pattern EWMA and retroactive correction behavior.
- Extend `/api/training-load` instead of adding a separate recommendation endpoint.
- Strict stage gates with required pass criteria before progression.
- Local DB reset/reimport is acceptable during migration and validation.
