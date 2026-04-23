# Hevy Fatigue - Local Plan Snapshot

Last updated: 2026-04-22

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
	- relocated legacy Training Stress chart (with existing pattern/baseline controls)
- Legacy dashboard chart/table blocks removed from check-in area:
	- removed orphan `tsbZoneChart` markup
	- removed legacy `tl-wrap` card
	- removed legacy recent workouts summary table
- Workouts tab migration completed:
	- Session Verification Queue retained
	- Session Log with filtering, fatigue annotation, expandable detail views, and inline per-row edit
	- Session row panels hardened: Edit and Show Details are now mutually exclusive per row
	- Session Log default page now loads 50 rows, with API-backed Load More pagination
- Settings tab updates completed:
	- Session Processing section now includes both conditioning load scale and auto-verify confidence threshold
	- Auto-verify threshold input is populated from `/api/settings/v2` and uses placeholder `0.90`
	- Session Processing now includes local reclassification actions for existing sessions without using Hevy sync
	- Settings section spacing restored to use existing card/grid spacing tokens after inline margin regression
	- Settings tab load flow now always fetches `/api/settings/v2` values even if API-key metadata fetch fails
	- Training State Thresholds fields rehydrate from saved `app_settings` values on each Settings tab open
- Import pipeline updates completed:
	- Session modality now uses two-layer detection: title keyword pass first, then existing exercise-level fallback
	- Mixed title matches are flagged with a session note and reduced confidence to force manual review

## 3) Check-In UX (Latest Overhaul)

- Check-in card moved to first card in Today view (input before outputs).
- Form now renders immediately when today is pending; no click required.
- When today is already submitted:
	- form auto-hides
	- read-only submitted-values panel is shown
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
	- submitted collapse/read-only switch
	- no dropdowns
	- all 8 fields and group headers
	- endpoint direction labels and non-interactive endpoint text
	- mobile 375px width, no overflow, 44px touch targets, full-width submit
	- backdated date submission behavior
- Workouts/session-processing backend gate script: PASS for
	- session-processing save/load and threshold validation range
	- edit behavior preserving status (`pending` stays pending, `verified` stays verified)
	- verification path still promoting pending sessions
	- pagination `limit`/`offset` behavior
	- auto-verify policy checks (strength/hypertrophy thresholding, conditioning/cardio always pending)
- Session processing default/migration updates: PASS
	- runtime default aligned to `0.90`
	- startup seeding preserves existing user values and only seeds missing `auto_verify_confidence_threshold` with `0.90`
- Title modality detection gate script: PASS for
	- `CC4.1.2 METCON` -> conditioning at confidence `0.95`
	- `CC4.1.1 PP/PU + WOD` -> conditioning at confidence `0.95`
	- `ME Lower + METCON` -> mixed-title handling with conditioning dominant, confidence `0.70`, mixed-session note present
	- `Morning Workout` (no title keywords) -> falls through to existing exercise-level inference unchanged
	- `Hypertrophy Upper` -> hypertrophy at confidence `0.95`
	- case-insensitive title matching
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
	- default auto-verify threshold baseline confirmed at `0.90`

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

