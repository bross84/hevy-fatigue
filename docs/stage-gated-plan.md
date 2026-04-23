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
- Replace free-text modality reasoning in `recommendation_v2` with TSB-driven training state descriptors.
- Add per-pattern `days_since_loaded` and `dots_filled` (1..5) display primitives.
- Keep `recommendation_adjusted` unchanged for backward compatibility.
- No changes to ATL/CTL/TSB math, pattern signal math, combined-signal math, or fatigue-score math.

Gate tests:
- TSB state mapping is correct for +10, +5, -2, -7, and -15 fixtures.
- Fatigue-tier mapping is correct for 8.5, 5.0, and 2.0 fixtures.
- Dot mapping is correct (0.91 -> 5, 0.28 -> 1).
- Pattern never-loaded path returns `days_since_loaded = None` without crash.
- TSB thresholds are readable from `app_settings` with seed defaults when missing.
- `recommendation_adjusted` remains present and unchanged.
- Full payload is well formed across edge cases, including no workout data and no check-in.

### Stage 6 Completion Summary (for review before Stage 7)

Status: COMPLETE and ready for commit on `v2`.

Implemented changes:
- Extended calibration settings model and storage in `main.py` with persisted Stage 6 thresholds:
	- `v2_threshold_stressed` (default `0.75`)
	- `v2_threshold_neutral` (default `0.50`)
	- `tsb_threshold_underloaded` (default `8`)
	- `tsb_threshold_slightly_fresh` (default `3`)
	- `tsb_threshold_balanced` (default `-5`)
	- `tsb_threshold_slightly_fatigued` (default `-10`)
	- Stored in `app_settings` as `fatigue_v2_threshold_stressed` / `fatigue_v2_threshold_neutral`.
	- Stored in `app_settings` as `tsb_threshold_underloaded`, `tsb_threshold_slightly_fresh`, `tsb_threshold_balanced`, `tsb_threshold_slightly_fatigued`.
- Added Stage 6 recommendation engine helpers in `main.py`:
	- `_resolve_v2_thresholds(calibration)`
	- `_resolve_tsb_state_thresholds(calibration)`
	- `_resolve_training_state(tsb, tsb_thresholds)`
	- `_resolve_fatigue_tier(fatigue_score)`
	- `_dots_filled(combined_signal)`
	- `_pattern_last_loaded_dates(db, today)`
	- `_days_since_loaded(pattern, last_loaded_dates, today)`
	- `_pattern_soreness_signals(checkin)`
	- `_pattern_load_signal(atl, ctl)` with explicit CTL=0 edge handling
	- `_state_from_signal(signal, thresholds)`
	- `_build_recommendation_v2(...)` reworked to return TSB-state payload shape.
- Added `today.recommendation_v2` to `/api/training-load` response with:
	- `training_state`, `training_state_label`, `training_state_detail`
	- `tsb`, `fatigue_score`, `fatigue_tier`, `fatigue_tier_detail`
	- `pattern_status` per pattern with `status`, `stress_level_label`, `combined_signal`, `days_since_loaded`, `dots_filled`, `dots_total`
- Removed from `recommendation_v2`:
	- `suggested_modality`, `reasoning`, `rest_day_recommended`, `primary_stress_driver`, `primary_stress_driver_label`, `available_patterns`, `stressed_patterns`
- Kept Layer 1 behavior unchanged (`fatigue_score`, `recommendation_adjusted`, and legacy fields are preserved).

Gate evidence (passed — `stage6_rework_gate.py`):
- TSB state mapping validated for +10, +5, -2, -7, and -15.
- Fatigue-tier mapping validated for 8.5 -> High, 5.0 -> Moderate, 2.0 -> Low.
- Dot mapping validated for 0.91 -> 5 and 0.28 -> 1.
- Never-loaded pattern path validated (`days_since_loaded = None`, no crash).
- Seed-default fallback for all TSB thresholds validated when settings are missing.
- `recommendation_adjusted` compatibility validated.
- `recommendation_v2` payload shape validated and removed fields confirmed absent.

Files changed in Stage 6:
- `main.py`

## Stage 7 - Dashboard UI Restructure (Split Delivery)

Goal: Present recommendation output clearly with Today-first UX.

Scope:
- Keep existing custom CSS system (no Tailwind migration in this pass).

### Stage 7.1 - Today View (COMPLETE)

