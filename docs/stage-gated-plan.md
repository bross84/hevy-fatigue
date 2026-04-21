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
4. Stage 3
5. Stage 5
6. Stage 6
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

## Stage 3 - Stress Pathway Dispatcher

Goal: Route stress computation by modality.

Pathways:
- Pathway 1: Strength/Hypertrophy via existing per-set stress math.
- Pathway 2: Conditioning using normalized `sRPE × duration` with pattern distribution.
- Pathway 3: Cardio using normalized `sRPE × duration` without pattern distribution.

Scope note:
- Keep stress-lock behavior unchanged except for improved stress inputs.

Gate tests:
- All pathways produce expected stress in controlled fixtures.

## Stage 5 - Pattern EWMA Tracking

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

## Stage 6 - Recommendation Engine v2

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
