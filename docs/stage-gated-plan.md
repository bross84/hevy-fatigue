# Stage-Gated Implementation Plan

This document locks implementation to strict stage gates and dependency order.

## Execution Rules

1. Only implement one stage at a time.
2. Do not begin the next stage until all tests for the current stage pass.
3. Keep changes scoped to files required by the active stage.
4. Preserve existing API contracts unless a stage explicitly changes them.
5. Use compute-on-demand where chosen, so corrected mappings update historical outputs retroactively.

## Latest Maintenance Update (2026-05-03, Sync Cooldown Removal)

- Removed sync cooldown enforcement from `POST /api/sync` in `main.py`.
- Removed `_SYNC_COOLDOWN_SECONDS` and the cooldown return path so sync requests are no longer throttled by elapsed time.
- Kept `_sync_lock` unchanged so overlapping sync runs remain blocked by the existing `already_running` guard.
- Validation: `python -m py_compile main.py` passed.

## Latest Maintenance Update (2026-05-03, Incremental Sync Gate)

- Added `incremental_sync_gate.py` using the same gate-runner output structure as existing gate scripts.
- Added preflight checks for app reachability and `GET /api/sync/last-sync` endpoint existence.
- Implemented five gates covering first-sync bootstrap behavior, incremental cursor advancement, local delete simulation checks, canonical substitution integrity checks, and repeat cursor advancement checks.
- Gate script supports `--base-url` and `--db-path` with defaults `http://127.0.0.1:8000` and `/data/hevy_fatigue.db`.
- Script prints per-gate PASS/FAIL (or SKIP), final summary counts, and exits non-zero when any gate fails.
- Validation: `python -m py_compile incremental_sync_gate.py` passed.

## Latest Maintenance Update (2026-05-03, Incremental Sync Migration + API)

- Added one-time startup migration in `database.py:init_db()` guarded by `app_settings.migration_incremental_sync_v1`.
- On first startup after deploy (flag missing), migration deletes `app_settings.last_sync` to force a fresh `initial_import`, then writes the migration flag so subsequent restarts skip it.
- Added `GET /api/sync/last-sync` in `main.py` (before static mounts), returning `{ "last_sync": <value|null> }` from `app_settings`.
- Validation: `python -m py_compile database.py` and `python -m py_compile main.py` passed.

## Latest Maintenance Update (2026-05-03, Importer Sync Refactor)

- Refactored `importer.py` into a two-mode sync flow with extracted `_process_workout(db, workout, canonical_map)` logic shared by:
	- `initial_import(db, canonical_map)` for full `GET /v1/workouts` pagination
	- `incremental_sync(db, last_sync, canonical_map)` for `GET /v1/workouts/events?since=...`
- Preserved existing importer behavior inside `_process_workout()` for canonical title substitution, modality classification, `ensure_exercise_mapped()`, `WorkoutSession` upserts, and set-level `WorkoutLog` upserts.
- `initial_import()` now clears `workout_logs`, `workout_sessions`, and auto/unreviewed `exercise_mappings` before replaying paginated workout imports.
- `incremental_sync()` now removes local rows for deleted workouts and reprocesses updated workouts from Hevy events, then stores the sync cursor in `app_settings.last_sync`.
- Updated importer callers in `main.py`, `canonical_gate.py`, and `conflict_gate.py` to use the new `import_hevy_data(db)` entrypoint.
- Validation: `python -m py_compile importer.py` and `python -m py_compile main.py canonical_gate.py conflict_gate.py` passed.

## Latest Maintenance Update (2026-05-03)

- Added `HevyClient.get_workout_events(since, page=1, page_size=10)` in `hevy_client.py` for `GET /v1/workouts/events`.
- Method builds the events URL inline, uses `self.session.get(..., timeout=30)`, clamps `page_size` to the API max of `10`, and returns `{ page, page_count, events: [] }` for `404` responses.
- Method now raises explicit client-side errors for unauthorized, HTTP, JSON decode, connection, timeout, and unexpected failure paths without adding a new repo-wide config or error abstraction.
- Validation: `python -m py_compile hevy_client.py` passed.

## Latest Maintenance Update (2026-04-26)

- `static/diagnostic.html` AI assistant markdown rendering added:
	- `marked.js` 9.1.6 loaded via CDN `<script>` in `<head>`
	- assistant message bubbles (initial render and streaming updates) now use `marked.parse()` for markdown formatting
	- user message bubbles retain `escapeHtml()` for XSS safety

## Latest Maintenance Update (2026-04-29)

- Today recommendation state switched from TSB-driven labels to a combined-score model in `/api/training-load`:
	- `combined_score = 0.80 * subjective_score + 0.20 * objective_score`
	- `subjective_score` comes from readiness check-in with fallback `5.0`
	- `objective_score` comes from 7-day session volume against 6-month weekly average volume
- `today.recommendation_v2` now exposes `subjective_score`, `objective_score`, and `combined_score` for frontend display.
- Today recommendation card now renders the three score tiles under the training-state detail line.

## Latest Maintenance Update (2026-04-30)

- Fixed CSS corruption in `static/index.html` introduced during Settings grid rebalancing:
	- removed stray `grid-template-areas` string literals from the `[data-theme="light"]` variable block
	- restored missing `html { ... }` wrapper in the Base section
	- removed misplaced `.today-chart-*` rules from the dark theme token block and restored them to normal CSS scope
	- moved mobile `.today-chart-wrap` sizing override back under a proper media query
- Verified style-block structural integrity:
	- brace count balanced
	- brace depth never negative
	- static diagnostics clean for `static/index.html`
- Updated 7-Day Readiness Trend visual contrast in `static/index.html`:
	- replaced five readiness-zone band colors with higher-contrast rgba values; current palette uses deep navy / cyan / green / amber / red bands
	- set readiness chart x/y gridlines to `rgba(128,128,128,0.15)` for improved visibility in both light and dark themes