Goal:
- Build Today as default landing view with one primary data fetch to `/api/training-load` plus one pending-session fetch for badge count.

Scope:
- Information-only Today summary (no modality recommendation CTA in this slice).
- Four-section layout:
	- Training State Header
	- Pattern Stress Grid
	- ATL/CTL/TSB Summary with plain-language labels + tooltips
	- Status Footer (check-in, pending sessions, last sync)
- Required fallback behavior:
	- no check-in
	- no workout data
	- missing `recommendation_v2`
	- `days_since_loaded = null`
- Mobile requirements at 375px width:
	- no horizontal scroll
	- pattern grid remains 2x2
	- 44x44 minimum touch targets
	- footer stacks vertically

Out of scope for 7.1:
- Trend view restructure
- Session/Log restructure
- backend changes
- check-in form changes
- verification queue changes

### Stage 7.2 - Trend View (COMPLETE)

Goal:
- Move trend-specific charts and controls into a dedicated Trend experience.

Implemented changes:
- Added dedicated Trend tab and section in `static/index.html`.
- Added one time-range selector (`6w`, `3m`, `6m`) with client-side filtering only.
- Added chart lifecycle state and render flow:
	- `activateTrendTab()`
	- `renderTrendView()`
	- chart destroy/recreate on range switch for clean redraws
- Added shared payload fetch/cache plumbing:
	- `ensureTrainingLoadPayload()` now owns the only frontend `/api/training-load` fetch call.
	- Today and Trend views both consume the same in-memory payload/promise.
	- Cache invalidation added on actions that mutate load outputs (check-in save, sync success, calibration save/reset).
- Added Trend chart 1 (Fatigue/Fitness/Form):
	- ATL, CTL, TSB lines
	- auto y-scale
	- dashed zero reference line hidden from legend/tooltip
	- tooltip includes derived training state label fallback from TSB thresholds
- Added Trend chart 2 (pattern ATL):
	- knee, hip, push, pull lines
	- legend toggles enabled
	- fallback message when `pattern_loads` is unavailable for selected range
- Added mobile-specific behavior already aligned to Stage 7.2 requirements:
	- min chart heights at narrow widths
	- range controls keep 44px touch target size

Gate evidence (passed):
- No undefined-function runtime risk remains for trend activation (`activateTrendTab` / `renderTrendView` now implemented).
- Single frontend fetch definition for `/api/training-load` confirmed in code (`ensureTrainingLoadPayload`).
- Trend can render from existing Today cache without duplicate fetch path.
- Empty-history and missing-pattern fallbacks render without crashes.
- Range selection re-renders both charts with filtered history windows (42, 90, 180 days).

### Stage 7.3 - Log / Session View (Session C) - COMPLETE

Goal:
- Promote workout/session diagnostics and log workflows in a dedicated view.

Implemented changes:
- Reworked the Workouts tab in `static/index.html` to split into two distinct surfaces:
	- Session Verification Queue (existing Stage 4 flow retained)
	- Session Log (new Stage 7.3 surface)
- Removed the old `Last 12 Workouts - Stress Detail` table and replaced it with a session-log experience backed by `GET /api/workout-sessions`.
- Added session log state and helpers in `static/index.html`:
	- `sessionLogRows`, `sessionLogVisibleCount`, `sessionLogFilter`, `sessionLogFatiguePayload`, `sessionDetailCache`
	- `loadSessionLog()`, `renderSessionLog()`, `setSessionLogFilter()`, `loadMoreSessionLog()`
	- `_sessionBadgeClass()`, `_sessionFilterMatches()`, `_sessionFatigueAnnotation()`, `_sessionStatusNote()`
	- `toggleSessionDetail()` and detail rendering helpers for all supported session types
- Added a new on-demand backend detail endpoint in `main.py`:
	- `GET /api/workout-sessions/{hevy_workout_id}`
- Added modality-aware session detail payloads in `main.py`:
	- `strength` / `hypertrophy`: set-level detail plus central/peripheral stress
	- `conditioning`: sRPE x duration load plus mapped pattern distribution
	- `cardio`: sRPE x duration load plus fixed 30/70 central/peripheral split
	- `pending`: verification requirements plus imported exercise summary
- Fixed FastAPI route ordering so static `GET /api/workout-sessions/pending` is not shadowed by dynamic `GET /api/workout-sessions/{hevy_workout_id}`.
- Added responsive session-log CSS for badges, toolbar, cards, detail grids, and stacked mobile layout.

