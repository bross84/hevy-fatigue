# Hevy Fatigue - Local Plan Snapshot

Last updated: 2026-04-23

## 1) Current Product State

- Subjective-first fatigue model remains primary recommendation driver.
- Fatigue score now excludes joint values:
	- `0.45 * tiredness + 0.30 * recovery + 0.25 * soreness`
- Joint health contributes through `recommendation_v2.joint_advisory` (upper/lower advisory and warning states), not through fatigue score weighting.
- Daily recommendation and Today cards are served from `/api/training-load` with shared frontend payload caching.

## 2) Frontend Status (Stage 7 Progress)

- Today, Trend, Workouts, Exercises, Log, Settings tabs are active in single-page `static/index.html`.
- Trend view is now the home for chart diagnostics:
	- ATL/CTL/TSB trend chart
	- pattern ATL trend chart
	- Training Stress (Legacy) chart removed entirely (requirement 2.3)
	- Chart window behavior fixed per requirement 2.1:
		- All Trend charts now display a fixed 30-day date range ending today
		- Time Range selector (3 Day/7 Day/14 Day labels) controls chart smoothing only via trailing moving average windows
		- Date axis/x-axis labels remain constant (same 30-day span) regardless of selector choice
		- Trend tooltips now read plotted (smoothed) dataset values so tooltip numbers match line values
	- Legacy dashboard chart/table blocks removed from check-in area:
	- removed orphan `tsbZoneChart` markup
	- removed legacy `tl-wrap` card
	- removed legacy recent workouts summary table
- Workouts tab migration completed:
	- Session Verification Queue retained
	- Session Log with filtering, fatigue annotation, expandable detail views, and inline per-row edit
	- Session row panels hardened: Edit and Show Details are now mutually exclusive per row
	- Session Log default page now loads 50 rows, with API-backed Load More pagination
- Today page behavior updates completed:
	- Recommendation card now shows only training-state label and TSB-driven detail text (fatigue score/tier line removed)
	- Status card removed entirely (CHECK-IN / PENDING SESSIONS / LAST SYNC tiles removed)
	- Submitted-today check-ins now render as collapsed minimal state with `Edit / Backdate` toggle
	- Collapsed submitted state shows only success banner + `Edit / Backdate` button (no read-only values grid)
	- Toggle expands/collapses full form without saving; collapse resets form fields back to today's saved values
	- Check-in date picker now capped at today (future dates blocked) while still allowing past-date backfill
	- `todayStr()` now uses local date parts (`getFullYear/getMonth/getDate`) instead of UTC `toISOString()`, preventing timezone drift in submitted-state detection
- Settings tab updates completed:
	- Session Processing section now includes both conditioning load scale and auto-verify confidence threshold
	- Auto-verify threshold input is populated from `/api/settings/v2` and uses placeholder `0.87`
	- Session Processing now includes local reclassification actions for existing sessions without using Hevy sync
	- Settings section spacing restored to use existing card/grid spacing tokens after inline margin regression
	- Settings container now uses explicit two-column card placement:
		- left column: Hevy API Key, Pattern Sensitivity, Hevy Sync
		- right column: Training State Thresholds, Session Processing
	- Settings tab load flow now always fetches `/api/settings/v2` values even if API-key metadata fetch fails
	- Training State Thresholds fields rehydrate from saved `app_settings` values on each Settings tab open
- Import pipeline updates completed:
	- Session modality now uses two-layer detection: title keyword pass first, then existing exercise-level fallback
	- Title keyword sets include abbreviation codes (` ST`, ` HYP`, ` CON`, ` CAR`) and `strongman`
	- `+` in title with any modality keyword/code forces mixed handling (`0.70` + mixed-session note), with dominant modality chosen by first keyword position
	- Import now parses title sRPE tags in format `@N` / `@N.N` (`0..10`) and stores parsed value to `workout_sessions.srpe`
	- Verification card display title strips `@N` tag for readability while stored session title remains unchanged
	- Valid sRPE title tag is a conditioning signal when no other modality keyword/code is present (`conditioning`, confidence `0.95`)
	- Conditioning/Cardio sessions can auto-verify when confidence `>= 0.87` only if sRPE came from title tag
	- Mixed title matches are flagged with a session note and reduced confidence to force manual review

## 3) Check-In UX (Latest Overhaul)

- Check-in card moved to first card in Today view (input before outputs).
- Form now renders immediately when today is pending; no click required.
- When today is already submitted:
	- form auto-hides
	- collapsed minimal submitted panel is shown (banner + `Edit / Backdate` only)
	- no read-only values grid is shown in either collapsed or expanded modes
- Check-in controls replaced with inline 0-4 button groups for all 8 fields:
	- tiredness, recovery
	- quad/knee, hip/posterior, upper push, upper pull
	- upper joint, lower joint
- Endpoint labels implemented per field scale direction:
	- Recovery: Poor -> Full
	- Joint fields: Good -> Pain
	- Others: None -> Extreme/Severe
- Date picker remains present and supports backdated submissions.
- Submit mapping and backend endpoint behavior are unchanged.

## 4) Validation Snapshot