## Latest Maintenance Update (2026-05-01, Backfill Sessions)

- Settings tab refactored to 3-card layout in `static/index.html`:
	- Pattern Sensitivity card removed; controls migrated to `static/diagnostic.html`
	- Session Processing card removed; controls migrated to `static/diagnostic.html`
	- Desktop grid-template-areas updated to `"api sync" / "diagnostics diagnostics"`
	- Mobile media query updated to reset `api`, `sync`, and `diagnostics` areas only
	- `View engine diagnostics →` text link replaced with a full-width `settings-card-diagnostics` card with accent-colour CTA button
	- Removed JS: `loadV2Settings()`, `savePatternSensitivity()`, `saveSessionProcessingSettings()`, `reclassifySessions()` from `static/index.html`
- Diagnostics page settings controls added to `static/diagnostic.html`:
	- Pattern Sensitivity section: Stressed/Neutral threshold inputs, save button, result feedback
	- Session Processing section: Auto-Verify Confidence Threshold input, pending + force reclassify buttons, result feedback
	- `diagLoadV2Settings()` called from `loadAndRender()` — inputs populate on page load and Refresh

## Latest Maintenance Update (2026-05-01)

- Added `POST /api/admin/backfill-sessions` in `main.py` for local data repair:
	- backfills missing `workout_sessions` rows from `workout_logs` where `workout_id` has no matching `workout_sessions.hevy_workout_id`
	- uses earliest `WorkoutLog` row per workout (`ORDER BY date, id`) for deterministic `workout_date` and `workout_title`
	- sets defaults: `modality="strength"`, `modality_confidence=0.0`, `verification_status="verified"`, `verified_at=datetime.utcnow()`, null `start_time/end_time/duration_minutes/srpe`
	- returns `{ "backfilled": N }`