Gate evidence (passed):
- Workouts tab now loads the verification queue and session log together via `loadWorkouts()`.
- Session log filtering, empty-state rendering, and load-more behavior implemented without relying on the removed recent-workouts table.
- On-demand session detail rendering implemented for all four variants: pending, strength/hypertrophy, conditioning, and cardio.
- Pending queue fetch path restored after route-order fix.
- Empty-state live validation passed without API key or workout data.

Open validation gap before broader rollout:
- Real-data visual validation for populated session-detail cards, modality realism, and trend-shape realism is still pending until the local database contains representative imported sessions.

### Post-Stage 7.3 Scoped Changes (completed before commit)

Implemented changes:
- Updated `_subjective_fatigue()` in `main.py` so joint fields no longer contribute to the global fatigue score; weighting is now `0.45 tiredness + 0.30 recovery + 0.25 soreness`.
- Added `_resolve_joint_advisory()` in `main.py` and included `joint_advisory` in `today.recommendation_v2`.
- Added a conditional `Joint Advisory` card to the Today view in `static/index.html`.
- Rendered advisory/warning rows for upper and lower joint signals using existing Stage 7.1 pattern color tokens:
	- knee -> `--quad`
	- hip -> `--posterior`
	- push -> `--push`
	- pull -> `--pull`
- Polished the Today status tiles so `Check-in pending` / `0 pending` inherit the app font and align correctly inside the status cards.

Validation evidence (passed):
- Backend joint gate assertions passed for:
	- no-check-in hidden advisory state
	- `2/1` -> none / none
	- `3/1` -> upper advisory
	- `4/3` -> upper warning + lower advisory
	- `4/4` -> upper warning + lower warning
	- fatigue-score invariance with joint values changed
- Frontend advisory rendering was validated with injected payload cases for hidden, advisory, and warning combinations.
- Pattern chips were manually verified to use existing CSS token variables rather than hardcoded colors.
- Today status tile typography/alignment fix validated with no file errors and live page rendering confirmation.

Gate tests:
- 7.1 gates:
	- Today is default landing page.
	- Training-state headline color maps correctly across all five states.
	- Pattern grid renders all four cells with status tint, days-since-loaded, and dot counts.
	- Tooltips render on hover/tap for Fatigue/Fitness/Form labels.
	- All fallback states render without crash (no check-in, no workout data, missing `recommendation_v2`, null `days_since_loaded`).
	- Single-fetch behavior on load is preserved (`/api/training-load` + `/api/workout-sessions/pending` only).
- 7.2 gates:
	- Trend tab renders two charts from `/api/training-load` history with one time selector.
	- Range control filters on client only (6w/3m/6m).
	- Main chart includes ATL/CTL/TSB lines and dashed y=0 reference line.
	- Tooltip includes training state label (payload label or TSB-threshold fallback).
	- Pattern chart includes knee/hip/push/pull ATL lines and legend toggles.
	- Missing pattern history shows note instead of chart crash.
	- Trend and Today share one cached payload fetch pathway.
