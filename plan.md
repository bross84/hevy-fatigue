# Hevy Fatigue - Local Plan Snapshot

Last updated: 2026-05-01 (Settings refactor + diagnostics migration)

## 1) Current Product State

- Today recommendation state now uses a combined score model:
	- `combined_score = 0.80 * subjective_score + 0.20 * objective_score`
	- `subjective_score` comes from the daily check-in (fallback `5.0` when missing)
	- `objective_score` comes from 7-day session volume versus 6-month weekly average volume
- Fatigue score now excludes joint values:
	- `0.45 * tiredness + 0.30 * recovery + 0.25 * soreness`
- Joint health contributes through `recommendation_v2.joint_advisory` (upper/lower advisory and warning states), not through fatigue score weighting.
- Daily recommendation and Today cards are served from `/api/training-load` with shared frontend payload caching.

## 2) Frontend Status (Stage 7 Progress)

- Today, Trend, Workouts, Exercises, Log, Settings tabs are active in single-page `static/index.html`.
- Diagnostics page AI panel script fixes completed in `static/diagnostic.html`:
	- readiness context prompt is now built only after async data load completes inside `loadAndRender()`
	- refresh button handler now closes before `ai-input` listeners are attached, preventing delayed or duplicate listener registration
	- AI assistant JS block indentation normalized to 4-space style to match surrounding script formatting
	- AI assistant now renders markdown: `marked.js` (9.1.6) added via CDN; assistant message bubbles use `marked.parse()` instead of `escapeHtml()`; user message bubbles retain `escapeHtml()` for XSS safety
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
	- Recommendation card now shows combined-score-driven training-state label/detail text plus Subjective / Objective / Combined score tiles
	- Status card removed entirely (CHECK-IN / PENDING SESSIONS / LAST SYNC tiles removed)
	- Submitted-today check-ins now render as collapsed minimal state with `Edit / Backdate` toggle
	- Collapsed submitted state shows only success banner + `Edit / Backdate` button (no read-only values grid)
	- Toggle expands/collapses full form without saving; collapse resets form fields back to today's saved values
	- Check-in date picker now capped at today (future dates blocked) while still allowing past-date backfill
	- `todayStr()` now uses local date parts (`getFullYear/getMonth/getDate`) instead of UTC `toISOString()`, preventing timezone drift in submitted-state detection
	- `checkTodayReadiness()` is now called on every dashboard tab activation (not only on initial page load), keeping submitted-state display current
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
	- Added subtle Settings footer link to diagnostics page: `View engine diagnostics →` (small, low-contrast text, no button styling)
- Settings tab refactored to 3-card layout (2026-05-01):
	- Removed Pattern Sensitivity card from Settings tab; controls migrated to `static/diagnostic.html`
	- Removed Session Processing card from Settings tab; controls migrated to `static/diagnostic.html`
	- Settings desktop grid updated to `"api sync" / "diagnostics diagnostics"` (2-col top, full-width bottom)
	- Replaced `View engine diagnostics →` text link with a full-width card: title "Engine Diagnostics & Tweaks", explainer, and accent-coloured CTA button
	- `loadV2Settings()`, `savePatternSensitivity()`, `saveSessionProcessingSettings()`, `reclassifySessions()` removed from `static/index.html`
- Diagnostics page settings sections added (2026-05-01):
	- Added Pattern Sensitivity section to `static/diagnostic.html` with Stressed/Neutral threshold inputs, save button, and result feedback
	- Added Session Processing section to `static/diagnostic.html` with Auto-Verify Confidence Threshold input, pending and force reclassification buttons, and result feedback
	- `diagLoadV2Settings()` wired into `loadAndRender()` so inputs populate on page load and Refresh
- Diagnostics page engine snapshot updates completed:
	- Added backend endpoint `GET /api/diagnostics/snapshot` in `main.py`
	- Endpoint returns grouped snapshot payload for subjective/objective/combined score breakdowns, ATL/CTL/TSB, TSB thresholds, joint advisory (raw + current state), and last 10 session classifications
	- Objective/load volume in snapshot reuses `_session_volume()` for 7-day and 180-day aggregations (no inline `weight × reps` reimplementation)
	- Added `Engine Snapshot` section in `static/diagnostic.html` above S&C Assistant panel
	- Engine Snapshot renders grouped blocks: Score Breakdown formulas, Check-in Inputs, Volume Baseline, Training Load, Joint Advisory, TSB Thresholds, Last 10 Sessions
	- No-check-in-today state now renders a neutral placeholder while keeping available non-check-in diagnostics visible