- Validation:
	- `python -m py_compile main.py` passed
	- live endpoint verification currently blocked in this environment because local app startup fails with `ModuleNotFoundError: No module named 'cryptography'`

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
	- Raised auto-verify threshold policy from `0.80` to `0.90` for strength/hypertrophy auto-verification (later superseded to `0.87` in Post-Stage 7.6/7.7).
	- Added configurable session-processing setting in `app_settings`:
		- `auto_verify_confidence_threshold` (default `0.90` at this stage, valid `0.50..1.00`; later superseded to `0.87`)
	- Updated importer verification logic in `importer.py`:
		- `_resolve_verification(..., auto_verify_confidence_threshold=0.90)` at this stage (later superseded to `0.87`)
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
			- confidence < configured threshold -> pending for strength/hypertrophy
			- confidence >= configured threshold -> auto-verified for strength/hypertrophy
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
	- Session-processing default aligned to `0.90` at this stage (later superseded to `0.87`).

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
	- Rolled auto-verify default baseline to `0.87`:
		- backend default constant in `main.py`
		- startup migration now upgrades legacy stored `0.90` and `0.95` values to `0.87`
		- startup seed behavior still preserves user-configured values outside migrated legacy defaults and seeds missing values
		- importer default argument baselines aligned to `0.87`
		- Session Processing input placeholder aligned to `0.87`

	Validation evidence (passed):
	- Settings TSB gate validated:
		- save custom thresholds (`40`, `15`, `-20`, `-50`)
		- reopen-equivalent fetch returns saved values
		- refresh-equivalent fetch via fresh DB session returns saved values
		- auto-verify default baseline verified at `0.87`
		- aggregate result: `SETTINGS_TSB_GATES_BACKEND PASS`
	- Settings container layout correction validated:
		- explicit two-column grid areas enforce intended grouping
		- left column contains: Hevy API Key, Pattern Sensitivity, Hevy Sync
		- right column contains: Training State Thresholds, Session Processing
		- responsive fallback still collapses to single-column on narrow viewports

	### Post-Stage 7.7 Title Abbreviation Codes + Mixed Plus Rule (completed before commit)

	Implemented changes:
	- Extended title keyword sets in `importer.py` with naming-convention abbreviation codes:
		- strength: ` ST`
		- hypertrophy: ` HYP`
		- conditioning: ` CON`
		- cardio: ` CAR` (separate `CARDIO_TITLE_KEYWORDS` list)
	- Added `strongman` to conditioning title keywords.
	- Kept case-insensitive matching by lowercasing title and keyword lists.
	- Added mixed-session override rule in title inference:
		- if title contains `+` and at least one modality keyword/code is matched, return confidence `0.70` with mixed-session note
		- dominant modality in this rule is chosen by earliest keyword position in title
	- Kept no-match fallthrough path unchanged:
		- title inference returns no result and existing exercise-level analysis decides modality/confidence.

	Validation evidence (passed):
	- `CC4.1.1(A) ST` -> `strength`, confidence `0.95`, auto-verified at threshold `0.87`
	- `CC4.1.1(A) HYP` -> `hypertrophy`, confidence `0.95`, auto-verified at threshold `0.87`
	- `CC4.1.1(A) ST + CON` -> mixed-session note present, confidence `0.70`, pending queue
	- `CC4.1.1(A) HYP + CON` -> mixed-session note present, confidence `0.70`, pending queue
	- `STRICT PRESS` -> no false-positive ` ST` match, falls through
	- `STRONGMAN Medley` -> `conditioning`, confidence `0.95`
	- `METCON` -> `conditioning`, confidence `0.95`, pending queue
	- `CC4.1.1(A)` -> no title match, falls through to exercise analysis unchanged
	- Case-insensitive matching validated across mixed-case titles
	- Startup migration check passed for stored `0.90` and `0.95` values -> `0.87`
	- Aggregate result: `ALL_GATES_PASS`

	### Post-Stage 7.8 sRPE Title-Tag Import + Conditional Auto-Verify (completed before commit)

	Implemented changes:
	- Added title sRPE parsing in `importer.py` for pattern `@N` or `@N.N` where `N` is `0..10`.
	- Import path now writes parsed value into `workout_sessions.srpe` (insert + upsert paths).
	- Added title-only conditioning signal:
		- when a valid `@N` tag exists and no modality keywords/codes are matched, title inference returns `conditioning` with confidence `0.95` before exercise analysis.
	- Updated verification behavior in import path:
		- strength/hypertrophy auto-verify behavior remains threshold-based.
		- conditioning/cardio sessions are now eligible for auto-verify only when:
			- confidence `>= auto_verify_confidence_threshold`
			- parsed `srpe` is present
			- `srpe` came from title tag
	- Updated Session Verification Queue title display in `static/index.html`:
		- strips `@N` / `@N.N` from rendered card title for readability
		- does not alter stored `workout_title` in DB.

	Validation evidence (passed):
	- `CC4.1.6 CON @7` -> `conditioning`, `srpe=7.0`, auto-verified
	- `CC4.1.6 METCON @8` -> `conditioning`, `srpe=8.0`, auto-verified
	- `Saturday WOD @6.5` -> `conditioning`, `srpe=6.5`, auto-verified
	- `CC4.1.6 METCON` (no tag) -> `srpe=null`, pending queue behavior unchanged
	- `@11` invalid range ignored (no sRPE parsed)
	- `@abc` invalid format ignored (no sRPE parsed)
	- Verification card display title strips sRPE tag while preserving stored title
	- Case-insensitive keyword matching remains intact alongside sRPE parsing
	- `CC4.1.1(A) ST @7` remains strength-classified (sRPE parsing does not override ST)
	- `CC4.1.6 @7` (tag only) -> `conditioning`, `srpe=7.0`, auto-verified
	- Aggregate result: `SRPE_TITLE_GATES_PASS`

	### Post-Stage 7.9 Today Page Consolidation + Check-in Toggle Refinement (completed before commit)

	Implemented changes:
	- Today recommendation card content simplified:
		- removed fatigue score/tier display line
		- retained only training-state label and training-state detail text.
	- Removed Today Status card entirely:
		- removed CHECK-IN / PENDING SESSIONS / LAST SYNC tile card from markup and render paths.
	- Updated submitted-check-in interaction model:
		- when today's check-in exists, show collapsed minimal submitted card
		- add `Edit / Backdate` toggle that expands/collapses full form
		- expanded form always shows date picker and defaults it to today.
	- Submitted-state display simplification finalized:
		- collapsed state renders only success banner + `Edit / Backdate` button
		- removed submitted-values read-only grid and related CSS entirely
		- no read-only values grid is shown in any submitted-state path.
	- Collapse-without-save behavior hardened:
		- collapsing editor resets all fields back to today's saved values (no unsaved draft retained).
	- Backdated save while today's summary exists:
		- post-submit flow resets picker to today and re-fetches `/api/readiness/today` so summary card always reflects today's canonical entry.
	- Date picker constrained:
		- `ci-date` now has `max=today`, preventing future-date submissions while preserving backdated entries.
	- Removed dead CSS:
		- deleted unused `.today-fatigue-line` class after fatigue line render removal.

	Validation evidence (passed):
	- Recommendation card no longer renders fatigue/tier line.
	- Status card removed from Today markup and render fallback path.
	- Submitted mode shows collapsed summary + `Edit / Backdate` toggle.
	- Submitted mode collapsed content is limited to banner + toggle only.
	- No read-only values grid rendered in submitted mode.
	- Toggle collapse restores today's saved values and clears transient status.
	- Backdated submit from expanded submitted-mode re-fetches today's entry via `/api/readiness/today`.
	- Date picker enforces max=today.
	- Static file diagnostics clean after patch.

	### Post-Stage 7.10 — Trend Chart Window Lock + Legacy Chart Removal (Requirements 2.1 & 2.3)

	Implemented changes:
	- Fixed Trend chart visible date window to always display 30 days ending today (requirement 2.1):
		- ATL/CTL/TSB chart now uses `_trendSlice()` with hardcoded 30-day window instead of variable slice.
		- Per-Pattern ATL chart uses same fixed 30-day window.
		- Charts always display the same x-axis date span regardless of selector state.
	- Repurposed Time Range selector from date-range control to smoothing-window control:
		- Selector button labels preserved as: 3 Day, 7 Day, 14 Day.
		- Default selector state changed to 7d (previously 3).
		- Selector click updates `trendSmoothingDays` (previously `trendRangeDays`).
		- Selector re-renders charts with new moving-average window applied to all three datasets.
	- Implemented client-side trailing moving average smoothing via new `_trendRollingAvg()` helper:
		- ATL/CTL/TSB datasets apply smoothing before rendering.
		- Per-Pattern ATL datasets apply smoothing before rendering.
		- Tooltip values now read directly from plotted Chart.js dataset points (smoothed values), matching rendered lines.
	- Removed legacy Training Stress (Legacy View) chart entirely (requirement 2.3):
		- Removed chart container, canvas element `stressChart`, and all markup from Trend tab.
		- Removed pattern filter (Total/Quad/Hip/Push/Pull) button group tied only to legacy chart.
		- Removed baseline toggle (3d/6d/12d) button group tied only to legacy chart.
		- Deleted legacy chart rendering functions: `renderChart()`, `renderPatternChart()`.
		- Deleted helper functions: `chartOpts()`, `buildDatasets()`, `rollingAvg()`.
		- Deleted stress history fetch: `loadStressHistory()` and global `stressHistory` state.
		- Deleted event listeners for pattern-filter and baseline-toggle controls.
		- Deleted pattern cache state and related globals: `patternCache`, `activePattern`, `baselineDays`.
		- Updated `_destroyTrendCharts()` to no longer attempt stressChart destruction.
		- Updated `renderTrendView()` to no longer attempt legacy chart render or call `loadStressHistory()`.

	Validation evidence (passed):
	- Static file diagnostics clean (no errors).
	- Both remaining Trend charts (ATL/CTL/TSB and Per-Pattern ATL) render with fixed 30-day date coverage.
	- Time Range selector labels remain 3 Day / 7 Day / 14 Day with default 7 Day.
	- Selector click triggers re-render with new smoothing window applied.
	- Both charts maintain same x-axis labels (30-day span) across all selector changes.
	- Tooltip values match smoothed plotted line values (not raw daily source fields).
	- Legacy chart card, controls, canvas, and all related JS completely removed from markup and code.
	- No references remain to `stressChart`, `renderChart`, `renderPatternChart`, `patternCache`, `activePattern`, `baselineDays`, or `stressHistory`.
	- Trend tab lifecycle (tab activate, re-render on resize, re-render on selector change) stable.

	### Post-Stage 7.11 — Local-Time `todayStr()` + Dashboard Tab Readiness Refresh

	Implemented changes:
	- Updated frontend `todayStr()` in `static/index.html` to build `YYYY-MM-DD` from local date parts (`getFullYear/getMonth/getDate`) instead of UTC `toISOString()`.
	- This aligns frontend date comparisons with browser date-input local-date semantics and prevents UTC/local day-boundary mismatches in today submitted-state detection.
	- Verified backend `/api/readiness/today` in `main.py` queries `DailyReadiness.date == date_type.today()`, which uses server-local date semantics.
	- Added `checkTodayReadiness()` call inside `activateTab()` for the dashboard tab alongside the existing `loadTrainingLoadCard()` call.
	- This ensures submitted-state is evaluated every time the user navigates to the dashboard tab, not only on the initial DOMContentLoaded.
	- Verified `ci-date` value and max are set before `checkTodayReadiness()` is called in DOMContentLoaded; ordering is correct.

	Validation evidence (passed):
	- `todayStr()` now returns local-date string format matching browser date input behavior.
	- `checkTodayReadiness()` is now invoked on every dashboard tab switch.
	- Existing comparisons that rely on `todayStr()` now inherit local-date alignment without additional code changes.
	- Backend readiness endpoint remains unchanged and already uses `date_type.today()`.
	- Static diagnostics clean after patch.

	### Post-Stage 7.12 — Combined Score Recommendation Model Switch

	Implemented changes:
	- Added objective load scoring in `main.py` for `/api/training-load`:
		- queries `WorkoutSession` rows from the trailing 7-day and 180-day windows
		- derives per-session volume from `WorkoutLog` rows using `WorkoutLog.workout_id == WorkoutSession.hevy_workout_id`
		- computes `objective_score` from 7-day volume versus 26-week average weekly volume, clamped to `0..10`
	- Added `_combined_recommendation()` in `main.py` with five states:
		- `large_increase`, `increase`, `continue`, `decrease`, `large_decrease`
	- Reworked `_build_recommendation_v2(...)` so `training_state`, `training_state_label`, and `training_state_detail` now come from `combined_score`, not TSB thresholds.
	- Preserved non-state `recommendation_v2` fields including `pattern_status`, `joint_advisory`, `tsb`, `fatigue_score`, and threshold metadata.
	- Added `subjective_score`, `objective_score`, and `combined_score` to `today.recommendation_v2`.
	- Updated Today recommendation card rendering in `static/index.html`:
		- added three score tiles (Subjective, Objective, Combined) under the state detail line
		- added formula explainer below score tiles: `Combined = (Subjective × 80%) + (Objective Load × 20%)`
		- updated headline color mapping to the new five combined-score states.
	- Added pattern explainer text below the pattern grid in `static/index.html`:
		- describes the 7-day verified-session basis and the four movement patterns (Knee, Hip, Push, Pull)

	### Post-Stage 7.13 — Pattern Dot Stress Label Fix

	Implemented changes:
	- Fixed `_stress_level_label()` in `main.py` to accept `dots_filled` (int 1–5) instead of a 3-state status string.
		- Old: `available→Fresh`, `neutral→Moderate`, `stressed→High`
		- New: `1→Fresh`, `2→Min. Stress`, `3→Normal Stress`, `4→Moderate Stress`, `5→High Stress`
	- Updated call site in `_build_recommendation_v2()` to compute `dots` first, pass to both `_stress_level_label(dots)` and `dots_filled` field.
	- Updated JS fallback label in `_safePatternStatus()` in `static/index.html` to derive from `dots_filled` using the same 5-label array.

	Validation evidence:
	- `main.py` syntax validated via `python -m py_compile`.
	- Static diagnostics clean after `static/index.html` patch.
	- Full local route execution is still pending in an environment with project dependencies installed; the currently configured interpreter does not include FastAPI.

	### Post-Stage 7.14 — Verified Session Sync Guard + Diagnostics Engine Snapshot

	Implemented changes:
	- Fixed sync/reclassification overwrite bug in `importer.py` (`import_hevy_data`):
		- before `WorkoutSession` upsert, query existing row by `hevy_workout_id`
		- if existing row is `verification_status == "verified"`, use metadata-only conflict update
		- metadata-only update now sets only: `workout_date`, `workout_title`, `start_time`, `end_time`, `duration_minutes`, `updated_at`
		- preserved fields for verified rows: `modality`, `modality_confidence`, `modality_note`, `verification_status`, `verified_at`, `srpe`
		- new or pending rows still use full upsert behavior (classification fields continue updating)
	- Added `GET /api/diagnostics/snapshot` in `main.py`:
		- returns grouped snapshot payload for subjective/objective/combined breakdowns, raw ATL/CTL/TSB, TSB thresholds, joint advisory, and last 10 session classifications
		- reuses existing helpers from training-load flow, including `_subjective_fatigue`, `_training_modifier`, `_build_recommendation_v2`, and `_session_volume`
		- objective/load volume uses `_session_volume()` for all 7-day and 180-day volume aggregation (no inline weight×reps reimplementation)
		- returns `200` with null-safe fields when check-in data is unavailable
	- Updated `static/diagnostic.html`:
		- added `Engine Snapshot` section above S&C Assistant panel
		- loads `/api/diagnostics/snapshot` on page load
		- renders required groups: Score Breakdown formulas with substituted values, Check-in Inputs, Volume Baseline, Training Load, Joint Advisory, TSB Thresholds, Last 10 Sessions
		- added neutral no-check-in placeholder state while preserving non-check-in diagnostics
	- Updated `static/index.html` Settings tab:
		- added subtle footer text link `View engine diagnostics →` to `/static/diagnostic.html`

	Validation evidence:
	- Syntax checks: no errors in `importer.py` and `main.py`.
	- Static diagnostics checks: no errors in `static/diagnostic.html` and `static/index.html`.
	- Full live endpoint/runtime verification remains pending in an environment with project dependencies installed.

	### Post-Stage 7.15 — Nav Active Class + Settings Grid Mobile Fix

	Implemented changes:
	- Removed hardcoded `active` class from both Today `nav-tab` buttons in `static/index.html`:
		- desktop `.nav-tabs` and mobile `.mobile-drawer-nav` Today buttons no longer carry `active` in HTML
		- runtime `activateTab()` already sets the `active` class dynamically; no JS changes needed
	- Fixed invalid CSS in `@media (max-width: 900px)` block for `.tab-content#tab-settings.active`:
		- removed `grid-template-areas: none` (invalid value; was breaking Settings card layout on mobile)
		- added `grid-area: auto` resets for all five `.settings-card-*` children so cards stack in DOM order under the single-column breakpoint

	Validation evidence:
	- Both fixes are purely HTML/CSS; no JS or Python changes.
	- Static diagnostics check: no errors in `static/index.html`.

	### Post-Stage 7.16 — Remove TSB Settings Card + Add 7-Day Readiness Trend

	Implemented changes:
	- Updated `static/index.html` Settings tab:
		- removed the obsolete `Training State Thresholds` card entirely
		- removed frontend references to `tsb-underloaded`, `tsb-slightly-fresh`, `tsb-balanced`, `tsb-slightly-fatigued`, `btn-save-tsb`, `tsb-result`, and `saveTrainingStateThresholds()`
		- rebalanced desktop Settings layout to named areas `api pattern` / `session sync`
		- mobile `grid-area: auto` reset now targets only the remaining cards: api, pattern, session, sync
	- Added `GET /api/readiness/combined-history` in `main.py`:
		- returns exactly `days` ordered entries from oldest to newest
		- computes `objective_score` per target date from the 7-day window ending on that date versus the 180-day baseline ending on that date
		- computes `subjective_score` via `_subjective_fatigue() * 10` only when a check-in exists that day
		- returns `subjective_score: null` and `combined_score: null` for missing-check-in days while still returning `objective_score`
	- Added Today `7-Day Readiness Trend` card in `static/index.html`:
		- placed below the recommendation card and above the pattern grid
		- fetches `/api/readiness/combined-history?days=7` through a dedicated cache helper alongside `loadTrainingLoadCard()`
		- renders a Chart.js line with point markers, null gaps, short weekday labels, y-axis `0..10`, and five horizontal readiness-zone color bands
		- redraws through the same Today refresh path and on theme changes

	Validation evidence:
	- `main.py` and `static/index.html` report no errors.
	- Targeted search confirms zero remaining frontend references to the removed TSB settings identifiers.
	- Desktop Settings layout and Today-card placement verified in the browser.
	- Full served-app runtime validation and real mobile-browser rendering remain pending outside the current file:// browser context.

        ### Post-Stage 7.17 — Movement Trend feature

        Implemented changes:
        - Added `GET /api/movements/search?q=` in `main.py`:
                - returns `{"results": [...]}` with up to 20 distinct `exercise_title` matches
                - case-insensitive LIKE filter, min 2 characters required, blank query returns empty list
        - Added `GET /api/movements/weekly-trend?exercise=&weeks=` in `main.py`:
                - returns one entry per week for the requested window (8, 12, or 26 weeks)
                - joins `WorkoutLog` to `WorkoutSession` on `workout_id == hevy_workout_id`
                - filters to `verification_status == "verified"` sessions only
                - per-week fields: `week_start` (ISO date of Monday), `weekly_volume`, `avg_weight` (nullable), `set_count`
                - missing weeks return zero volume and null avg_weight
                - Python-side Monday grouping (`date - timedelta(days=date.weekday())`) avoids SQLite ISO week edge cases
                - both endpoints inserted before the static file mount in `main.py`
        - Added Movement Trend card to Workouts tab in `static/index.html`:
                - card placed between Session Verification Queue and Session Log cards
                - 8/12/26 week selector using `.btn-group`
                - search input with 300 ms debounced autocomplete calling `/api/movements/search`
                - autocomplete dropdown (`.mvt-dropdown`) with click-to-select and close-on-outside-click via `document.addEventListener('click')`
                - clear (`×`) button resets selection, dropdown, and chart
                - three states: placeholder text, `.loading-wrap` spinner, `.trend-chart-wrap` canvas
                - Chart.js dual-axis bar+line combo: bars = weekly volume (left Y), line = avg weight with `spanGaps: false` (right Y)
                - theme-aware colors via `themeColors()`; chart rebuilds in `applyTheme()` RAF block when Workouts tab is active and `mvtLastData` is non-null
                - `_mvtInitHandlers()` called once from `DOMContentLoaded`
                - six new state variables: `mvtSelectedMovement`, `mvtWeeks`, `mvtSearchTimer`, `mvtChart`, `mvtSearchSeq`, `mvtLastData`

        Validation evidence:
        - Brace balance audit of `static/index.html`: open == close, delta 0.
        - Symbol presence check: all 12 new identifiers confirmed present at expected counts.
        - Log tab Rec column removed (prior task, same session).
        - Full live browser validation pending in a served-app environment.

	### Post-Stage 7.18 — Movement Trend redesign (UI + client data flow)

	Implemented changes:
	- Replaced the entire Movement Trend implementation in `static/index.html` (HTML, CSS, and JS) while keeping the card between Session Verification Queue and Session Log in Workouts.
	- Updated card structure:
		- title: `Movement Trend`
		- search input (`Search movements...`) with clear button
		- two toggle groups on one wrapping row:
			- Metric: `e1RM`, `Top Set`, `Avg Weight`, `Volume`
			- Window: `8W`, `6M`, `1Y`, `All`
		- chart canvas area + empty placeholder + loading spinner
	- Search and selection behavior:
		- 300 ms debounce, minimum 2 characters
		- autocomplete endpoint remains `/api/movements/search?q=`
		- dropdown selection sets movement, closes dropdown, and loads chart
		- clear resets movement state, chart instance, dropdown, and placeholder message
		- outside-click dropdown close merged into existing document click listener using `event.target.closest('#mvt-search-wrap')`
	- Metric/window endpoint routing changed in client:
		- `e1RM` / `Top Set` / `Avg Weight` -> `/api/movements/session-trend?exercise=&window=`
		- `Volume` -> `/api/movements/volume-trend?exercise=&window=`
	- Chart rendering changed to single line series with markers:
		- `spanGaps: false`
		- x-axis `maxTicksLimit: 6` with short month/day labels
		- y-axis title uses selected metric name
		- y-axis auto-range applies 10% dynamic padding
		- line + points use `--accent`; point border uses `--card`
		- legend disabled; tooltip shows date + metric label + value
	- Lifecycle hardening:
		- prior chart destroyed before each rebuild
		- redraw on theme changes retained when Workouts tab is active and cached movement data exists
		- handler setup made idempotent via `mvtHandlersBound`

	Validation evidence:
	- Static diagnostics pass: `static/index.html` reports no errors.
	- Search confirms old week-selector wiring removed (`mvt-week-selector` / `data-weeks` absent).
	- New endpoint wiring present in `static/index.html`: `/api/movements/session-trend` and `/api/movements/volume-trend`.

	### Post-Stage 7.19 — WorkoutLog title-upsert conflict fix

	Implemented changes:
	- Updated set-level insert behavior in `importer.py` for `WorkoutLog` rows.
	- Replaced `on_conflict_do_nothing()` with `on_conflict_do_update()` using the existing unique set key:
		- `workout_id`, `exercise_id`, `set_number`
	- Conflict update now modifies only title fields:
		- `exercise_title`
		- `workout_title`
	- All other set fields remain unchanged on conflict:
		- `weight_lbs`, `reps`, `rpe`, `rir`, `estimated_1rm`, `is_conditioning`

	Validation evidence:
	- Syntax check passed: `python -m py_compile importer.py`.

	### Post-Stage 7.20 — Movement endpoint contract replacement in main.py

	Implemented changes:
	- Kept `GET /api/movements/search` unchanged.
	- Removed legacy `GET /api/movements/weekly-trend` route.
	- Added `GET /api/movements/session-trend`:
		- params: `exercise` (required), `window` (`8w|6m|1y|all`, default `6m`)
		- filters: verified sessions only, case-insensitive exact movement title match
		- date filter by `WorkoutSession.workout_date` based on window
		- output rows per session: `session_date`, `top_set`, `avg_weight`, `e1rm`
		- `e1rm` uses max set-level `calculate_e1rm(weight, reps, rpe, rir)` per session
	- Added `GET /api/movements/volume-trend`:
		- params: `exercise` (required), `window` (`8w|6m|1y|all`, default `6m`)
		- filters: verified sessions only, case-insensitive exact movement title match
		- groups by Monday-start ISO week from `WorkoutSession.workout_date`
		- output rows: `week_start`, `weekly_volume`

	Validation evidence:
	- Route scan confirms `session-trend` and `volume-trend` are present and `weekly-trend` is absent.
	- Syntax check passed: `python -m py_compile main.py`.

	### Post-Stage 7.21 — Exercise rename endpoint + Diagnostics UI tool

	Implemented changes:
	- Added `POST /api/exercises/rename` in `main.py` with JSON body `{ old_title, new_title }`.
	- Validation:
		- both fields required after trimming
		- reject same-title rename (`old_title == new_title`, case-insensitive)
	- Single transaction behavior:
		- updates `WorkoutLog.exercise_title` where old title matches case-insensitively
		- updates `ExerciseMapping.exercise_title` where old title matches case-insensitively
		- skips mapping update silently when no mapping exists
	- Response contract:
		- success: `{ updated_sets, mapping_updated }`
		- 404 when no `WorkoutLog` rows match old title
	- Updated `static/diagnostic.html` Engine Snapshot section with `Exercise Rename Tool` UI:
		- helper text, old/new title inputs, `Rename Exercise` button
		- success message: `Renamed X sets. Mapping updated: yes/no.`
		- 404 message: `No sets found matching that title.`
		- error path shows backend error message

	Validation evidence:
	- Syntax check passed: `python -m py_compile main.py`.
	- Static diagnostics pass: `static/diagnostic.html` reports no errors.

	### Post-Stage 7.22 — Exercise Rename UI moved to Exercises tab

	Implemented changes:
	- Added a new `Rename Exercise` card to `static/index.html` in the Exercises tab, placed above `Exercise Movement Mappings`.
	- Card content includes:
		- helper text for Hevy title-change use case
		- `Current title` autocomplete input using `/api/movements/search?q=`
		- `New title` text input
		- accent-styled `Rename Exercise` button
		- inline result area for success/error feedback
	- Client behavior implemented in `static/index.html`:
		- 300 ms debounced search, min 2 characters
		- autocomplete dropdown uses existing `.mvt-dropdown` and `.mvt-dropdown-item` styles
		- selecting a dropdown option fills current title and closes dropdown
		- submit posts `{ old_title, new_title }` to `/api/exercises/rename`
		- messages:
			- success: `Renamed X sets. Mapping updated: yes/no.`
			- 404: `No sets found matching that title.`
			- other error: backend detail message
		- clearing Current title clears both inputs and result area
		- outside-click dropdown close merged into existing document click listener (no extra global listener)
		- idempotent event binding via `exRenameHandlersBound`
	- Removed the `Exercise Rename Tool` section and its JS handler from `static/diagnostic.html`.

	Validation evidence:
	- Static diagnostics pass: `static/index.html` and `static/diagnostic.html` report no errors.

	### Post-Stage 7.23 — Canonical exercise title overrides (DB + importer + API + UI + gate)

	Implemented changes:
	- Added `ExerciseCanonical` model in `database.py`:
		- `exercise_id` (PK), `canonical_title` (not null), `created_at`, `updated_at`
	- Added startup-safe table creation in `database.py:init_db()`:
		- sqlite table-existence check for `exercise_canonical`
		- creates table when missing (idempotent)
	- Updated `importer.py` set-write path:
		- loads all `exercise_canonical` rows once per sync into dict keyed by `exercise_id`
		- substitutes canonical title before `WorkoutLog` write when mapping exists
		- preserves existing behavior when mapping missing (API title unchanged)
	- Added canonical CRUD endpoints in `main.py` (before static mounts):
		- `GET /api/exercises/canonical`
		- `POST /api/exercises/canonical`
		- `DELETE /api/exercises/canonical/{exercise_id}`
		- GET includes `latest_hevy_title` from most-recent `workout_logs` row per `exercise_id`
	- Updated Exercises tab in `static/index.html`:
		- added `Exercise Name Overrides` card above `Rename Exercise`
		- loads overrides on each Exercises-tab activation
		- table columns: `Hevy Title | Your Name | Action`
		- inline Edit/Save posts to `POST /api/exercises/canonical` and reloads rows
		- empty state: `No overrides set. Exercises use names from Hevy.`
	- Added new gate script `canonical_gate.py`:
		- validates canonical CRUD endpoints against running local app
		- simulates importer with controlled fake-Hevy payload to verify canonical write-through in `workout_logs`
		- prints PASS/FAIL per gate and final summary

	Validation evidence (passed):
	- `database.py` bootstrap check confirmed `exercise_canonical` table exists with expected columns.
	- Focused runtime validation confirmed importer stores canonical title for matching `exercise_id`.
	- API validation confirmed create/list/upsert/delete behavior for canonical rows.
	- `canonical_gate.py` run output:
		- PASS Gate 1..6
		- `SUMMARY: 6 passed, 0 failed`
	- Static/code diagnostics report no errors for touched files:
		- `database.py`, `importer.py`, `main.py`, `static/index.html`, `canonical_gate.py`

	### Post-Stage 7.24 — Dedup gate script for workout_logs protections

	Implemented changes:
	- Added `dedup_gate.py` as a standalone gate script.
	- Script targets DB + sync behavior with three gates:
		- Gate 1: verifies `uq_workout_logs_set` exists in `sqlite_master`.
		- Gate 2: verifies zero duplicate groups for `(workout_id, exercise_id, set_number)`.
		- Gate 3: checks row-count growth after `POST /api/sync` using `/api/sync/status` polling and enforces `after <= before + 10`.
	- Script prints PASS/FAIL per gate, emits final summary, and exits non-zero on failure.

	Validation evidence:
	- Syntax check passed: `python -m py_compile dedup_gate.py`.
	- Full runtime gate execution depends on DB path `/data/hevy_fatigue.db` being available in the executing environment.

	### Post-Stage 7.25 — Fix startup migration for hard dedup index

	Issue found:
	- Gate 1 failure (`uq_workout_logs_set` missing) traced to `database.py:init_db()` not creating that explicit index.
	- Existing model-level unique constraint (`uq_workout_set`) did not satisfy gate logic checking `sqlite_master` for index name `uq_workout_logs_set`.

	Implemented fix:
	- Updated `database.py:init_db()` to run startup dedup for `workout_logs` on `(workout_id, exercise_id, set_number)`.
	- Dedup keeps earliest row (`MIN(id)`) and deletes remaining duplicates before index creation.
	- Added explicit idempotent migration step:
		- `CREATE UNIQUE INDEX IF NOT EXISTS uq_workout_logs_set ON workout_logs (workout_id, exercise_id, set_number)`
	- This enforces a hard DB-level uniqueness guarantee independent of importer conflict logic.

	Validation evidence:
	- `python -m py_compile database.py` passed.