- 7.3 gates:
	- Workouts tab renders the verification queue and session log together.
	- Session log is driven by session endpoints rather than the removed recent-workouts table.
	- Filter chips (`all`, `pending`, `verified`, `strength`, `hypertrophy`, `conditioning`, `cardio`) render and switch views client-side.
	- Empty-state rendering succeeds without crashes when there is no API key or no imported workout data.
	- Session detail expands on demand and supports pending, strength/hypertrophy, conditioning, and cardio payload shapes.
	- Static `pending` route remains reachable after adding dynamic session detail route.

	### Post-Stage 7.3 Session Log + Session Processing Hardening (completed before commit)

	Implemented changes:
	- Updated verification-queue success flow in `static/index.html` so session verification refreshes both surfaces immediately:
		- `loadSessionVerificationQueue()`
		- `loadSessionLog()`
	- Added inline session-row editing for both `pending` and `verified` rows in Session Log:
		- `Edit` action on every row
		- row-local inline form with modality, duration, and conditional sRPE inputs
		- `Save` writes through `PUT /api/workout-sessions/{hevy_workout_id}/verify`
		- `Cancel` closes inline editor without mutation
	- Extended verification payload contract in `main.py`:
		- `SessionVerificationUpdate.verify: bool = True`
		- `verify=true` keeps queue verification behavior (promote to `verified`)
		- `verify=false` performs edit-only mutation while preserving current status
		- pending rows remain pending after edit; verified rows remain verified after edit
	- Added session-log pagination with backend offset/limit support:
		- Frontend default page size raised to `50`
		- `Load More` now fetches the next page from API instead of only expanding a local slice
		- Backend `GET /api/workout-sessions` now supports `limit` and `offset` (default `limit=50`)
	- Confirmed and reused shared `_toggleSessionSrpe(...)` behavior for both:
		- verification queue cards
		- inline edit forms
	- Raised auto-verify threshold policy from `0.80` to `0.90` for strength/hypertrophy auto-verification.
	- Added configurable session-processing setting in `app_settings`:
		- `auto_verify_confidence_threshold` (default `0.90`, valid `0.50..1.00`)
	- Updated importer verification logic in `importer.py`:
		- `_resolve_verification(..., auto_verify_confidence_threshold=0.90)`
		- strength/hypertrophy auto-verify only when confidence >= configured threshold
		- conditioning/cardio always pending regardless of confidence
	- Updated sync execution path in `main.py` so new syncs immediately honor current settings:
		- `/api/sync` reads `auto_verify_confidence_threshold` from `app_settings`
		- threshold is injected into `import_hevy_data(...)`
	- Renamed Settings section from `Conditioning Load Scale` to `Session Processing` in `static/index.html`.
	- Added `Auto-Verify Confidence Threshold` field to Session Processing with single-section save behavior covering:
		- `conditioning_stress_scaling_factor`
		- `auto_verify_confidence_threshold`
		- endpoint: `PUT /api/settings/v2/session-processing`

	Follow-up bugfixes completed:
	- Fixed row-panel conflict in Session Log so only one panel can be open per row:
		- opening `Edit` closes `Show Details`
		- opening `Show Details` closes `Edit`
		- closing either returns row to collapsed baseline
	- Normalized inline edit control sizing so duration and sRPE inputs match modality select height/visual weight using existing form styling tokens (no hardcoded fixed px sizes).

	Validation evidence (passed):
	- Backend gate script validated:
		- session-processing save/load and threshold-range validation
		- edit-only behavior preserving row status for pending and verified sessions
		- verification path still promoting pending sessions when `verify=true`
		- pagination parameter behavior (`limit`/`offset`)
		- auto-verify policy gates:
			- confidence < 0.95 -> pending for strength/hypertrophy
			- confidence >= 0.95 -> auto-verified for strength/hypertrophy
			- conditioning/cardio always pending
	- Frontend wiring verified in code for:
		- dual refresh after queue verification
		- inline edit availability on all rows
		- dynamic sRPE visibility toggle
		- mutual exclusion between edit/details panels
		- 50-row page fetch + API-backed load-more flow

	### Post-Stage 7.4 Title-Aware Session Modality Detection (completed before commit)

	Implemented changes:
	- Added title-first modality inference layer in `importer.py` before exercise-level analysis.
	- Added explicit title keyword sets:
		- conditioning: metcon, wod, amrap, emom, hiit, conditioning, cardio, crossfit, circuit
		- strength: me upper, me lower, max effort
		- hypertrophy: hypertrophy, hyp, bodybuilding
	- Single-modality title match behavior:
		- selects matched modality with confidence `0.95`
	- Mixed-modality title match behavior:
		- selects dominant modality by match count, with tie-priority `conditioning > strength > hypertrophy`
		- sets confidence `0.70` to force verification queue review
		- writes session note: `Mixed session detected - consider splitting by modality`
	- No title match behavior:
		- falls through to prior exercise-level set/rep analysis unchanged
	- Added `WorkoutSession.modality_note` persistence field and startup-safe schema migration for existing SQLite databases.
	- Exposed `modality_note` in workout session API list/detail/update responses.
	- Session-processing default now aligned to `0.90`.

	Validation evidence (passed):
	- Gate 1: `CC4.1.2 METCON` -> conditioning, confidence `0.95`
	- Gate 2: `CC4.1.1 PP/PU + WOD` -> conditioning, confidence `0.95`
	- Gate 3: `ME Lower + METCON` -> conditioning dominant, confidence `0.70`, mixed-session note present
	- Gate 4: `Morning Workout` with barbell sets -> no title match, falls through to existing exercise analysis behavior
	- Gate 5: `Hypertrophy Upper` -> hypertrophy, confidence `0.95`
	- Gate 6: case-insensitive matching verified
	- Aggregate result: `TITLE_MODALITY_GATES PASS`

	### Post-Stage 7.5 Local Session Reclassification + Settings Spacing Repair (completed before commit)

	Implemented changes:
	- Added DB-only session reclassification path in `importer.py` that:
		- reads existing `workout_sessions`
		- reads stored `workout_logs` for each session
		- rebuilds exercise payloads from stored data
		- reruns current title-first modality inference plus existing exercise-analysis fallback
		- updates `modality`, `modality_confidence`, and `modality_note`
	- Added `POST /api/settings/v2/reclassify-sessions` in `main.py`.
	- Default reclassification behavior:
		- updates `pending` sessions only
		- skips `verified` sessions and reports skip count
	- Added explicit force-all behavior:
		- allows verified sessions to be overwritten only when user explicitly requests full reclassification
	- Added Session Processing UI actions in `static/index.html`:
		- `Reclassify Sessions`
		- `Force Reclassify All`
		- force-all path requires confirmation
	- Reclassification completion now refreshes both session surfaces:
		- verification queue
		- session log
	- No Hevy sync/API path is used during local reclassification.
	- Repaired Settings page spacing regression in `static/index.html` by removing inline top-margin overrides from Settings cards so spacing returns to existing card/grid spacing tokens.

	Validation evidence (passed):
	- Backend reclassification gate validated:
		- pending session title-match reclassification
		- pending session exercise-fallback reclassification
		- verified sessions skipped during normal run
		- force-all run updates previously verified session
		- result summary counts are correct
		- Hevy import path is not called
		- aggregate result: `RECLASSIFY_GATES_BACKEND PASS`
	- UI/code checks verified:
		- `Reclassify Sessions` button present in Session Processing
		- `Force Reclassify All` option present with confirmation
		- completion path refreshes `loadSessionVerificationQueue()` and `loadSessionLog()`
	- Settings spacing repair verified by removing per-card inline `margin-top:14px` overrides so section spacing is controlled by existing shared layout rules.

	### Post-Stage 7.6 Settings V2 Rehydration Fix + Auto-Verify Default Rollback (completed before commit)

	Implemented changes:
	- Root-cause fix in `static/index.html` for Settings tab hydration:
		- `loadSettingsTab()` now always calls `loadV2Settings()` even if `GET /api/settings` (API-key metadata fetch) fails.
		- This prevents stale/default-looking threshold inputs when the API-key fetch path errors.
	- Confirmed Training State input mapping remains correct:
		- `tsb-underloaded` <- `tsb_threshold_underloaded`
		- `tsb-slightly-fresh` <- `tsb_threshold_slightly_fresh`
		- `tsb-balanced` <- `tsb_threshold_balanced`
		- `tsb-slightly-fatigued` <- `tsb_threshold_slightly_fatigued`
	- Confirmed Settings hydration trigger remains on tab activation:
		- `activateTab('settings')` -> `loadSettingsTab()`
	- Rolled auto-verify default baseline back to `0.90`:
		- backend default constant in `main.py`
		- startup seed behavior now preserves existing user-configured values and only seeds missing values
		- importer default argument baselines aligned to `0.90`
		- Session Processing input placeholder aligned to `0.90`

	Validation evidence (passed):
	- Settings TSB gate validated:
		- save custom thresholds (`40`, `15`, `-20`, `-50`)
		- reopen-equivalent fetch returns saved values
		- refresh-equivalent fetch via fresh DB session returns saved values
		- auto-verify default baseline verified at `0.90`
		- aggregate result: `SETTINGS_TSB_GATES_BACKEND PASS`
	- Settings container layout correction validated:
		- explicit two-column grid areas enforce intended grouping
		- left column contains: Hevy API Key, Pattern Sensitivity, Hevy Sync
		- right column contains: Training State Thresholds, Session Processing
		- responsive fallback still collapses to single-column on narrow viewports

## Decisions Locked

- Full-body via existing percentage fields (no `is_full_body` column).
- Primary modality approximation for mixed sessions in this phase.
- Compute-on-demand pattern EWMA and retroactive correction behavior.
- Extend `/api/training-load` instead of adding a separate recommendation endpoint.
- Strict stage gates with required pass criteria before progression.
- Local DB reset/reimport is acceptable during migration and validation.