- Import pipeline updates completed:
	- Session modality now uses two-layer detection: title keyword pass first, then existing exercise-level fallback
	- Title keyword sets include abbreviation codes (` ST`, ` HYP`, ` CON`, ` CAR`) and `strongman`
	- `+` in title with any modality keyword/code forces mixed handling (`0.70` + mixed-session note), with dominant modality chosen by first keyword position
	- Import now parses title sRPE tags in format `@N` / `@N.N` (`0..10`) and stores parsed value to `workout_sessions.srpe`
	- Verification card display title strips `@N` tag for readability while stored session title remains unchanged
	- Valid sRPE title tag is a conditioning signal when no other modality keyword/code is present (`conditioning`, confidence `0.95`)
	- Conditioning/Cardio sessions can auto-verify when confidence `>= 0.87` only if sRPE came from title tag
	- Mixed title matches are flagged with a session note and reduced confidence to force manual review
	- Sync/reclassification guard added in `importer.py`: existing `verified` sessions now use metadata-only upsert updates (date/title/time/duration/updated_at) and preserve classification fields (`modality`, `modality_confidence`, `modality_note`, `verification_status`, `verified_at`, `srpe`)

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
- Combined-score Today recommendation switch: PARTIAL VALIDATION
	- backend recommendation state now comes from combined-score thresholds instead of TSB thresholds
	- Today recommendation card renders Subjective / Objective / Combined score tiles from `recommendation_v2`
	- formula explainer line added below score tiles: `Combined = (Subjective × 80%) + (Objective Load × 20%)`
	- pattern explainer text added below pattern grid describing the 7-day verified-session basis
- Pattern dot stress label fix: DONE
	- `_stress_level_label()` in `main.py` switched from 3-bucket status string to 5-point `dots_filled` int: `1→Fresh`, `2→Min. Stress`, `3→Normal Stress`, `4→Moderate Stress`, `5→High Stress`
	- JS fallback label in `static/index.html` updated to derive from `dots_filled` using same 5-label array
	- `main.py` syntax validated with `py_compile`
	- full local route execution remains blocked in the currently configured Python interpreter because it does not have FastAPI installed
- Diagnostics snapshot + importer verified-session sync guard: PARTIAL VALIDATION
	- `importer.py` now checks for existing session by `hevy_workout_id` before upsert
	- Existing `verification_status == verified` sessions are protected from reclassification on sync
	- New endpoint `GET /api/diagnostics/snapshot` added and wired to diagnostics UI
	- Snapshot objective/load volume calculations use `_session_volume()` helper for both 7-day and 180-day windows
	- Python syntax validation passed for `importer.py` and `main.py`; static diagnostics report clean for touched HTML files
	- Full live endpoint/runtime validation remains pending in a local environment with app dependencies installed
- Nav active class hardcode fix: DONE
	- Removed hardcoded `active` class from desktop `.nav-tabs` Today button and mobile `.mobile-drawer-nav` Today button in `static/index.html`
	- Runtime `activateTab()` already manages the `active` class; no JS changes needed
- Settings grid mobile fix: DONE
	- Removed invalid `grid-template-areas: none` from `@media (max-width: 900px)` block in `static/index.html`
	- Added `grid-area: auto` resets for all 5 `.settings-card-*` children within the same breakpoint so cards stack in DOM order
- Settings CSS corruption hotfix: DONE
	- Removed stray `grid-template-areas` string literals that were incorrectly inserted into the `[data-theme="light"]` variable block
	- Restored missing `html { ... }` wrapper in the Base CSS section
	- Removed misplaced `.today-chart-*` rules that were accidentally injected inside the dark theme token block and relocated those rules to the Today section
	- Restored mobile `.today-chart-wrap` sizing rule under a proper media query block
- TSB Settings card removal: DONE
	- Removed obsolete `Training State Thresholds` card from `static/index.html`
	- Removed frontend-only JS support for `saveTrainingStateThresholds()`, the four TSB inputs, and `tsb-result`
	- Rebalanced desktop Settings grid to `api/pattern` then `session/sync`; mobile reset now applies only to remaining Settings cards
- 7-day readiness trend: PARTIAL VALIDATION
	- Added `GET /api/readiness/combined-history` in `main.py` returning fixed day-by-day history with `date`, `objective_score`, `subjective_score`, and `combined_score`
	- Historical no-check-in days now return `objective_score` plus `subjective_score=null` and `combined_score=null`
	- Added Today-tab `7-Day Readiness Trend` Chart.js card in `static/index.html` below the recommendation card and above the pattern grid
	- Chart uses null gaps, short weekday labels, y-axis `0..10`, and five readiness-zone background bands
	- Updated readiness-zone band fills for stronger contrast and clearer state separation; current palette uses deep navy / cyan / green / amber / red bands
	- Updated readiness chart x/y gridline color to `rgba(128,128,128,0.15)` for light/dark visibility parity
	- Syntax/static validation passed for `main.py` and `static/index.html`; desktop Settings layout and Today card placement verified in-browser
	- Full live API/runtime verification and true sub-900px browser rendering remain pending in an environment with the app served normally
- CSS corruption repair verification: DONE
	- `<style>` block brace audit passed: opening and closing braces are equal and running depth never goes negative
	- Static diagnostics pass for `static/index.html` reports no errors
	- Runtime style check confirms body font stack and theme colors now apply from CSS instead of fallback defaults

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

"Read plan.md first. Continue from Priority A validation with real data. Preserve the new Today-first check-in flow, Trend-owned charts, and combined-score Today recommendation model."