## Latest Maintenance Update (2026-05-02, Conflict Gate)

- `conflict_gate.py` gate script created and syntax-validated:
	- GateRunner with 7 gates, preflight checks, and finally-block cleanup
	- Preflight verifies app reachable, `/api/exercises/conflicts` reachable, `exercise_conflicts` table present
	- Fixtures: two exercise UUIDs, old/new/canonical title strings, monkeypatched HevyClient (same pattern as `canonical_gate.py`)
	- Gate 1: seed old_title in workout_logs, import with new_title → confirm conflict row created
	- Gate 2: confirm workout_logs stores new_title post-import
	- Gate 3: GET `/api/exercises/conflicts` returns the test conflict
	- Gate 4: resolve endpoint → canonical upserted, conflict marked resolved
	- Gate 5: resolved conflict absent from GET
	- Gate 6: re-import with canonical present → no new conflict created
	- Gate 7: dismiss endpoint → resolved=True with no canonical write
	- `python -m py_compile conflict_gate.py` — no errors
- Conflict stack prerequisites still pending:
	- `ExerciseConflict` SQLAlchemy model + `init_db()` migration block in `database.py`
	- Conflict detection logic in `importer.py` (upsert on title drift, skip if already flagged)
	- Three endpoints in `main.py`: GET `/api/exercises/conflicts`, POST `…/resolve`, POST `…/dismiss`
	- Conflict review UI in `static/index.html`: Needs Review section, resolve/dismiss actions, nav badge