- Joint-advisory backend gate script: PASS.
- Trend chart relocation lifecycle checks: PASS (first activation, tab switching, refresh stability, no duplicate chart instance behavior).
- Check-in UX checks: PASS for
	- first-card placement
	- pending immediate visibility
	- submitted collapse showing only banner + `Edit / Backdate` toggle
	- no read-only values grid rendered at any point in submitted mode
	- collapse without save resets editor fields to today's canonical values
	- no dropdowns
	- all 8 fields and group headers
	- endpoint direction labels and non-interactive endpoint text
	- date picker max bound set to today (past-date backfill preserved)
	- mobile 375px width, no overflow, 44px touch targets, full-width submit
	- backdated date submission behavior
- Workouts/session-processing backend gate script: PASS for
	- session-processing save/load and threshold validation range
	- edit behavior preserving status (`pending` stays pending, `verified` stays verified)
	- verification path still promoting pending sessions
	- pagination `limit`/`offset` behavior
	- auto-verify policy checks (strength/hypertrophy thresholding; conditioning/cardio pending unless sRPE title-tag auto-verify condition is met)
- Session processing default/migration updates: PASS
	- runtime default aligned to `0.87`
	- startup migration updates legacy stored `0.90` and `0.95` values to `0.87`
	- startup seeding still fills missing `auto_verify_confidence_threshold` with `0.87`
- Title modality detection gate script: PASS for
	- `CC4.1.1(A) ST` -> strength at confidence `0.95` (auto-verifies at threshold `0.87`)
	- `CC4.1.1(A) HYP` -> hypertrophy at confidence `0.95` (auto-verifies at threshold `0.87`)
	- `CC4.1.1(A) ST + CON` -> mixed handling with confidence `0.70`, mixed-session note present, pending queue
	- `CC4.1.1(A) HYP + CON` -> mixed handling with confidence `0.70`, mixed-session note present, pending queue
	- `STRICT PRESS` -> no ` ST` false-positive match (falls through)
	- `STRONGMAN Medley` -> conditioning at confidence `0.95`
	- `METCON` -> conditioning at confidence `0.95` and remains pending
	- `CC4.1.1(A)` (no code) -> falls through to existing exercise-level inference unchanged
	- case-insensitive title matching
	- legacy threshold values `0.90` and `0.95` migrated to `0.87` on startup
- sRPE title-tag gate script: PASS for
	- `CC4.1.6 CON @7` -> `conditioning`, `srpe=7.0`, auto-verified
	- `CC4.1.6 METCON @8` -> `conditioning`, `srpe=8.0`, auto-verified
	- `Saturday WOD @6.5` -> `conditioning`, `srpe=6.5`, auto-verified
	- `CC4.1.6 METCON` (no tag) -> `srpe=null`, pending queue behavior unchanged
	- `@11` / `@abc` invalid tags ignored
	- verification-card title strips `@N` tag for display
	- case-insensitive keyword matching remains intact alongside sRPE parsing
	- `CC4.1.1(A) ST @7` remains strength-classified (sRPE parsing does not override ST modality)
	- `CC4.1.6 @7` with no other modality keywords -> `conditioning`, `srpe=7.0`, auto-verified
	- aggregate result: `SRPE_TITLE_GATES_PASS`
- Local session reclassification gate script: PASS for
	- pending sessions reclassified from current stored workout data using current classifier rules
	- verified sessions skipped during normal reclassification runs
	- force-all reclassification updates verified sessions only when explicitly requested
	- result summary counts returned as expected
	- no Hevy API import/sync path invoked during reclassification
- Settings TSB reload gate script: PASS for
	- custom TSB thresholds saved (`40`, `15`, `-20`, `-50`)
	- settings payload re-read (tab reopen equivalent) returns saved values, not defaults
	- fresh DB session re-read (page refresh equivalent) returns saved values, not defaults
	- default auto-verify threshold baseline confirmed at `0.87`
- Settings layout fix: PASS
	- explicit two-column grouping matches intended UX
	- mobile collapse remains single-column under responsive breakpoint
- Today recommendation/status cleanup: PASS
	- no rendered fatigue/tier line on recommendation card
	- no Status card markup or render path remains
	- removed dead `.today-fatigue-line` CSS definition

## 5) Open Items / Next Backlog

Priority A

- Manual visual QA on real populated workout/check-in data for Trend and Session Log realism (including inline row edit, mutual exclusion of row panels, and verified/pending filters).
- Confirm final spacing/typography rhythm in Today card stack after check-in overhaul.
- Run cross-device pass (Safari iOS + Chrome Android) for check-in button groups and endpoint labels.
- Browser click-through regression pass for Workouts:
	- verify queue -> log immediate refresh
	- Edit/Cancel/Save flows on both pending and verified rows
	- Show Details expand/collapse while edit mutual exclusion remains enforced

Priority B

- Optional cleanup of obsolete helper names/comments that still reference legacy dashboard wording.
- Add a short release checklist for pre-commit UI and endpoint regression checks.

## 6) Quick Resume Prompt

Use this when you come back:

"Read plan.md first. Continue from Priority A validation with real data. Preserve the new Today-first check-in flow, Trend-owned charts, and current subjective-first fatigue language."