## Latest Maintenance Update (2026-05-02, Conflict Stack Implementation)

- `ExerciseConflict` model added to `database.py`:
	- Columns: `exercise_id` (PK), `hevy_title`, `stored_title`, `detected_at`, `resolved` (Bool, default False), `resolved_at` (nullable)
	- `init_db()` migration block: creates `exercise_conflicts` table on startup if absent
- Conflict detection added to `importer.py`:
	- Preloads `already_flagged` set (unresolved conflict exercise IDs) once per sync
	- Preloads `stored_titles` dict (most-recent `exercise_title` per `exercise_id` from `workout_logs`) via MAX(id) subquery
	- Per-exercise: if no canonical mapping, not already flagged, stored title differs from Hevy title → `db.merge(ExerciseConflict(...))`
- Three endpoints added to `main.py`:
	- `ExerciseConflictResolveInput(BaseModel)` Pydantic model with `canonical_title: str`
	- `GET /api/exercises/conflicts` → returns unresolved conflicts ordered by `detected_at desc`
	- `POST /api/exercises/conflicts/{exercise_id}/resolve` → upserts canonical, marks conflict resolved; 422 if empty title, 404 if not found
	- `POST /api/exercises/conflicts/{exercise_id}/dismiss` → marks resolved=True/resolved_at=now; idempotent; 404 if not found
- Conflict review UI added to `static/index.html`:
	- `exerciseConflictRows` and `exerciseConflictEditingId` state vars
	- Needs Review card (`#ex-conflict-card`) above canonical card; hidden by default via `style="display:none"`
	- `activateTab` exercises branch now calls `loadExerciseConflicts()` before `loadExerciseCanonical()`
	- Nav badge spans (`#ex-conflict-badge`, `#ex-conflict-badge-mobile`) with `.badge-conflict` styling on both desktop and mobile exercises buttons
	- `loadExerciseConflicts()`, `_updateExConflictBadge()`, `renderExerciseConflictTable()`, `editExerciseConflict()`, `cancelExerciseConflictEdit()`, `resolveExerciseConflict()`, `dismissExerciseConflict()` JS functions
- Validation:
	- `python -m py_compile database.py` — OK
	- `python -m py_compile importer.py` — OK
	- `python -m py_compile main.py` — OK
	- `static/index.html` JS brace balance: open=842 close=842, `<script>`/`</script>` count balanced 3/3

## Latest Maintenance Update (2026-05-02, Sync Payload + Post-Sync Conflict Query)

- Sync endpoint response simplified in `main.py`:
	- `POST /api/sync` success response now returns only:
		- `status: "complete"`
		- `synced_at: <utc iso timestamp>`
	- `new_sets` removed from sync API response payload.
- Sync UI updated in `static/index.html`:
	- `runSync()` success branch now renders `Sync complete` with the returned `synced_at` timestamp.
	- Removed set-count messaging and branching tied to `new_sets`.
	- Existing cooldown/already-running states and post-sync refresh calls remain unchanged.
- Importer conflict detection refactored in `importer.py`:
	- Removed preloads and per-loop conflict logic:
		- `already_flagged` set
		- `stored_titles` map
		- inline per-exercise `ExerciseConflict` upsert block inside import loop
	- Added `detect_exercise_conflicts(db)` and call at end of `import_hevy_data()` after set writes:
		- selects `exercise_id` values with `COUNT(DISTINCT workout_logs.exercise_title) > 1`
		- excludes canonical IDs present in `exercise_canonical`
		- excludes IDs with unresolved conflicts in `exercise_conflicts`
		- for remaining IDs, upserts conflict rows with:
			- `hevy_title` = newest by `WorkoutLog.date DESC, WorkoutLog.id DESC`
			- `stored_title` = oldest by `WorkoutLog.date ASC, WorkoutLog.id ASC`
			- `detected_at` = `datetime.utcnow()`
			- `resolved` = `False`
	- Canonical substitution logic, session modality inference, and workout_logs write path are unchanged.
- Validation evidence:
	- `python -m py_compile importer.py` — OK
	- `python -m py_compile main.py` — OK
	- `static/index.html` diagnostics — OK (`<script>`/`</script>`: 3/3, JS braces: 841/841)

## Decisions Locked

- Full-body via existing percentage fields (no `is_full_body` column).
- Primary modality approximation for mixed sessions in this phase.
- Compute-on-demand pattern EWMA and retroactive correction behavior.
- Extend `/api/training-load` instead of adding a separate recommendation endpoint.
- Strict stage gates with required pass criteria before progression.
- Local DB reset/reimport is acceptable during migration and validation.
