# Hevy Fatigue - Local Plan Snapshot

Last updated: 2026-05-25 (Revert readiness inversion, main.py only)

## Latest Update (2026-05-25 — Revert readiness inversion, main.py only)

- Workflow selected: Express
- Files changed: `main.py`

### Summary
- Reverted the two subjective readiness conversions in `main.py` back to the original orientation
- Higher subjective scores now once again mean more fatigue in both affected endpoints

### Changes

#### main.py
- **Updated** `get_vol_fatigue_summary(...)`:
	- `subjective_score` changed from `(1.0 - subj) * 10.0` back to `subj * 10.0`
- **Updated** `get_readiness_combined_history(...)`:
	- `subjective_score` changed from `(1.0 - _subjective_fatigue(checkin)) * 20.0` back to `_subjective_fatigue(checkin) * 20.0`

### Gate Results
- `python -m py_compile main.py`: **PASS**
- `get_errors(main.py)`: **PASS**
- Schema check: `PRAGMA table_info(daily_readiness)` via Python `sqlite3`: **PASS**
- Data-dependent API gates: **BLOCKED in this shell** because the active local database has `0` `daily_readiness` rows, so endpoint assertions tied to real check-ins and chart bands could not be executed here

## Latest Update (2026-05-24 — Spec: Recent Sessions show 7 + Workouts tab link)

- Workflow selected: Main
- Files changed: `main.py`, `static/index.html`

### Summary
- Increased backend `recent_sessions` payload cap from 5 to 7 in `get_training_load`
- Increased dashboard card render count from 3 to 7
- Made each dashboard recent-session row clickable; click now switches to Workouts tab, scrolls to matching session card, and opens details when collapsed

### Changes

#### main.py
- **Updated** `get_training_load(days, db)`:
	- `recent_sessions_data` query limit changed from `5` to `7`

#### static/index.html
- **Updated** `renderDashboardRecentSessions(payload)`:
	- Session display cap changed from `source.slice(0, 3)` to `source.slice(0, 7)`
	- Replaced row template with clickable items:
		- Adds inline `onclick="navigateToSession('...')"`
		- Preserves title, modality badge, and date/duration/sRPE metadata
- **Added** `navigateToSession(hevy_workout_id)`:
	- Activates `workouts` tab
	- Waits 100ms for DOM render
	- Resets Workouts filter to `all` so target session can be found
	- Loads session log if empty, then auto-loads additional pages while `sessionLogHasMore` until the target appears
	- Locates `.session-log-item[data-session-id="..."]`
	- Scrolls card into view and opens details if currently hidden

### Gate Results
- `python -m py_compile main.py`: **PASS**
- `get_errors(main.py, static/index.html)`: **PASS**
- API smoke test: `GET /api/training-load?days=60` returns `recent_sessions` list with `len <= 7`
- Local data note: `workout_sessions` table has `0` rows in this environment, so click-to-scroll/open UX gates require seeded/imported sessions to validate fully

## Latest Update (2026-05-24 — Spec: Dashboard Recent Sessions via /api/training-load)

- Workflow selected: Main
- Files changed: `main.py`, `static/index.html`

### Summary
- Added top-level `recent_sessions` payload to `GET /api/training-load` sourced from the latest 5 `WorkoutSession` rows
- Reverted dashboard recent-session source fallback in `renderDashboardRecentSessions(payload)` to the original three keys so `payload.recent_sessions` is primary

### Changes

#### main.py
- **Updated** `get_training_load(days, db)` near the return block:
	- Added `recent_sessions_data` query:
		- `WorkoutSession` ordered by `workout_date desc, start_time desc`, limited to 5
	- Added top-level `"recent_sessions"` to response dict with fields:
		- `hevy_workout_id`, `workout_date`, `workout_title`, `modality`, `duration_minutes`, `srpe`, `verification_status`

#### static/index.html
- **Updated** `renderDashboardRecentSessions(payload)` source selection:
	- Removed `last_10_session_classifications`
	- Restored original chain: `recent_sessions -> sessions -> today.recent_sessions -> []`

### Gate Results
- `python -m py_compile main.py`: **PASS**
- `get_errors(main.py, static/index.html)`: **PASS**
- API smoke test: `GET /api/training-load?days=60` returns `recent_sessions` key
- Local data note: `workout_sessions` table contains `0` rows in this environment, so `recent_sessions` is currently an empty list and the "at least one item" gate requires seeded/imported session data

## Latest Update (2026-05-24 — Fix 1 + Fix 2: Dashboard Recent Sessions + Pattern Breakdown)

- Workflow selected: Main
- Files changed: `static/index.html`, `main.py`

### Summary
- **Fix 1** — Dashboard Recent Sessions: Updated `renderDashboardRecentSessions()` to check `last_10_session_classifications` first before falling back to other sources
- **Fix 2** — Pattern Breakdown on Workout Card: Replaced fatigue annotation display with pattern breakdown percentages
  - Backend: Added `_compute_session_pattern_summary()` helper to query WorkoutLog+ExerciseMapping and compute pattern percentages
  - Backend: Updated `get_workout_sessions()` to include `pattern_summary` field in response
  - Frontend: Replaced `_sessionFatigueAnnotation()` to display pattern tags when available (e.g. Push 60% · Pull 40%), falls back to ATL/CTL/TSB, and returns empty string when neither available

### Changes

#### main.py
- **Added** `_compute_session_pattern_summary(hevy_workout_id: str, db: Session) -> dict` helper function above `get_workout_sessions()`
  - Queries WorkoutLog for session exercises
  - Joins to ExerciseMapping via exercise_title
  - Sums pattern percentages across all logs
  - Normalizes to percentages (knee, hip, push, pull)
  - Returns only patterns with >0%, empty dict if no mappings
- **Updated** `get_workout_sessions()` list comprehension to include:
  - `"pattern_summary": _compute_session_pattern_summary(row.hevy_workout_id, db),`

#### static/index.html
- **Updated** `renderDashboardRecentSessions(payload)` source check:
  - Now checks `last_10_session_classifications` first, then other sources
- **Replaced** `_sessionFatigueAnnotation(session)` function:
  - Checks `session.pattern_summary` first
  - If available and non-empty, renders pattern tags (e.g. "Push 60% · Pull 40%")
  - Falls back to ATL/CTL/TSB lookup from history
  - Returns empty string if no data available

### Gate Results
- `python -m py_compile main.py`: **PASS**
- `get_errors(main.py)`: **PASS** (no errors)
- `get_errors(static/index.html)`: **PASS** (no errors)
- Gate tests (manual application testing required):
  - Dashboard Recent Sessions card shows today's session after reload — no "No recent sessions found"
  - Workout card second line shows pattern breakdown e.g. Push 60% · Pull 40% instead of Fatigue 0.0
  - A session with no mapped exercises shows ATL/CTL/TSB fallback, not an empty line
  - /api/workout-sessions response for a HYP session includes pattern_summary with at least one key
  - Existing ATL/CTL/TSB values on the card are unchanged for sessions where pattern_summary is empty

## Latest Update (2026-05-24 — Mobile Exercises HTTP 404 + AI input size follow-up)

- Workflow selected: Debug
- Files changed: `static/index.html` only

### Reproduction
- On mobile, Exercise Metrics tab showed: `Failed to load exercises: HTTP 404`
- AI chat input still felt too short for comfortable entry

### Hypothesis
- Some deployments expose a legacy singular Exercise Metrics route while the current frontend uses only the plural route, and chat autosize cap plus rows=1 kept the composer visually small.

### Fixes
- Added fetch fallback in `loadExerciseMetrics(filter)`:
	- primary: `/api/exercises/metrics?...`
	- fallback on 404: `/api/exercise/metrics?...`
- Added same fallback behavior in `loadExerciseDetail(exerciseId, windowDays)`
- Increased chat composer baseline size:
	- textarea `rows` changed `1 -> 2`
	- `.ai-chat-input` `min-height` changed `56px -> 64px`
	- autosize cap changed `120px -> 180px` in `_initAIChatHandlers()`

### Gate Results
- `python -m py_compile main.py`: PASS
- JS brace audit: 1817 open / 1817 close: PASS
- Problems check (`static/index.html`, `main.py`): no errors

## Latest Update (2026-05-24 — Mobile Exercises card clipping and AI chat input UI)

- Workflow selected: Express
- Files changed: `static/index.html` only

### Summary of fix
- Added mobile-only bottom clearance for Exercise Metrics content so cards are not obscured by the fixed bottom nav
- Increased AI chat textarea minimum height for both mobile and desktop
- Added themed scrollbar styling for AI chat textarea overflow to match existing UI conventions

### CSS changes
- `@media (max-width: 767px)`:
	- `#tab-exercise-metrics { padding-bottom: calc(72px + env(safe-area-inset-bottom)); }`
	- `#exm-list { padding-bottom: calc(96px + env(safe-area-inset-bottom)); }`
- `.ai-chat-input`:
	- `padding` increased to `12px 14px`
	- `min-height` increased from `44px` to `56px`
	- `max-height` increased from `160px` to `200px`
	- added `scrollbar-width` and `scrollbar-color`
- Added `.ai-chat-input::-webkit-scrollbar*` rules (track/thumb/hover)

### Gate Results
- `python -m py_compile main.py`: PASS
- JS brace audit: 1811 open / 1811 close: PASS
- Problems check (`static/index.html`, `main.py`): no errors

## Latest Update (2026-05-24 — Per-Pattern Fatigue chart range/smoothing behavior)

- Workflow selected: Express
- Files changed: `static/index.html` only

### Summary of fix
- Changed history slice from `_trendSliceByDays()` to fixed `_trendSlice(..., 30)` so chart always spans 30 calendar days
- Replaced button values from 3/7/14 to 7/14/30 Day; default remains 7
- Remapped EWMA smoothing window from `trendSmoothingDays` to the selected `windowDays` parameter
- Removed x-axis min/max boundary logic since display window is now always 30 days

### Behavior change
- Per-Pattern chart now displays 30 days on X-axis regardless of button selection
- Buttons control the EWMA smoothing window (7, 14, or 30 days) instead of the date range
- Switching buttons now changes line smoothness without changing the date range

### Gate Results
- `python -m py_compile main.py`: PASS
- JS brace audit: 1796 open / 1796 close: PASS
- History slice: `_trendSlice(payload?.history || [], 30)` present
- Button values: 7/14/30 Day confirmed
- EWMA smoothing: `_trendRollingAvg(..., windowDays)` confirmed
- X-axis boundaries: min/max logic removed from x-axis config

## Latest Update (2026-05-24 — Spec Task B: Per-Pattern Tonnage EWMA + ATL/Tonnage Toggle)

- Workflow selected: Main
- Files changed: `static/index.html`, `plan.md`, `docs/stage-gated-plan.md`

### Task 1 — toggle state + card UI
- Added module-level `_todayPatternSignal = 'atl'` state beside `_todayPatternRange`
- Updated Per-Pattern Fatigue card markup to show a second control row for ATL/Tonnage selection
- Kept range controls independent from signal controls

### Task 2 — chart signal routing
- Updated `renderTodayPatternFatigueCard()` to pass `_todayPatternSignal` into `_renderTrendPatternChart()`
- Added delegated click handler for `#today-pattern-signal` buttons
- `_renderTrendPatternChart()` now selects either `atl` or `ton_atl` fields based on the active signal

### Task 3 — y-axis labeling
- Added a chart y-axis title that switches between `ATL` and `Tonnage (EWMA)` based on the selected signal

### Gate Results
- `python -m py_compile main.py`: PASS
- Script tag balance: 4/4: PASS
- JS audit checks: module state, `data-pattern-signal`, and `ton_atl` references present

## Latest Update (2026-05-24 — Spec Task A: Per-Pattern Fatigue Trend window control)

- Workflow selected: Main
- Files changed: `static/index.html` only

### Task 1 — `_trendSliceByDays()` date filtering
- Replaced entry-count slicing with date-based filtering using ISO date cutoff
- New behavior includes all entries whose `date >= cutoffStr` for selected window

### Task 2 — training load fetch window verification
- Verified fetch remains `'/api/training-load?days=180'` (no change required)

### Task 3 — chart boundary/control wiring
- Updated `_renderTrendPatternChart` signature to include `windowDays = 14`
- Updated today-card call site to pass `_todayPatternRange`
- Added explicit x-axis `min/max` boundaries keyed off selected window in `_renderTrendPatternChart`

### Gate Results
- `python -m py_compile main.py`: PASS
- JS brace audit: 1786 open / 1786 close: PASS
- Script tag balance: 4/4: PASS
- Problems check (`static/index.html`, `main.py`): no errors

## Latest Update (2026-05-24 — Dashboard Pattern card gauge-row refactor)

- Workflow selected: Main
- Files changed: `static/index.html` only

### Pattern card render update
- Replaced 2×2 pattern cell grid in `_renderTodayCards()` with four horizontal gauge rows (Knee, Hip, Push, Pull)
- Preserved underlying signal source (`dots_filled`, 1–5) and threshold mapping
- Pending/no-check-in state now renders muted gauge fill with `—` status per row
- Removed pattern explainer render from dashboard pattern card assignment

### CSS additions
- Added `/* ── Pattern stress gauges ── */` section after `.today-pattern-pending`
- Added gauge row/item/track/fill/status classes including threshold-specific fill/status variants

### CSS cleanup
- Removed unused legacy classes after reference sweep:
	- `.today-pattern-grid`
	- `.today-pattern-name`
	- `.today-pattern-days`
	- `.today-dots`
	- `.today-dot`
	- `.today-dot-filled`
	- `.today-pattern-level`
- Removed matching small-screen overrides for removed classes
- Kept existing `.today-pattern-*` classes still referenced by `_patternCellClass()` as requested

### Gate Results
- `python -m py_compile main.py`: PASS
- JS brace audit: 1784 open / 1784 close: PASS
- Script tag balance: 4/4: PASS
- Problems check (`static/index.html`): no errors
- Old grid class family absent (`today-pattern-grid`, `today-dot*`, `today-pattern-name/days/level`)

## Latest Update (2026-05-24 — Fatigue tab bar+line conversion + dashboard card removal)

- Workflow selected: Main
- Files changed: `static/index.html` only

### Fatigue tab charts
- Replaced `_vfRenderCharts(data)` implementation to use `_vfBuildBarLineChart()` for all three Fatigue tab charts
- Left-axis series now use daily backend fields:
	- `daily_stress`
	- `daily_tonnage`
	- `daily_set_count`
- Readiness overlay remains `rolling_readiness`

### Dashboard Training Load removal
- Removed `today-training-load-card` from dashboard HTML
- Removed `renderTodayTrainingLoadCard()` function
- Removed `_todayLoadRange` state and `_todayLoadRangeHandler` delegated listener
- Removed `_destroyTodayTrainingLoadChart()` and remaining call sites/state references
- `loadTrainingLoadCard()` still calls `renderTodayPatternFatigueCard()` and `renderDashboardVFCard()`

### Gate Results
- `python -m py_compile main.py`: PASS
- JS brace audit: 1774 open / 1774 close: PASS
- Script tag balance: 4/4: PASS
- Problems check (`static/index.html`, `main.py`): no errors
- `/api/volfatigue/summary`: daily fields present on every row; rest-day zero sample verified
- Non-zero training-day sample not verifiable in local DB because current workspace DB contains no workout sessions/workout logs

## Latest Update (2026-05-24 — Dashboard VF uses daily values + bar/line chart)

- Workflow selected: Main
- Files changed: `static/index.html` only

### Dashboard VF card update
- `renderDashboardVFCard()` now reads daily backend fields instead of rolling fields:
	- `daily_tonnage`
	- `daily_stress`
	- `daily_set_count`
- Swapped chart build from `_vfBuildChart()` to `_vfBuildBarLineChart()`
- Updated note text to describe daily values and zero-bar rest days

### Legend update
- Added inline custom legend below dashboard VF canvas
- Legend signal label and swatch color now update after chart build

### Gate Results
- Problems check (`static/index.html`): no errors
- JS brace audit: 1792 open / 1792 close: PASS
- Script tag balance: 4/4: PASS

## Latest Update (2026-05-24 — Frontend _vfBuildBarLineChart helper)

- Workflow selected: Express
- Files changed: `static/index.html` only

### Helper addition
- Added new `_vfBuildBarLineChart()` immediately before existing `_vfBuildChart()`
- Helper builds combined bar + dashed readiness line chart with:
	- integerized left-axis max
	- `Lbs` tick compaction to `k`
	- rest-day tooltip for zero bars
	- amber readiness line on right axis

### Gate Results
- Problems check (`static/index.html`): no errors
- JS brace audit: 1792 open / 1792 close: PASS
- Script tag balance: 4/4: PASS

## Latest Update (2026-05-24 — Backend daily signal fields for /api/volfatigue/summary)

- Workflow selected: Express
- Files changed: `main.py` only

### API payload expansion
- Updated `get_vol_fatigue_summary()` in `main.py`
- Added daily fields to each response row while keeping existing rolling fields intact:
	- `daily_tonnage`
	- `daily_stress`
	- `daily_set_count`
- Daily values default to zero on rest days using existing per-date lookup dicts

### Docstring update
- Replaced rolling-only description with combined daily + rolling field description
- Preserved readiness nullability note for fewer than 3 trailing check-in days

### Schema verification
- `PRAGMA table_info(workout_sessions)`: PASS
- `PRAGMA table_info(daily_readiness)`: PASS
- `PRAGMA table_info(workout_logs)`: PASS

### Gate Results
- `python -m py_compile main.py`: PASS
- Problems check (`main.py`): no errors

## Latest Update (2026-05-23 — VF custom range button-state sync)

- Workflow selected: Express
- Files changed: `static/index.html` only

### Fix — Custom button should become active when custom row opens
- Root cause: `_dvfRangeHandler` custom branch set `_dashboardVfActiveRange = 'custom'` and toggled row visibility directly, but did not re-render button group classes
- Updated custom branch to call `renderDashboardVFCard()` immediately, so `Custom` gets active styling while preserving custom row visibility

### Gate Results
- Problems check (`static/index.html`): no errors
- JS brace audit: 1757 open / 1757 close: PASS

## Latest Update (2026-05-23 — Training Load 30-day semantics correction)

- Workflow selected: Main
- Files changed: `static/index.html` only

### Correction — 30-day window vs term selector
- Reverted `_trendSlice()` to fixed 30-point behavior for the Training Load trend context
- Added `_trendSliceByDays(history, days)` helper and moved Per-Pattern range slicing to this helper so 3/7/14 controls there still change the chart window

### Training Load controls now match 3/6/12 term intent
- Updated `today-load-range` buttons from `3/7/14` to `3/6/12`
- Default term set to `6` (`let _todayLoadRange = 6`)
- `renderTodayTrainingLoadCard()` now always charts the last 30 days (`_trendSlice(payload.history)`)

### Baseline behavior in chart
- In `_renderTrendMainChart()` for `today-training-load-chart`, dotted dataset now renders rolling baseline from ATL using selected term (`_todayLoadRange`)
- Tooltip includes `Baseline (Xd)` value for the selected term

### Gate Results
- `python -m py_compile main.py`: PASS
- JS brace audit: 1757 open / 1757 close: PASS
- Problems check (`static/index.html`): no errors

## Latest Update (2026-05-23 — Range slicing + calendar icon + VF contrast)

- Workflow selected: Main
- Files changed: `static/index.html` only

### Fix 1 — Training Load and Per-Pattern range buttons now affect chart window
- Root cause: `_trendSlice(history, days)` ignored `days` and always returned up to 30 points
- Updated `_trendSlice()` to honor `days` (`3/7/14` etc.) with numeric guard logic and proper tail slicing

### Fix 2 — Dark mode date picker icon visibility
- Added dark-theme WebKit date input styling so calendar indicator is no longer black on dark backgrounds
- Added dark-theme datetime edit text color alignment with `var(--text)`

### Fix 3 — VF Sets chart readability
- In `_vfBuildChart()`, added `readinessColor` fallback logic so readiness line changes to `c.accent` when left series uses `c.push` (sets), preventing same-color green overlap

### Gate Results
- `python -m py_compile main.py`: PASS
- JS brace audit: 1752 open / 1752 close: PASS
- Problems check (`static/index.html`): no errors

## Latest Update (2026-05-23 — VF catch/listeners/CSS active-state hotfix)

- Workflow selected: Main
- Files changed: `static/index.html` only

### Fix 1 — `_dashboardVfSignal` state
- Verified `let _dashboardVfSignal = 'tonnage';` already exists in module-level state (line ~3456), so no duplicate declaration added

### Fix 2 — Dashboard VF catch preserves card shell
- Updated `renderDashboardVFCard()` catch to `catch (err)` with `console.error('Dashboard VF error:', err)`
- Replaced full-card overwrite with targeted `.vf-chart-wrap` error content so signal/range controls stay intact during failures

### Fix 3 — Dashboard VF listeners moved to delegated handlers
- Removed in-function listeners for `dashboard-vf-signal-btns`, `dashboard-vf-range-btns`, and `dashboard-vf-custom-apply`
- Added one-time document-delegated handlers after function:
	- `_dvfSignalHandler`
	- `_dvfRangeHandler`
	- `_dvfCustomApplyHandler`

### Fix 4 — Active secondary button styling
- Added `.btn-secondary.active` rule after `.btn-secondary:hover`:
	- `background: var(--accent-sub)`
	- `border-color: var(--accent)`
	- `color: var(--accent)`
	- `font-weight: 600`

### Gate Results
- `python -m py_compile main.py`: PASS
- JS brace audit: 1750 open / 1750 close: PASS
- Problems check (`static/index.html`): no errors
- Verified no in-function VF `addEventListener` calls remain
- Verified delegated handlers and catch-shell behavior strings present

## Latest Update (2026-05-23 — Fixes 1/2/3: Y-Axis Float, Range Delegation, Mobile Padding)

- Workflow selected: Main
- Files changed: `static/index.html` only

### Fix 1 — Y-Axis Float Precision
- `_vfBuildChart()`: wrapped `maxLeft` in `Math.ceil()` and `max: Math.ceil(maxLeft * 1.1)` — eliminates floating-point display artifacts (e.g. 55.000000000000010) on Set Count axis

### Fix 2 — Range Button Listener Accumulation
- Removed inline `addEventListener` from inside `renderTodayTrainingLoadCard()` (success path after `_renderTrendMainChart`)
- Added `document.addEventListener('click', async function _todayLoadRangeHandler...)` after function closing brace — targets `#today-load-range button[data-load-range]` via delegation; fires once, survives DOM replacement
- Same pattern for `renderTodayPatternFatigueCard()` — removed inline listener, added `_todayPatternRangeHandler` document delegation after function

### Fix 3 — Mobile Dead Space / Padding Override
- `@media (max-width: 767px)` block: added `main { padding: 16px 14px 90px !important; }` to override the later-declared `@media (max-width: 640px)` rule that was setting `padding: 74px 14px 12px` (top dead space + too little bottom padding)

### Gate Results
- `python -m py_compile main.py`: PASS
- JS brace audit: 1749 open / 1749 close: PASS
- Script tags: 4/4: PASS

## Latest Update (2026-05-23 — Issues 1/2/3: VF Signal Toggle, Duplicate Listeners, Mobile Padding)

- Workflow selected: Main
- Files changed: `static/index.html` only

### Issue 1 — Dashboard VF Card Signal Toggle
- Added `let _dashboardVfSignal = 'tonnage';` state variable after `_dashboardVfActiveRange`
- Replaced `renderDashboardVFCard()` — now renders 3 signal buttons (Tonnage · RPE Load · Sets), Tonnage active by default
- Signal buttons use `data-dvf-signal` attribute; toggle re-renders card with correct field (`rolling_tonnage` / `rolling_stress` / `rolling_set_count`) and color (`c.warn` / `c.accent` / `c.push`)
- Fixed field name bug: old code used `rolling_stress_load` (wrong); new code uses `rolling_stress` (matches `/api/volfatigue/summary` response)
- Note text updates per signal; custom-range inputs preserve state across renders

### Issue 2 — Duplicate Event Listeners Removed
- `renderTodayTrainingLoadCard()`: removed listener from empty-state early-return path; kept single listener in success path (calls `renderTodayTrainingLoadCard()`)
- `renderTodayPatternFatigueCard()`: same — removed duplicate listener from empty-state path; kept success-path listener (calls `renderTodayPatternFatigueCard()`)

### Issue 3 — Mobile Bottom Padding
- `@media (max-width: 767px)` `main` block: `padding-bottom` updated from 76px → 90px

### Gate Results
- `python -m py_compile main.py`: PASS
- JS brace audit: 1748 open / 1748 close: PASS
- Script tags: 4/4: PASS

## Latest Update (2026-05-23 — Design System C2: Nav Restructure)

- Workflow selected: Main
- Files changed: `static/index.html` only
- Removed old mobile hamburger/drawer CSS blocks (`.mobile-menu-btn`, `.mobile-nav-overlay`, `.mobile-nav-drawer`, `.mobile-drawer-nav`)
- Updated `nav` rule: `padding: 0 24px`, `gap: 8px`, `height: 52px`; added `white-space: nowrap` to `.nav-tab`
- Added bottom nav CSS section (`.bottom-nav`, `.bottom-nav-btn`, `.bottom-nav-items`)
- Added bottom sheet CSS section (`.bottom-sheet-scrim`, `.bottom-sheet`, `.bottom-sheet-items`, `.bottom-sheet-item`)
- Replaced `@media (max-width: 767px)` block: top nav hidden, bottom nav shown, `padding-bottom: 76px`
- Replaced `<nav>` HTML: logo left, 8 tabs center (Dashboard/Exercises/Workouts/AI/Fatigue/Log/Settings/Patterns), theme toggle right
- Tab renames: "Today" → "Dashboard", "Trend" → "Fatigue" (labels only; `data-tab` values unchanged)
- Removed `<div class="mobile-nav-overlay">` and `<aside class="mobile-nav-drawer">` elements
- Added `<nav class="bottom-nav">` with 5 items (Dashboard/Exercises/Workouts/AI/More) after closing `</nav>`
- Added bottom sheet with Fatigue/Log/Settings/Patterns/Docs
- Removed `setMobileNavOpen()` JS function
- Added `setBottomSheetOpen()`, bottom nav btn listeners, More/scrim/sheet-item listeners
- Updated `activateTab()`: calls `setBottomSheetOpen(false)`, updates `.bottom-nav-btn[data-tab]` active states
- `tab-dashboard` reference in `applyTheme()` confirmed unchanged
- py_compile: PASS; brace audit: 1678/1678; script tags: 4/4

## Previous Update (2026-05-23 — Design System C1: Replace color palette)

- Workflow selected: Express
- Files changed: `static/index.html` only
- Dark theme: `--bg #0F172A`, `--card #111827`, `--accent #3772FF` + new tokens `--card-raised`, `--border-mid`, `--accent-light`
- Light theme: `--bg #F1F5F9`, `--card #FFFFFF`, `--accent #3772FF` + matching new tokens
- Updated THEME TOKENS comment block
- `themeColors()` now returns `accentLight`, `warn`, `danger` keys
- `color: #fff` on `.btn-primary` and `.settings-diag-cta` confirmed correct (both sit on `background: var(--accent)`)
- `tab-dashboard` reference in `applyTheme()` confirmed unchanged
- py_compile: PASS

## Previous Update (2026-05-23, Tasks 2 & 3 — Vol-Fatigue 3-chart expansion + Today card range selectors)

- Workflow selected: Main
- No schema changes; index.html only (besides plan files)

### Task 2 — HTML: Replace single chart card with three
- Removed `<div class="vf-card" id="vf-chart-card">` (old single Vol-Fatigue Correlation card)
- Added three separate `vf-card` divs with IDs: `vf-chart-rpe`, `vf-chart-tonnage`, `vf-chart-sets`
- Each card has: card-title, vf-chart-wrap with named canvas, vf-chart-note
- Canvas IDs: `vf-chart-rpe-canvas`, `vf-chart-tonnage-canvas`, `vf-chart-sets-canvas`

### Task 3 — JS: Three chart instances + helper + Today card range selectors
- Replaced `let _vfChart = null` with three module-level vars: `_vfChartRpe`, `_vfChartTonnage`, `_vfChartSets`
- Updated `_vfDestroyChart()` to destroy all three instances
- Updated `renderVolFatigueView()` show/hide to toggle all three card IDs instead of old `vf-chart-card`
- Added `_vfBuildChart(canvasId, leftData, leftLabel, leftColor, leftAxisTitle, readinessData, labels, rawData)` helper
  - Dual Y-axes: left for primary metric, right for readiness (fixed 0-10)
  - Uses `_trendChartBaseOptions()` as base; `grid.drawOnChartArea: false` on right axis
- Added `_vfRenderCharts(data)` replacing `_vfRenderChart(data)`:
  - RPE chart: `c.accent` color
  - Tonnage chart: `c.quad` color (c.warn does not exist in themeColors)
  - Sets chart: `c.posterior` color
- Added `let _todayLoadRange = 7` module state
- Updated `renderTodayTrainingLoadCard()`: range row with 3/7/14 day buttons; wires click listener; uses `_todayLoadRange`
- Added `let _todayPatternRange = 7` module state
- Updated `renderTodayPatternFatigueCard()`: same range row pattern; uses `_todayPatternRange`
- Task 4 (CSS): No changes needed — `.trend-range` and `.btn.btn-secondary` already exist

### Validation
- Brace balance: 1666/1666 BALANCED
- Script tag balance: 4/4 BALANCED
- No residual references to old `vf-chart-card` ID or `_vfChart` single-instance
- py_compile: N/A (JS-only changes)

## Previous Update (2026-05-23, Task 1 — Backend /api/volfatigue/summary five fixes)

- Workflow selected: Express
- Schema verification completed with PRAGMA table_info on workout_sessions, workout_logs, daily_readiness
- Fix 1: Readiness scale corrected from 0-20 to 0-10 in endpoint logic
	- Changed from subjective_score = subj * 20.0
	- To subjective_score = round(subj * 10.0, 2)
- Fix 2: Added per-day tonnage and set count lookups
	- New dicts: tonnage_by_date, set_count_by_date
	- Added WorkoutLog join query to WorkoutSession via workout_logs.workout_id == workout_sessions.hevy_workout_id
	- Date filter uses lookback_start through end
	- Includes all sessions (no modality filter)
- Fix 3: Added rolling 7-day tonnage and set count in per-day loop
	- rolling_tonnage accumulates tonnage_by_date over trailing 7 days
	- rolling_set_count accumulates set_count_by_date over trailing 7 days
- Fix 4: Added response fields
	- rolling_tonnage (rounded to 1 decimal)
	- rolling_set_count (integer)
- Fix 5: Updated endpoint docstring wording to include stress load, raw tonnage, set count, and readiness with rolling 7-day sums/averages
- Validation
	- python -m py_compile main.py: PASS
	- read/problems on main.py: No errors
- Scope check
	- No schema changes
	- Out-of-scope files untouched in this task


- Workflow selected: Express
- Schema verification completed with PRAGMA table_info on workout_sessions, workout_logs, daily_readiness
- Fix 1: Readiness scale corrected from 0-20 to 0-10 in endpoint logic
	- Changed from subjective_score = subj * 20.0
	- To subjective_score = round(subj * 10.0, 2)
- Fix 2: Added per-day tonnage and set count lookups
	- New dicts: tonnage_by_date, set_count_by_date
	- Added WorkoutLog join query to WorkoutSession via workout_logs.workout_id == workout_sessions.hevy_workout_id
	- Date filter uses lookback_start through end
	- Includes all sessions (no modality filter)
- Fix 3: Added rolling 7-day tonnage and set count in per-day loop
	- rolling_tonnage accumulates tonnage_by_date over trailing 7 days
	- rolling_set_count accumulates set_count_by_date over trailing 7 days
- Fix 4: Added response fields
	- rolling_tonnage (rounded to 1 decimal)
	- rolling_set_count (integer)
- Fix 5: Updated endpoint docstring wording to include stress load, raw tonnage, set count, and readiness with rolling 7-day sums/averages
- Validation
	- python -m py_compile main.py: PASS
	- read/problems on main.py: No errors
- Scope check
	- No schema changes
	- Out-of-scope files untouched in this task

## Latest Update (2026-05-22, Spec B Tasks 4 & 5 — Vol-Fatigue Correlation JavaScript + Destroy)

- **Task 4 — JavaScript**: Implemented complete `// ═══ Vol-Fatigue Correlation Tab ════` section (lines 6668–6845)
- **Module state**: `_vfChart` (Chart.js instance), `_vfActiveRange` (default 4 weeks), `_vfCustomStart`/`_vfCustomEnd` (ISO date strings)
- **Helper `_vfDateRange()`**: Computes `{ start, end }` ISO strings — if numeric range, calculates `endDate - (range * 7 days)`; if 'custom', returns stored custom dates
- **Helper `_vfDestroyChart()`**: Safely destroys existing `_vfChart` instance and sets to null
- **Main `renderVolFatigueView()`**: Async function — calls `_vfDateRange()`, fetches `/api/volfatigue/summary?start_date=${start}&end_date=${end}`, handles errors, shows empty state on error/no data, otherwise calls `_vfRenderChart(data)`
- **Chart render `_vfRenderChart(data)`**: Chart.js line chart with two datasets + dual Y-axes:
  - Dataset 1: "Rolling Stress Load" — data from `rolling_stress` field, color `var(--accent)`, Y axis "y" (left), auto-scaled 0 to max*1.1
  - Dataset 2: "Rolling Readiness" — data from `rolling_readiness` field, color `var(--success)`, Y axis "y1" (right), fixed 0-10 scale
  - Both datasets: `spanGaps: false`, tension: 0.35, pointRadius: 3
  - X-axis labels: `_dateLabel()` (MMM D format), maxTicksLimit: 10
  - Tooltip: Shows both values; formats stress/readiness to 1 decimal, shows "—" for null readiness
  - Uses `_trendChartBaseOptions()` as base config
- **Event wiring**: Range buttons (`[data-vf-range]`) — toggle `.active` class, if custom show `#vf-custom-range`, else set `_vfActiveRange` and call `renderVolFatigueView()`
- **Event wiring**: Custom Apply button (`#vf-custom-apply`) — validates start/end dates, stores in `_vfCustomStart`/`_vfCustomEnd`, calls `renderVolFatigueView()`
- **Tab activation**: Updated `renderTrendView()` to call `renderVolFatigueView()`
- **Task 5 — Destroy**: Added `_vfDestroyChart();` call to `_destroyTrendCharts()` (line 6447)
- **Validation**: Syntax balanced (1653 braces, 4 script tags); Python syntax OK

## Latest Update (2026-05-22, Spec B Task 3 — Vol-Fatigue Correlation CSS Spacing Fix)
- **.vf-card**: Styled as card container matching .today-card pattern — var(--card) background, var(--border) border, border-radius: 10px, padding: 14px
- **.vf-range-row**: Flexbox button group — display: flex, flex-wrap: wrap, gap: 8px, margin-top: 8px
- **.vf-custom-range**: Flexbox date input container — align-items: center, gap: 8px, margin-top: 12px, flex-wrap: wrap
- **.vf-date-sep**: Separator text — color: var(--muted), font-size: 0.85rem
- **.vf-chart-wrap**: Canvas wrapper — position: relative, height: 260px, margin-top: 12px
- **.vf-chart-note**: Explanatory text below chart — font-size: 0.78rem, color: var(--muted), margin-top: 6px
- **.vf-empty**: Empty state message — padding: 32px 16px, text-align: center, color: var(--muted)
- **Media Query**: @media (max-width: 900px) — .vf-chart-wrap height reduced to 220px for smaller screens
- **CSS Variables**: All rules use only var(--card), var(--border), var(--muted) tokens — no hardcoded hex values
- **Validation**: HTML/JS syntax balanced (1603 braces, 4 script tags); CSS section properly placed before </style>

## Latest Update (2026-05-22, Spec B Task 2 — Vol-Fatigue Correlation Frontend HTML)

- **Task 2**: Populated `<div id="trend-wrap"></div>` with complete Vol-Fatigue Correlation UI structure
- **Block Selector Card** (#vf-range-card): "Block Window" title with four preset buttons (4/8/12 Weeks, Custom) plus hidden custom date range inputs
- **Custom Range** (#vf-custom-range, initially hidden): Two date inputs (start/end) with "Apply" button, toggled via Custom button click
- **Chart Card** (#vf-chart-card): Title "Vol-Fatigue Correlation" with canvas element (#vf-chart) and explanatory note about rolling 7-day metrics and missing data
- **Empty State** (#vf-empty, initially hidden): Shown when no data available; message prompts user to log workouts and check-ins
- **CSS Classes**: .vf-card (container), .vf-range-row (button group), .vf-custom-range (date inputs), .vf-chart-wrap (canvas wrapper), .vf-date-sep (separator text), .vf-chart-note (explanatory text), .vf-empty (empty state message)
- **Buttons**: data-vf-range attribute on preset buttons for range selection handler (4, 8, 12, custom values)
- **Structure**: 3-card layout within trend-wrap: range selector at top, chart in middle, empty state overlay (display:none)
- **Validation**: HTML/JS syntax balanced (1594 braces, 4 script tags); all key elements verified present

## Latest Update (2026-05-22, Spec B Task 1 — Vol-Fatigue Correlation Backend Endpoint)

- **Task 1**: Implemented `GET /api/volfatigue/summary` endpoint in main.py
- **Query Parameters**: `start_date` (ISO format, default: 28 days ago), `end_date` (ISO format, default: today)
- **Date Spine**: Generates every calendar date from start_date to end_date inclusive
- **Session Stress**: Pulls all sessions where `modality IN (strength, hypertrophy, conditioning, cardio)` within window. Computes per-date stress as sum of (central + peripheral) stress scores from `calculate_stress_scores()`.
- **Rolling Stress**: 7-day trailing sum per date (current day + 6 prior days). Never null — returns 0.0 when no sessions in window.
- **Readiness Score**: Computed from `DailyReadiness` entries using `_subjective_fatigue() * 20.0` to get 0-20 scale.
- **Rolling Readiness**: 7-day trailing average per date. Returns null if fewer than 3 of the 7 days have check-in data.
- **Response Format**: `{ start_date, end_date, data: [{ date, rolling_stress, rolling_readiness, session_count }, ...] }`
- **Placement**: Added after `/api/diagnostics/snapshot` endpoint, uses existing SQLAlchemy session pattern and `Depends(get_db)`.
- **Validation**: Compiled successfully with `python -m py_compile main.py`

## Latest Update (2026-05-22, Spec A Tasks 6 & 7 — Trend Tab Clear + CSS Cleanup)

- **Task 6**: Cleared the Trend tab HTML completely, leaving only `<section id="tab-trend"><div id="trend-wrap"></div></section>`. Removed all chart cards, time range buttons, canvases, and empty state elements.
- **Task 6**: Gutted `renderTrendView()` function to a no-op stub with comment reserving it for future Vol-Fatigue Correlation feature. All existing event listeners continue to call the stub without errors.
- **Task 6**: Updated `_destroyTrendCharts()` to only destroy Today page chart instances (`todayTrainingLoadChart`, `todayPatternFatigueChart`). Removed destruction of trend tab instances since trend-main-chart and trend-pattern-chart canvases no longer exist.
- **Task 7**: Removed orphaned CSS classes: `.trend-wrap`, `.trend-chart-card`, `.trend-range`, `.trend-range .btn`, `.trend-range .btn.active`, `.trend-note`, `.trend-empty`. Updated media queries to remove `.trend-range` responsive rules.
- **Task 7**: Preserved `.trend-chart-wrap` CSS class since it's used by the Movement Trend chart in the Workouts tab.
- **Spec A fully complete** — All tasks 1-7 (reorder, remove, add cards, wire, destroy, clear Trend tab, CSS cleanup) implemented end-to-end.

## Latest Update (2026-05-22, Spec A Tasks 4 & 5 — Card Wiring + Destroy Logic)

- **Task 4**: Updated `loadTrainingLoadCard()` to call `renderTodayTrainingLoadCard()` and `renderTodayPatternFatigueCard()` after the readiness chart render (lines 6122-6123). Both functions reuse the cached training load payload via `ensureTrainingLoadPayload()` — no additional network requests.
- **Task 5**: Updated `_destroyTrendCharts()` to also destroy the new Today page chart instances (`todayTrainingLoadChart` and `todayPatternFatigueChart`). This ensures proper cleanup when the Trend tab rerenders or when the app re-initializes.
- Both tasks complete; Spec A (Tasks 1-5) fully implemented.

## Latest Update (2026-05-22, Spec A Task 3 — Today Page New Chart Cards)

- Added two new card HTML elements to `#today-wrap` in `static/index.html`: `#today-training-load-card` and `#today-pattern-fatigue-card`.
- Updated `_renderTrendMainChart(history, thresholds)` signature to accept optional `canvasId` parameter with default `'trend-main-chart'`.
- Updated `_renderTrendPatternChart(history)` signature to accept optional `canvasId` parameter with default `'trend-pattern-chart'`.
- Modified both chart render functions to conditionally assign chart instances to appropriate global variables (`trendMainChart`, `todayTrainingLoadChart`, `trendPatternChart`, `todayPatternFatigueChart`) based on canvas ID.
- Created `renderTodayTrainingLoadCard()` async function that fetches training load data, slices to 30 days, renders ATL/CTL/TSB trend using `_renderTrendMainChart()` with 'today-training-load-chart' canvas ID, with card title and note.
- Created `renderTodayPatternFatigueCard()` async function that fetches training load data, checks for pattern loads, renders per-pattern fatigue trend using `_renderTrendPatternChart()` with 'today-pattern-fatigue-chart' canvas ID.
- Added global chart variables `todayTrainingLoadChart` and `todayPatternFatigueChart` to track instances.
- Added `_destroyTodayTrainingLoadChart()` and `_destroyTodayPatternFatigueChart()` helper functions for cleanup.
- Updated `loadTrainingLoadCard()` to call both new render functions after rendering readiness chart.
- Final DOM order: checkin → state → pattern → readiness-trend → training-load → pattern-fatigue → joint.

## Latest Update (2026-05-22, Spec A Task 1 — Today Page Card Reorder + Metrics Removal)

- Reordered cards within `#today-wrap` in `static/index.html`: moved `#today-pattern-card` up before `#today-readiness-trend-card` to match new layout spec.
- Removed `#today-metrics-card` HTML element entirely from the DOM.
- Removed all JavaScript references to `today-metrics-card`: deleted rendering code from `_renderTodayCards()` function and no-data fallback from `loadTrainingLoadCard()` catch block.
- Final DOM order (Task 1 complete): `#today-checkin-card` → `#today-state-card` → `#today-pattern-card` → `#today-readiness-trend-card` → `#today-joint-card`.
- Task 2 (Trend tab content) and Task 3 (new cards) pending.

## Latest Update (2026-05-22, Settings Mobile Layout Fix)

- Updated the Settings tab layout CSS in `static/index.html` so the four Settings cards render as a fixed two-column grid instead of expanding to three columns on wider screens.
- Added `min-width: 0` handling to settings cards, key rows, and AI settings fields so the AI key row no longer widens the grid on narrow viewports.
- Added a narrow-width collapse at `780px` so the Settings tab switches directly from two columns to one column when space gets tight.
- Kept the narrow-width key-row wrapping so the API-key toggle buttons drop below the input instead of forcing overflow.
- Validation: editor diagnostics report no errors in `static/index.html`.

## Latest Update (2026-05-21, Docs Weighting Visibility Clarification)

- Updated `static/docs.html` to add a dedicated user-facing weighting breakdown table under the check-in formula section.
- Added explicit percentage and max-point contributions for tiredness (45%, 9.0), perceived recovery (30%, 6.0), and soreness composite (25%, 5.0).
- Added explicit note that each individual soreness field contributes equally within the soreness composite (up to 1.25 points each).

## Latest Update (2026-05-21, Backlog Closure — Docs Schema Bug)

- Updated `docs/backlog.md` to mark the docs schema mismatch as completed.
- Removed the `21MAY2026` docs schema item from Open Bugs and added it to the closed/completed decisions table with completion details.

## Latest Update (2026-05-21, Docs Accuracy Corrective Pass)

- Updated `static/docs.html` check-in schema section to match the live backend fields and scale: `tiredness`, `perceived_recovery`, four pattern soreness fields, and `joint_upper/joint_lower` on a 0-4 input range.
- Replaced the stale 1-10 inversion formula with the implemented subjective-fatigue calculation used in `main.py` (`0.45*t + 0.30*r + 0.25*s`, scaled to 0-20).
- Updated the TSB training-state section labels and threshold table to match current runtime labels: Underloaded, Slightly Fresh, Balanced, Slightly Fatigued, Fatigued.
- Updated the joint advisory section to describe current 0-4 scoring and the implemented advisory/warning levels.
- Validation target: static diagnostics clean for `static/docs.html`; no structure-breaking HTML edits.

## Latest Update (2026-05-20, Exercise Metrics Tooltip Raw Date Source)

- Updated `static/index.html` chart builders (`_exmBuildLineChart` and `_exmBuildBarChart`) to use object dataset points in Chart.js: `data: points.map(p => ({ x: p.date, y: p.value }))`.
- Changed tooltip title callback to use `items[0].raw.x` (raw dataset date) and format it as `MMM D, YYYY`, with safe fallback to label when raw date is unavailable.
- Kept x-axis display labels user-friendly by formatting stored raw date labels with a tick callback (`_dateLabel(this.getLabelForValue(value))`).
- This single shared-builder change covers all three exercise metrics charts: max weight, avg volume/set, and session volume.

## Latest Update (2026-05-20, Exercise Metrics Tooltip Year Formatting)

- Updated exercise metrics chart builders in `static/index.html` (`_exmBuildLineChart` and `_exmBuildBarChart`) to override Chart.js tooltip title formatting with full date including year.
- Added tooltip title callback using `new Date(items[0].label + 'T00:00:00')` and `toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })`.
- This applies to all three exercise detail charts (max weight, avg volume/set, session volume) through the shared builders.
- Validation: inline JS extraction + `node --check` passed; static diagnostics report no errors in `static/index.html`.

## Latest Update (2026-05-20, Exercise Metrics Card Onclick Quote Fix)

- Updated `filterAndRenderExerciseList()` card markup in `static/index.html` so `onclick` passes `exercise_id` with single quotes inside the attribute: `loadExerciseDetail('${ex.exercise_id}')`.
- This prevents HTML attribute parsing breakage caused by nested double quotes and restores click-through behavior for exercise detail cards.
- Validation: inline JS extraction + `node --check` passed; static diagnostics report no errors in `static/index.html`.

## Latest Update (2026-05-20, Documentation Refresh)

- Updated `static/docs.html` to reflect the current source values and UI structure for check-in scoring, stress pathways, movement pattern dots, fatigue display, readiness trend, AI assistant, and exercise metrics.
- Added the new pending-state, exercise metrics, readiness trend, and AI assistant sections, plus the corresponding sidebar links.
- Kept the changes scope-limited to documentation and validated the file for structural correctness.

## Latest Update (2026-05-19, Exercise Metrics Feature — Phase 5: CSS)

- Added a clearly marked `/* === EXERCISE METRICS TAB === */` stylesheet section in `static/index.html`.
- Aligned the exercise metrics styles to the requested `exm-*` selectors: header, search, filter buttons, summary, list cards, detail view, back button, stats row, PR pills, window toggle, and chart grid.
- Kept all color usage on theme variables / `color-mix(...)`; no hardcoded hex values were introduced in the new section.
- Updated the detail-view markup/classes to use the new selector names so the CSS applies cleanly.

## Latest Update (2026-05-19, Exercise Metrics Feature — Phase 4: Frontend Detail View)

- Added CSS for `.exm-detail-header/title/last`, `.exm-detail-sesscount`, `.exm-stats-row`, `.exm-top-sets-section/table`, `.exm-pr-section/list/item/label/value`, `.exm-window-toggle/btn`, `.exm-chart-grid`, `.exm-chart-wrap/full/canvas-wrap`; with `@media (max-width:900px)` stack override.
- Added `exmCharts` object and `_exmCurrentExerciseId` module-level state.
- Added `_exmDestroyCharts()`, `_exmFmtVal()`, `_exmBuildLineChart()`, `_exmBuildBarChart()` helpers.
- Replaced Phase 3 stub with full `loadExerciseDetail(exerciseId, windowDays=0)`: fetches API, builds header/stats/top-sets/PRs/window-toggle/chart canvases HTML, then renders three Chart.js instances (max weight line, avg vol/set line, session volume bar).
- Added `_exmWindowClick(days)` to re-call detail with new window.
- Updated back-button listener to call `_exmDestroyCharts()` before hiding detail.

## Previous Update (2026-05-19, Exercise Metrics Feature — Phases 1, 2 & 3)

- Fixed Phase 1 bug: `data-tab` on new nav buttons corrected from `tab-exercise-metrics` → `exercise-metrics` so `activateTab` resolves `id="tab-exercise-metrics"` correctly.
- Added CSS block for `.exm-header`, `#exm-search`, `.exm-filter-btn`, `.exm-summary`, `#exm-list`, `.exm-card`, `.exm-card-left/.title/.meta`, `.exm-chevron`, `.exm-detail-view`, `#exm-back-btn`.
- Hooked `activateTab` to call `loadExerciseMetrics('all')` when `exercise-metrics` tab activates.
- Added `loadExerciseMetrics(filter)`: fetches `/api/exercises/metrics`, stores full list in `_exmAllExercises`, renders summary (`Total: N · Active: N`), then calls `filterAndRenderExerciseList()`.
- Added `filterAndRenderExerciseList()`: client-side filter by active button state and case-insensitive search on title; re-renders `#exm-list`.
- Days formatting: Today / Yesterday / X days ago / X weeks ago (rounded, threshold 14 days).
- Pattern pills use existing `.chip-quad/posterior/push/pull/cond` CSS classes.
- Filter button click handler toggles `.active` and calls `filterAndRenderExerciseList()`.
- Search input fires `filterAndRenderExerciseList` on `input` event.
- `loadExerciseDetail(exerciseId)` stub: hides list+header, shows detail panel. Back button reverses.

## Previous Update (2026-05-19, Exercise Metrics Feature — Phases 1 & 2)

- Phase 1 — Nav & scaffold (`static/index.html`):
	- Renamed existing `data-tab="exercises"` button label from "Exercises" → "Patterns" in both desktop `.nav-tabs` and mobile `.mobile-drawer-nav`. `data-tab` and badge spans unchanged.
	- Added new `<button class="nav-tab" data-tab="tab-exercise-metrics">Exercises</button>` before the Patterns button in both navs.
	- Added `<section id="tab-exercise-metrics" class="tab-content">` shell with `.exm-header`, `#exm-list`, and `#exm-detail` inner structure.
- Phase 2 — Backend endpoint (`main.py`):
	- Added helper `_derive_pattern(...)` that converts exercise_mappings pct columns to a human-readable label (Knee/Hip/Push/Pull/Conditioning).
	- Added `GET /api/exercises/metrics` endpoint supporting list mode and detail mode via optional `exercise_id` param.
	- List mode: returns all exercises from workout_logs joined to workout_sessions, exercise_canonical, exercise_mappings; sorted by most recent session; supports `filter=active` (56-day window).
	- Detail mode: returns personal records (Brzycki 1RM, best set volume, max weight), top 3 best sets, and three chart series (max_weight_over_time, avg_volume_per_set, session_volume) with optional `window_days` filter.
	- All queries use raw SQLAlchemy `text(...)`. `py_compile` passed.

## Previous Maintenance Update (2026-05-19, Training Load Performance Phases 1-3)

- Implemented Phase 1 in `main.py` to eliminate duplicate stress-score recomputation during `GET /api/training-load`:
	- `_compute_training_load(...)` now returns precomputed `stress_by_date` and `pattern_stress_by_date` maps.
	- `_pattern_last_loaded_dates(...)` accepts and uses precomputed pattern maps on the hot path.
	- `get_training_load(...)` and `_build_recommendation_v2(...)` now thread those maps forward.
- Implemented Phase 2 in `main.py` to remove `_session_volume` N+1 usage inside `get_training_load(...)`:
	- replaced per-session volume loops with grouped `workout_logs` aggregation by `workout_id` for both 7-day and 6-month windows.
	- switched volume assembly to dictionary lookups with `0.0` default.
- Implemented Phase 3 in `main.py` to remove repeated per-date `app_settings` reads in stress scoring:
	- updated `calculate_stress_scores(...)` to accept `conditioning_scale` and `hyp_scale` keyword args with fallback defaults.
	- `_compute_training_load(...)` now fetches scale settings once via settings dict and passes constants into each per-date stress call.
	- `_pattern_last_loaded_dates(...)` now applies a 330-day floor (`today - 330d`) to align with compute window and avoid older-date fallback churn.
- Validation evidence captured during implementation:
	- `python -m py_compile main.py` passed after each phase.
	- `GET /api/training-load?days=180` returned `200` with history and pattern payloads.
	- function-scope verification confirmed `calculate_stress_scores(...)` no longer calls app-settings helper lookups.

## Latest Maintenance Update (2026-05-19, AGENTS Constraint-Overload Reduction)

- Updated `AGENTS.md` to reduce instruction cognitive load without changing policy intent.
- Added a front-loaded quick checklist with grouped must-do actions (scope, pre-implementation, verification, DB safety, architecture guards, reporting).
- Added a concise decision flow and section map to make rule discovery faster and reduce missed constraints.
- Explicit non-changes preserved:
	- no behavioral policy removals
	- no tool allowance changes
	- no architecture/safety rule relaxations

## Latest Maintenance Update (2026-05-16, Sticky AI Model Selection via localStorage)

- Updated AI model preference persistence in `static/index.html` using browser `localStorage` only (no backend changes).
- Changed module-level initialization to hydrate `aiSelectedModel` from `localStorage.getItem('ai_preferred_model')` with fallback to `AI_DEFAULT_MODEL`.
- Updated AI model select change handler to persist selected preset model to `localStorage` under key `ai_preferred_model`.
- Updated custom model input handler to persist non-empty custom model values to the same `ai_preferred_model` key.
- Preserved existing `theme` persistence behavior and key usage (`theme`) with no overlap.

## Latest Maintenance Update (2026-05-16, No-Check-In Pending State + Null Subjective)

- Updated backend subjective fallback handling in `main.py` so no-check-in state returns `recommendation_v2.subjective_score = null` instead of `10.0`.
- Updated `_build_recommendation_v2(...)` signature to accept `subjective_score: float | None = None`.
- Updated recommendation payload mapping to preserve null subjective score (`None` stays `None`).
- Updated combined-score computation path in `get_training_load()` to use a neutral subjective fallback (`10.0`) only for math when subjective is null.
- Updated frontend pending-state behavior in `static/index.html`:
	- added `.today-pattern-pending` muted pattern card class
	- force-neutral pattern cards now render pending style instead of fresh style
	- no-check-in pattern dots render empty and stress label renders as `—`
	- subjective score now renders pending placeholder `—` when no check-in exists
	- combined score renders as unconfirmed `value*` with pending style when no check-in exists
	- explainer copy switches to check-in prompt when subjective is unavailable
- Explicit non-change preserved: "No check-in today - pattern signals based on training load only" footer note remains in place.

## Latest Maintenance Update (2026-05-16, Pattern Cell Dot-Band Colors + Label Size)

- Updated pattern-cell visual state classes in `static/index.html`:
	- replaced `today-pattern-available` with `today-pattern-fresh` (accent)
	- remapped `today-pattern-neutral` to success tone
	- added `today-pattern-elevated` for warn tone
	- kept `today-pattern-stressed` as danger tone
- Replaced `_patternCellClass(...)` to derive visual class from `dots_filled` count bands:
	- 1 dot -> fresh
	- 2-3 dots -> neutral
	- 4 dots -> elevated
	- 5 dots -> stressed
- Updated pattern card call site to pass `d.dots_filled` into `_patternCellClass(...)`.
- Increased `.today-pattern-level` typography to `font-size: 15px` and `font-weight: 700`.

## Latest Maintenance Update (2026-05-16, Pattern Stress Dots TSB Signal)

- Replaced pattern stress-dot load helper in `main.py` from ATL/CTL ratio logic to per-pattern TSB-driven logic.
- Renamed helper from `_pattern_load_signal(atl, ctl)` to `_pattern_tsb_signal(tsb, ctl)`.
- New signal behavior:
	- returns `0.0` when `ctl <= 0.0`
	- otherwise computes `clamp(-tsb / ctl, 0..1)` and rounds to 3 decimals
- Updated `_build_recommendation_v2()` call site to pass `tsb` and `ctl` into the new helper.
- Explicit non-changes preserved:
	- no schema changes
	- no new database queries
	- no changes to `_dots_filled()`, `_stress_level_label()`, or the 70/30 combined signal split

## Latest Maintenance Update (2026-05-15, Scoring Scale 0-20 Migration)

- Migrated readiness scoring scale in `main.py` from 0-10 to 0-20 by updating multiplier call sites that consume `_subjective_fatigue()` output.
- Updated fatigue threshold defaults in `_CALIBRATION_DEFAULTS`:
	- large decrease: `15.0`
	- decrease: `13.0`
	- continue: `8.0`
	- increase: `6.0`
- Updated `_combined_recommendation()` band thresholds to 0-20 equivalents.
- Updated objective score scaling factors and clamp ranges used in readiness endpoints and diagnostics (`*10` objective ratio scale and `0.0..20.0` clamps).
- Updated neutral subjective fallback defaults from `5.0` to `10.0` where combined/fatigue score paths require a midpoint fallback.
- Kept `_subjective_fatigue()` unchanged (still returns `0.0..1.0`).
- Kept training modifier behavior and bounds unchanged (`±1.5`).
- Updated chart rendering scale in `static/index.html`:
	- ATL/CTL bar percentage denominator from 10 to 20
	- readiness background bands to new 0-20 tier boundaries
	- readiness chart y-axis max from 10 to 20
- Validation status:
	- static diagnostics report no errors in `main.py` and `static/index.html`

## Latest Maintenance Update (2026-05-14, Critical Bug-Hunt Skill Added)

- Added a new workspace skill at `.github/skills/critical-bug-hunt/SKILL.md`.
- Skill captures a reusable high-severity bug-finding workflow focused on concrete-trigger correctness failures:
	- data loss/corruption
	- crash in critical paths
	- auth/permission bypass and security exposure
	- significant user-facing breakage
- Includes explicit decision gates for:
	- criticality threshold (concrete trigger + high impact)
	- fix vs report-only behavior when confidence is uncertain
	- PR safety bar (high confidence required)
- Includes output contract for both outcomes:
	- fixed bug report with impact, root cause, fix, and validation
	- no-critical-bugs-found summary

## Latest Maintenance Update (2026-05-09, Canonical Mapping Sync + Startup Mapping Migration)

- Updated canonical save flows in `main.py` so when a canonical title is saved (direct canonical API and conflict resolve API), the canonical title is synchronized into `exercise_mappings`.
- New canonical-to-mapping sync behavior:
	- carries over an existing mapping pattern when one exists (prefers previous canonical title mapping, then latest Hevy title mapping for the same `exercise_id`)
	- inserts an unassigned mapping row when no prior pattern exists
	- removes the old mapping title entry after carry-over so canonical title becomes the active mapping key
- Added startup migration flag `migration_canonical_mapping_sync_v1` in `database.py`.
- Migration behavior inserts unassigned `exercise_mappings` rows for canonical titles that are missing from `exercise_mappings` (case-insensitive existence check).
- Validation status:
	- `python -m py_compile main.py database.py` passes

## Latest Maintenance Update (2026-05-09, Canonical Sync Root-Cause + Movement Trend ID Join + Backfill)

- Updated `importer.py` pre-write canonical resolution to re-check `exercise_canonical` by `exercise_id` during sync processing, addressing stale map timing within long import runs without adding any post-write rewrite path.
- Updated movement analytics APIs in `main.py`:
	- `/api/movements/search` now resolves display titles via canonical + mapping join path and returns `items[{exercise_id,title}]` for stable selection.
	- `/api/movements/session-trend` and `/api/movements/volume-trend` now support `exercise_id` filtering and resolve movement titles through canonical/mapping joins instead of raw title equality.
- Updated Movement Trend UI wiring in `static/index.html` to select/store `exercise_id` from autocomplete items and query trend endpoints via `exercise_id` (with title fallback for compatibility).
- Added one-time historical canonical backfill migration in `database.py` (`migration_canonical_title_backfill_v1`) that updates `workout_logs.exercise_title` from `exercise_canonical.canonical_title` where `exercise_id` matches.
- Updated `canonical_gate.py` Gate checks to verify canonical storage using direct SQL against `workout_logs` filtered by `exercise_id`.
- Added `movement_trend_gate.py` with Gate #3 validating exercise_id-based session trend aggregation after backfill.
- Validation status:
	- static/file diagnostics report no syntax errors in edited files
	- live gate scripts are blocked until local API is running at `http://127.0.0.1:8000`

## Latest Maintenance Update (2026-05-08, AI Tab Overflow Height Handoff)

- Updated `static/index.html` so `body.ai-open` now sets both `overflow: hidden` and `height: 100vh`.
- Added `body.ai-open main` constraints (`padding: 0`, `overflow: hidden`, `height: calc(100vh - 54px)`, flex column, full width behavior) to prevent page-level scroll conflict while AI tab is open.
- Updated `.tab-content#tab-ai.active` to `flex: 1`, `height: 100%`, and `overflow: hidden`, removing previous `calc(100vh - 54px)` dependency.
- Updated mobile AI override to use `height: 100%` for `.tab-content#tab-ai.active`.

## Latest Maintenance Update (2026-05-07, AI Tab Body Overflow Lock)

- Added `body.ai-open { overflow: hidden; }` in `static/index.html` to lock page scroll while AI tab is active.
- Updated AI tab activation path in `activateTab(tabName)` to toggle `document.body.classList` with `ai-open` for AI vs non-AI tabs.
- Kept `tab-content#tab-ai.active` height/overflow rule intact and scoped changes to requested CSS/JS only.

## Latest Maintenance Update (2026-05-07, AI Chat Full Height Sticky Layout)

- Replaced `static/index.html` AI tab active layout with a full-height column (`height: calc(100vh - 54px)`) and hidden overflow.
- Replaced AI chat card and message area rules to a full-height scrollable layout with sticky input row and no legacy fixed message-area heights.
- Updated user/assistant message-role rules to the requested subtle right bubble for user and no-bubble full-width assistant style.
- Updated `@media (max-width: 900px)` AI overrides to only enforce tab height and `ai-chat-messages { min-height: 0; }`.

## Latest Maintenance Update (2026-05-07, AI Chat Surface Token Alignment)

- Updated `static/index.html` AI chat message area surface to `var(--bg)` and explicitly removed box shadow while keeping border removed.
- Updated model selector/input controls in `#ai-model-field` to use `background: var(--card)` and `color: var(--text)`.
- Updated `.ai-chat-input` to use `background: var(--card)` and `color: var(--text)`.

## Latest Maintenance Update (2026-05-07, AI Chat Card Shell Removal)

- Updated `static/index.html` so `#tab-ai .ai-chat-card` uses a transparent shell (`background: transparent !important; border: none !important; box-shadow: none;`) with centered `max-width: 760px` layout and `padding: 0 16px`.
- Added compact inline model control styling for `#tab-ai #ai-model-field select` and `#tab-ai #ai-model-field input` (auto width, 160px minimum, compact padding).
- Scope remained CSS-only with no HTML or JS changes.

## Latest Maintenance Update (2026-05-07, AI Chat Plain Text Stack)

- Updated `static/index.html` AI chat message presentation to plain stacked text (no bubble background, radius, or per-bubble border styling).
- Removed row-style alignment wrappers by switching message containers to block layout and text alignment by role.
- Set `#tab-ai .ai-chat-card` to a centered 760px column and adjusted message pane sizing/background to the requested standard chat column style.

## Latest Maintenance Update (2026-05-07, AI Chat Standard UI Revert)

- Reverted `static/index.html` AI chat window from terminal styling to a standard modern chat UI using theme tokens (`var(--card)`, `var(--border)`, `var(--bg)`).
- Removed terminal artifacts: `$`/`>` prefixes, cursor animation, hardcoded dark colors, and the `ai-chat-clear` button element/CSS.
- Applied requested message bubble layout, input sizing, model-label typography, scrollbar styling, and three-dot typing indicator styling.

## Latest Maintenance Update (2026-05-07, AI Terminal Bar Removal)

- Removed the `terminal-bar` element and its three colored dot children from the AI chat card in `static/index.html`.
- Deleted the `.terminal-bar` and `.terminal-dot*` CSS rules from `static/index.html`.
- Kept all other HTML and CSS unchanged.

## Latest Maintenance Update (2026-05-07, AI Chat UX Alignment Pass)

- Updated `static/index.html` so AI chat messages are constrained to `max-width: 75%`, with user messages right-aligned and assistant messages left-aligned.
- Preserved terminal-style differentiation with `>` and `$` prefixes and role-specific text colors.
- Added an `#ai-typing-indicator` element and CSS visibility/animation hooks for in-flight response feedback.
- Updated AI chat textarea placeholder copy and enforced touch/iOS-safe input/button sizing.

## Latest Maintenance Update (2026-05-07, Settings Grid Equal Height)

- Updated `static/index.html` so `#tab-settings.active` stretches grid items instead of aligning them to the start.
- Added `height: 100%` to `#tab-settings .settings-card` so each settings card fills its grid cell height.
- Scope remained CSS-only and limited to the settings grid equal-height behavior.

## Latest Maintenance Update (2026-05-07, Settings Grid 2x2 Layout)

- Updated `static/index.html` so `#tab-settings.active` uses a 2x2 named-area layout: `api`, `sync`, `diagnostics`, and `ai`.
- Added the missing `#tab-settings .ai-settings-card { grid-area: ai; }` assignment.
- Removed the full-width AI settings card override so the named grid-area controls placement.

## Latest Maintenance Update (2026-05-07, AI Chat Terminal Restyle)

- Restyled the AI chat card in `static/index.html` to read as a terminal window with a scoped dark shell, title bar, and monospace title treatment.
- Added a new `terminal-bar` element with red, yellow, and green dots immediately before the existing `AI Chat` title.
- Flattened user and assistant message bubbles into terminal-style lines with `>` and `$` prefixes while preserving existing AI chat behavior.

## Latest Maintenance Update (2026-05-07, Mobile Drawer Docs Link)

- Added `Docs` link to the mobile drawer in `static/index.html`.
- Placed the link after the last existing mobile nav tab (`Settings`) and pointed it to `/static/docs.html`.
- Scope intentionally limited to mobile drawer markup only.

## Latest Maintenance Update (2026-05-07, AI/Settings/Mobile UI Stabilization)

- Updated `static/index.html` to keep top navigation persistently visible on mobile:
	- set mobile nav to fixed positioning at the top
	- adjusted `main` top padding at mobile breakpoints to avoid content overlap
	- simplified very-small-screen nav rules to prevent 2-row wrapping behavior
- Updated mobile drawer offset so it opens beneath the fixed top nav (`top: 54px`).
- Fixed AI chat card alignment on desktop:
	- centered active AI tab content container
	- constrained chat card width with centered margins
- Fixed Settings tab layout imbalance:
	- forced `AI Settings` card to span full grid width on desktop (`grid-column: 1 / -1`)
- Reduced mobile AI input zoom/keyboard friction:
	- increased `.ai-chat-input` font size to `16px`
	- added textarea input attributes (`autocomplete`, `autocorrect`, `autocapitalize`, `spellcheck`, `enterkeyhint`) for better mobile behavior
- Validation:
	- static diagnostics report no errors in `static/index.html`

## Latest Maintenance Update (2026-05-07, Docs CSS Variables and Importer List Styling Fix)

- Updated `static/docs.html` `:root` wiki override mappings to define missing variables used by existing styles:
	- `--text-primary: var(--text)`
	- `--text-secondary: var(--text)`
	- `--text-muted: var(--muted)`
	- `--bg-code: color-mix(in srgb, var(--card) 72%, black 28%)`
	- `--border-accent: var(--border)`
	- `--accent-border: color-mix(in srgb, var(--accent) 40%, transparent)`
- Added `.doc-list` and `.doc-list li` CSS rules to standardize importer bullet styling.
- Applied `class="doc-list"` to the unordered list in the `#importer` section only.
- Verified section badge sequencing remains correct:
	- `05` (modalities), `05b` (title tagging), `05c` (importer), `06` (movement patterns)
- Validation: static diagnostics report no errors in `static/docs.html`.

## Latest Maintenance Update (2026-05-07, Diagnostics Page Outlined in Docs)

- Added a dedicated `Diagnostics page` section to `static/docs.html` (`id="diagnostics"`) to clearly document purpose and usage.
- Added a new Notes sidebar link to `#diagnostics` for quick wiki-style navigation.
- Expanded documentation coverage with:
	- when to use diagnostics
	- panel-by-panel outline (session volume, 7-day, 28-day, raw session data)
	- a recommended debugging workflow block
	- practical note about observational vs corrective actions
- Updated importer Diagnostics callout to link to the full diagnostics section (`§10 Diagnostics page`).
- Renumbered trailing sections to preserve order:
	- Limitations: `10` -> `11`
	- References: `11` -> `12`
- Validation:
	- diagnostics sidebar link and section anchor both present in `static/docs.html`
	- static diagnostics report no errors in `static/docs.html`

## Latest Maintenance Update (2026-05-07, Remove Divergences from RTS TRAC Section)

- Removed the entire `Divergences from RTS TRAC` section from `static/docs.html`.
- Removed the corresponding sidebar TOC link to `#divergences` in the Notes group.
- Updated an Overview paragraph to remove the in-page link to the removed section.
- Renumbered subsequent sections to keep ordering contiguous:
	- `Known limitations` changed from section 11 to 10
	- `References` changed from section 12 to 11
- Validation:
	- no remaining `divergences` references in `static/docs.html`
	- static diagnostics report no errors in `static/docs.html`

## Latest Maintenance Update (2026-05-07, Docs Wiki Sidebar Restoration)

- Reworked `static/docs.html` to restore wiki-style section navigation while retaining index theme colors.
- Added a fixed left sidebar Table of Contents on desktop and a slide-in mobile drawer on small screens.
- Added mobile navigation controls:
	- hamburger menu button in top nav
	- tap-to-close overlay
	- responsive open/close behavior with ARIA state updates
- Added requested Training load TOC links in sidebar:
	- `Title tagging` (`#title-tagging`)
	- `Workout importer` (`#importer`)
- Added new docs sections between §05 and §06:
	- `§05b Workout title tagging convention`
	- `§05c Workout importer`
- Added section-aware sidebar highlighting via `IntersectionObserver` and smooth-scroll behavior for TOC links.
- Kept index-compatible visual theme tokens (`--bg`, `--card`, `--border`, `--text`, `--accent`, etc.) while preserving docs-specific layout.

## Latest Maintenance Update (2026-05-07, Docs Page Navbar Integration)

- Added "Docs" link to the navbar in `static/index.html` 
  - Added as an external link in the nav-tabs section, styled to match existing nav elements
- Refactored `static/docs.html` to match `static/index.html` styling:
  - Replaced custom color scheme with index.html's theme variables (dark: `#2e282a`, `#3d3638`, etc.)
  - Added sticky navbar at top with logo, nav links, and "← Dashboard" return button
  - Removed sidebar layout (previously a fixed left sidebar with navigation sections)
  - Converted main content area from `margin-left: var(--sidebar-w)` to centered `main` with `max-width: 900px`
  - Updated typography: headings, body text, and inline code now use index.html's font sizes and colors
  - Updated component styling:
    - Formula blocks: new background/border colors matching theme
    - Info cards: updated with new color scheme
    - Tables: header and cell styling aligned with index.html
    - Inline code: updated background/border/text colors
  - Updated mobile responsiveness for new navbar layout
  - Simplified JavaScript: removed sidebar nav link tracking, kept only smooth scroll for anchor links

## Latest Maintenance Update (2026-05-03, Backlog source-of-truth established)

- Removed the Diagnostics page AI Assistant section from `static/diagnostic.html`.
- Deleted AI section HTML controls and containers:
	- model selector
	- context preview toggle and preview area
	- chat message window
	- input row, send/clear controls, and status line
- Removed AI-only JavaScript from `static/diagnostic.html`:
	- `OPENROUTER_API_KEY` and `OPENROUTER_URL`
	- `chatHistory` and `readinessContext`
	- `buildSystemPrompt()`, `sendMessage()`, `clearChat()`, `appendMessage()`, `escapeHtml()`, `setStatus()`, `setContextPreview()`, and `toggleContextPreview()`
	- removed readiness-context assignment from `loadAndRender()`
	- removed AI input listeners from `DOMContentLoaded`
- Removed AI-only CSS selectors (`.ai-*`) from `static/diagnostic.html`.
- Removed `marked.js` CDN script tag from `static/diagnostic.html` because no markdown parsing remains in that file.
- Preserved non-AI diagnostics functionality and controls:
	- Engine Snapshot render path remains intact
	- Pattern Sensitivity and Session Processing cards remain unchanged
- Validation:
	- static diagnostics report no errors in `static/diagnostic.html`
	- no `OPENROUTER_API_KEY`, `marked`, or removed AI function/id references remain in `static/diagnostic.html`

## Latest Maintenance Update (2026-05-06, AI Prompt Recent Session Detail Rewrite)

- Replaced the recent-session section in `_build_ai_system_prompt()` in `main.py` with direct database queries over `WorkoutSession` and `WorkoutLog`.
- The AI system prompt now includes only the last 3 sessions ordered by `workout_date DESC, start_time DESC` instead of a snapshot-derived 7-day window.
- Each session line now includes:
	- workout date
	- workout title
	- modality
	- duration in minutes
	- sRPE
- Each session now expands into per-exercise detail aggregated from `WorkoutLog` grouped by `exercise_title`, including:
	- set count
	- total reps
	- total volume (`weight_lbs * reps`)
	- top weight
	- average RPE when present
- Session ATL/CTL/TSB values were intentionally left out of the session line because current-day training load context already appears in the prompt's `Training Load` section.
- Validation:
	- `python -m py_compile main.py` passes

## Latest Maintenance Update (2026-05-06, AI Prompt Scale Reference)

- Updated `_build_ai_system_prompt()` in `main.py` to include a `SCALE REFERENCE (critical for correct interpretation):` section immediately after the prompt header/date block.
- Revised the scale guidance to emphasize subjective-input semantics:
	- all subjective inputs now share a common 0-4 interpretation where `2` is normal expected training fatigue and only `3` or `4` should trigger caution/modification recommendations
	- combined and subjective scores are explicitly defined as `0 = fully fresh/recovered, 10 = maximum fatigue`
	- objective score is clarified as a neutral 0-10 recent-volume context signal rather than a readiness score
	- TSB and volume ratio definitions remain explicit for load-context interpretation
- Validation:
	- `python -m py_compile main.py` passes

## Latest Maintenance Update (2026-05-06, AI Chat Raw JSON SSE Alignment)

- Updated AI chat streaming contract between `main.py` and `static/index.html` to preserve upstream OpenRouter JSON SSE payloads instead of flattening deltas into plain-text proxy chunks.
- Changed `_stream_openrouter(...)` in `main.py` to forward upstream `data:` payloads unchanged:
	- still buffers `iter_text()` manually on `\n\n` SSE boundaries
	- now emits `data: {raw_json}\n\n` for each upstream JSON event
	- preserves `[DONE]` pass-through and keeps response/client cleanup in `finally`
- Refactored `sendAIMessage()` in `static/index.html` to match the working diagnostic-style parser against raw JSON SSE lines:
	- reads stream chunks with `ReadableStream` + `TextDecoder`
	- buffers incomplete lines across chunks
	- processes `data: ` lines individually instead of joining multiple payload lines
	- parses each JSON payload and appends `choices[0].delta.content` (with `text` fallback) to `assistantText`
	- keeps incremental `marked.parse(assistantText)` rendering and scroll-to-bottom behavior
- Resulting architecture keeps backend key secrecy intact while aligning the chat parser with the working raw-JSON SSE model used elsewhere.
- Validation:
	- `python -m py_compile main.py` passes
	- editor diagnostics report no errors in `main.py` or `static/index.html`

## Latest Maintenance Update (2026-05-06, Session-Scoped AI Model Selection)

- Moved AI model selection out of persisted settings and into the AI chat UI in `static/index.html`:
	- AI tab now renders a model dropdown above the context preview with six preset OpenRouter models plus `Custom model…`
	- session-only state is stored in `aiSelectedModel`, defaulting to `openai/gpt-4o-mini` on page load
	- selecting `Custom model…` reveals a text input and chat requests use that custom string for the current browser session only
- Simplified the Settings-tab AI card in `static/index.html` to API-key-only:
	- removed the model selector from Settings
	- preserved API key preview, encrypted-key save flow, and lock/change behavior
	- updated copy so Settings manages only the API key while model choice happens in the AI tab
- Reduced the backend AI settings contract in `main.py`:
	- `AISettingsInput` now accepts only `api_key`
	- `GET /api/settings/ai` now returns only `configured` and `api_key_preview`
	- `PUT /api/settings/ai` now validates/stores only encrypted `ai_api_key`
	- code no longer reads or writes `ai_model`
- Updated request-scoped chat model handling in `main.py`:
	- `AIChatRequest` now includes `model` with default `openai/gpt-4o-mini`
	- `POST /api/ai/chat` now uses the request model with the stored API key when calling `_stream_openrouter(...)`
	- `sendAIMessage()` now posts `{ message, history, model }`
- Validation:
	- `python -m py_compile main.py` passes
	- editor diagnostics report no errors in `main.py` or `static/index.html`
	- isolated API smoke checks confirmed `PUT /api/settings/ai` succeeds with only `api_key`, `GET /api/settings/ai` returns no `model` field, chat requests pass through the selected request model, and only `ai_api_key` is persisted

## Latest Maintenance Update (2026-05-05, OpenRouter-Only AI Simplification)

- Simplified backend AI integration in `main.py` to OpenRouter-only:
	- removed provider field from `AISettingsInput`
	- `_get_ai_settings(db)` now returns only `(model, api_key)` and no longer reads `ai_provider`
	- removed multi-provider stream helpers (`_stream_anthropic`, `_stream_gemini`) and provider-specific payload builders
	- renamed `_stream_openai_family(...)` to `_stream_openrouter(...)` and hardcoded OpenRouter chat completions URL
	- removed provider dispatch from `POST /api/ai/chat`; endpoint now always uses OpenRouter path via `_openai_compatible_messages(...)`
- Simplified AI settings API contract in `main.py`:
	- `PUT /api/settings/ai` now accepts/stores only `model` and `api_key` (encrypted)
	- `GET /api/settings/ai` now returns `configured`, `model`, and `api_key_preview` only (no `provider` field)
- Confirmed `_safe_sse_chunk()` behavior in `main.py` keeps only carriage-return sanitization:
	- `clean = (delta or "").replace("\r", "")`
	- no newline replacement and no `.strip()`
- Simplified AI settings UI/JS in `static/index.html`:
	- removed provider dropdown from Settings tab AI card
	- replaced chip/provider model controls with a single free-text model input and helper note
	- removed provider-switching frontend logic and provider-bearing save payloads
	- `saveAISettings()` now sends `{ model, api_key }`
	- updated AI copy to OpenRouter-specific wording
- Kept chat card behavior unchanged (including SSE streaming and final markdown render on completion).
- Validation:
	- static diagnostics: no errors in `main.py` and `static/index.html`
	- `python -m py_compile main.py` passes

## Latest Maintenance Update (2026-05-05, Stage 5 Frontend: AI Chat Card)

- Added AI chat card UI in `#tab-ai` inside `static/index.html` with:
	- collapsed context preview (`show context` / `hide context`) using monospace pre-wrapped display
	- scrollable message window with user bubbles right-aligned and assistant bubbles left-aligned
	- markdown rendering for assistant content via `marked.parse()`
	- auto-resize textarea input row with Enter-to-send and Shift+Enter newline behavior
	- Send/Clear buttons and status line for `Thinking...` and error states
- Added marked.js CDN to `static/index.html` head (`cdnjs marked 9.1.6`).
- Added frontend state in `static/index.html`:
	- `aiChatHistory = []`
	- `aiReadinessContext = null`
- Implemented `loadAIContext()` in `static/index.html`:
	- fetches `GET /api/diagnostics/snapshot`
	- builds context preview string client-side using the same field set/labels as `_build_ai_system_prompt()` in backend
	- refreshes on every AI tab activation
- Updated AI tab activation flow in `static/index.html`:
	- `activateTab('ai')` now runs `loadAISettings().then(() => loadAIContext())`
- Implemented `sendAIMessage()` in `static/index.html`:
	- posts `{ message, history: aiChatHistory }` to `POST /api/ai/chat`
	- reads SSE stream into a plain-text streaming assistant bubble
	- renders assistant markdown with `marked.parse()` once after the stream completes
	- finalizes exchange into `aiChatHistory`
- Implemented `clearAIChat()` in `static/index.html`:
	- resets `aiChatHistory`
	- restores message window placeholder and clears status/input state
- Added unconfigured-state chat gating:
	- when AI settings are not configured on tab activation, chat notice is shown and Send is disabled
	- when configured, notice is hidden and Send is enabled
- Validation:
	- static diagnostics on `static/index.html` pass (no errors)
	- inline JS brace counts balanced (`open=close` for both inline script blocks)
	- marked.js CDN reference confirmed in `static/index.html`

## Latest Maintenance Update (2026-05-05, Stage 4 Fix: Move AI Settings To Settings Tab)

- Moved the full AI settings card markup (provider/model/API key + save/change controls) from `#tab-ai` to `#tab-settings` in `static/index.html`.
- Left `#tab-ai` in the DOM but empty to reserve it for Stage 5 chat UI.
- Kept AI settings logic unchanged:
	- `loadAISettings()` unchanged
	- `saveAISettings()` unchanged
	- AI tab activation still calls `loadAISettings()` for configured-state refresh
- No backend changes.
- No CSS changes required.
- Validation:
	- static diagnostics on `static/index.html` pass (no errors)
	- markup checks confirm AI card is now inside Settings tab and AI tab is empty

## Latest Maintenance Update (2026-05-04, Stage 4 Frontend: AI Settings Card)

- Updated `static/index.html` navigation to add `AI` as the fifth tab in both desktop and mobile tab lists.
- Added new `#tab-ai` panel in `static/index.html` with an AI settings card containing:
	- provider selector (`OpenRouter`, `Anthropic`, `Gemini`, `ChatGPT (OpenAI)`, `DeepSeek`)
	- dynamic model control area
	- encrypted API key input with show/hide toggle
	- inline result feedback and save/change actions
- Added provider-aware model control behavior in `static/index.html`:
	- OpenRouter uses free-text model input plus quick-pick chips:
		- `google/gemini-flash-1.5`
		- `anthropic/claude-sonnet-4-5`
		- `meta-llama/llama-3.3-70b-instruct`
		- `deepseek/deepseek-chat`
		- `openai/gpt-4o`
	- Anthropic models: `claude-opus-4-5`, `claude-sonnet-4-5`, `claude-haiku-3-5`
	- Gemini models: `gemini-2.0-flash`, `gemini-2.0-flash-lite`, `gemini-1.5-pro`
	- OpenAI models: `gpt-4o`, `gpt-4o-mini`, `o3-mini`
	- DeepSeek models: `deepseek-chat`, `deepseek-reasoner`
- Added AI settings API wiring in `static/index.html`:
	- `loadAISettings()` -> `GET /api/settings/ai` on AI tab activation
	- `saveAISettings()` -> `PUT /api/settings/ai`
	- inline `422`/validation detail extraction and display
	- empty API key client-side validation (request blocked)
	- success lock flow: fields disabled + masked preview shown + `Change` unlock action
- Validation:
	- static diagnostics for `static/index.html` report no errors
	- existing tab activation branches preserved with added `ai` activation load hook

## Latest Maintenance Update (2026-05-04, Stage 3 Backend: AI Chat Proxy Endpoint)

- Added `AIChatMessage` and `AIChatRequest` models in `main.py`.
- Added `POST /api/ai/chat` in `main.py`:
	- returns `422` when AI settings are not configured
	- builds system prompt using `_build_ai_system_prompt(db)`
	- dispatches by stored provider (`openrouter`, `openai`, `deepseek`, `anthropic`, `gemini`)
- Implemented provider-specific streaming helpers using `httpx` with streamed upstream responses:
	- OpenRouter/OpenAI/DeepSeek via shared OpenAI-compatible path and message format
	- Anthropic via `https://api.anthropic.com/v1/messages` with required headers and Anthropic message format
	- Gemini via `.../{model}:streamGenerateContent?key=...` with Gemini contents format
- SSE proxy behavior:
	- forwards chunks as `data: {delta}\n\n`
	- terminates with `data: [DONE]\n\n`
- Provider error mapping:
	- upstream HTTP errors are surfaced as `502` with provider error detail
	- avoids raw Python traceback leakage in response detail
- Validation:
	- `python -m py_compile main.py` passed
	- Stage 3 gate checks passed in deterministic mocked-stream harness:
		- no AI settings configured -> `422`
		- bad API key -> `502` with provider message
		- OpenAI-compatible stream yields at least one `data:` chunk and ends with `[DONE]`
		- Anthropic stream yields at least one `data:` chunk and ends with `[DONE]`
		- history payload propagation verified with follow-up context response

## Latest Maintenance Update (2026-05-04, Stage 2 Backend: System Prompt Builder)

- Refactored diagnostics snapshot logic into shared helper `_build_diagnostics_snapshot(db)` in `main.py`.
- Updated `GET /api/diagnostics/snapshot` in `main.py` to return `_build_diagnostics_snapshot(db)` so route output remains unchanged while enabling internal reuse.
- Added `_build_ai_system_prompt(db)` helper in `main.py` that consumes the same diagnostics snapshot data and builds a structured system prompt containing:
	- date
	- combined/subjective/objective scores
	- check-in detail fields
	- joint advisory
	- ATL/CTL/TSB
	- volume baseline
	- last 7 days of sessions
- Missing-data handling in `_build_ai_system_prompt(db)`:
	- emits `No check-in recorded for today` when no check-in exists for today
	- emits `No sessions in the last 7 days` when no sessions match the last-7-day window
	- normalizes missing values to `N/A` (no literal `None` output)
- Validation:
	- `python -m py_compile main.py` passed
	- Stage 2 gate checks passed via isolated temp DB snippet:
		- with today's check-in: output contains `Combined Score`, `Tiredness`, `ATL`, and at least one `Session:` line
		- with no check-in today: output contains `No check-in recorded for today` and does not contain literal `None`
		- with no sessions in last 7 days: output contains `No sessions in the last 7 days`

## Latest Maintenance Update (2026-05-04, Stage 1 Backend: Encrypted AI Settings Storage)

- Added `AISettingsInput` in `main.py` with fields `provider`, `api_key`, and `model` for AI settings payloads.
- Added `_get_ai_settings(db)` helper in `main.py`:
	- reads `ai_provider`, `ai_model`, and `ai_api_key` from `app_settings`
	- decrypts `ai_api_key` via `_decrypt()`
	- returns `(None, None, None)` when any value is missing or decryption fails
- Added `GET /api/settings/ai` in `main.py`:
	- always returns stable shape `{ configured, provider, model, api_key_preview }`
	- maps unset/missing state to `configured: false` with null `provider`, `model`, and `api_key_preview`
	- never returns raw API key
- Added `PUT /api/settings/ai` in `main.py`:
	- validates provider allowlist: `openrouter`, `anthropic`, `gemini`, `openai`, `deepseek`
	- returns `422` on invalid provider
	- trims and validates non-empty `model` and `api_key` (`422` on empty)
	- encrypts API key with `_encrypt()` and stores `ai_provider`, `ai_model`, `ai_api_key` in `app_settings`
	- returns same shape as GET with masked preview only
- Validation:
	- `python -m py_compile main.py` passed
	- API gate checks passed (isolated temp DB + TestClient):
		- unset `GET /api/settings/ai` returns `200` and stable `configured: false` null-shape
		- valid `PUT /api/settings/ai` returns `200`, `configured: true`, preview suffix matches key tail, raw key absent
		- invalid provider returns `422`
		- empty key returns `422`
		- post-save `GET /api/settings/ai` returns correct provider/model, raw key absent
		- DB `app_settings.ai_api_key` stored encrypted (Fernet token prefix `gAAA`, not plaintext)

## Latest Maintenance Update (2026-05-03, Backlog Source-of-Truth)

- Added `backlog.md` in project root with release blockers, bookmarked items, low-priority items, and recently completed context.
- Outstanding work tracking now uses `backlog.md` as the source of truth.
- `plan.md` open-items section is retained as historical context only.

## Latest Maintenance Update (2026-05-03, Initial Import Verification-State Preservation)

- Updated `initial_import()` in `importer.py` to preserve manual verification fields across full reimport wipes.
- Before deleting `workout_sessions`, importer now snapshots existing rows into a dict keyed by `hevy_workout_id` containing:
	- `verification_status`
	- `verified_at`
	- `srpe`
- After replaying Hevy workouts and rebuilding `workout_sessions`, importer now restores those preserved fields onto rebuilt rows where `hevy_workout_id` matches.
- This prevents full reimports from resetting previously verified/manual session state back to default pending values.
- No changes made to `incremental_sync()`.
- No changes made to `_process_workout()`.
- Validation: `python -m py_compile importer.py` passed.

## Latest Maintenance Update (2026-05-03, Exercises Tab Cleanup)

- Removed `Exercise Name Overrides` card and all associated frontend JS/state from `static/index.html`.
- Removed `Rename Exercise` card and all associated frontend JS/state from `static/index.html`.
- Updated `Exercise Names - Needs Review` card to be collapsible with a header toggle:
	- Expanded by default when unresolved conflicts exist.
	- Collapsed by default when no unresolved conflicts exist.
- Added inline `Add Override` flow inside the expanded Needs Review card:
	- Debounced autocomplete search using `GET /api/movements/search`.
	- Canonical name input with Save/Cancel actions.
	- Save posts to `POST /api/exercises/canonical` with `{ exercise_id, canonical_title }`.
	- Inline error handling on save failures.
- Enforced one-open-editor rule in Needs Review:
	- Opening Add Override closes any conflict inline edit.
	- Opening conflict inline edit closes Add Override form.
- Preserved existing conflict table actions and nav badge behavior.
- Backend compatibility update in `main.py`:
	- `GET /api/movements/search` now also returns `items` with `{ exercise_id, title }` while preserving existing `results` title list for back-compat.
- Validation: static diagnostics on `static/index.html` passed (no errors).

## Latest Maintenance Update (2026-05-03, Sync Cooldown Removal)

- Removed sync cooldown enforcement from `POST /api/sync` in `main.py`.
- Removed `_SYNC_COOLDOWN_SECONDS` and the cooldown response path (`status="cooldown"`, `retry_after_seconds`).
- Preserved `_sync_lock` behavior so concurrent sync runs are still prevented (`status="already_running"`).
- Validation: `python -m py_compile main.py` passed.

## Latest Maintenance Update (2026-05-03, Incremental Sync Gate)

- Added `incremental_sync_gate.py` with gate-runner structure aligned to existing gate scripts (`dedup_gate.py`, `conflict_gate.py`).
- Script includes preflight checks for app reachability and `GET /api/sync/last-sync` availability.
- Implemented gates:
	- Gate 1: clears DB `last_sync`, triggers sync, verifies `workout_sessions > 0` and `last_sync` repopulated.
	- Gate 2: triggers second sync and verifies `last_sync` strictly advanced with unchanged `workout_sessions` count.
	- Gate 3: simulates delete path by directly removing one workout from `workout_sessions` and `workout_logs`, then verifies both are gone.
	- Gate 4: verifies canonical title substitution integrity for `exercise_canonical` rows, with SKIP when no canonical entries exist.
	- Gate 5: verifies `last_sync` strictly advances after another sync.
- CLI args: `--base-url`, `--db-path`, `--sync-timeout-seconds`, `--poll-interval-seconds`.
- Final output includes per-gate PASS/FAIL (or SKIP), summary counts, and non-zero exit on failures.
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
- Preserved existing importer behavior inside `_process_workout()` for:
	- canonical title substitution
	- modality classification and verification resolution
	- `ensure_exercise_mapped()` exercise mapping flow
	- `WorkoutSession` upsert behavior, including verified-session preservation
	- set-level `WorkoutLog` upsert behavior that only updates titles on conflict
- `initial_import()` now clears `workout_logs`, `workout_sessions`, and auto/unreviewed `exercise_mappings` before replaying paginated workout imports.
- `incremental_sync()` now applies Hevy workout events:
	- `deleted` events remove matching `workout_logs` and `workout_sessions`
	- `updated` events re-run `_process_workout()` on the supplied workout payload
- Import sync cursor now persists to `app_settings.last_sync` after successful full or incremental sync passes.
- Updated importer callers in `main.py`, `canonical_gate.py`, and `conflict_gate.py` to use the new `import_hevy_data(db)` entrypoint.
- Validation: `python -m py_compile importer.py` and `python -m py_compile main.py canonical_gate.py conflict_gate.py` passed.

## Latest Maintenance Update (2026-05-03)

- Added `HevyClient.get_workout_events(since, page=1, page_size=10)` in `hevy_client.py` for `GET /v1/workouts/events`.
- Method builds the events URL inline, uses `self.session.get(..., timeout=30)`, clamps `page_size` to the API max of `10`, and returns `{ page, page_count, events: [] }` for `404` responses.
- Method now raises explicit client-side errors for unauthorized, HTTP, JSON decode, connection, timeout, and unexpected failure paths without expanding the repo to a new config/error abstraction.
- Validation: `python -m py_compile hevy_client.py` passed.

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
- Log tab: Rec column removed from session log table (column header + cells stripped).
- Movement Trend redesigned in Workouts tab (2026-05-01):
	- Backend movement trend endpoints now aligned to redesigned client contract in `main.py`:
		- added `GET /api/movements/session-trend?exercise=&window=`
		- added `GET /api/movements/volume-trend?exercise=&window=`
		- removed legacy `GET /api/movements/weekly-trend`
		- window validation: `8w|6m|1y|all` (default `6m`)
		- session-trend returns per-session `session_date`, `top_set`, `avg_weight`, `e1rm` for verified sessions
		- volume-trend returns Monday-start weekly `week_start`, `weekly_volume` for verified sessions
		- session `e1rm` uses best set-level value from `calculate_e1rm(weight, reps, rpe, rir)`
		- syntax validation: `python -m py_compile main.py` passed
	- Card remains between Session Verification Queue and Session Log
	- Search row uses placeholder `Search movements...` + clear button and 300 ms debounced autocomplete (`/api/movements/search?q=`)
	- Controls now use two toggle groups on one row:
		- Metric: `e1RM`, `Top Set`, `Avg Weight`, `Volume`
		- Window: `8W`, `6M`, `1Y`, `All`
	- Endpoint routing by metric:
		- `e1RM`/`Top Set`/`Avg Weight` -> `/api/movements/session-trend?exercise=&window=`
		- `Volume` -> `/api/movements/volume-trend?exercise=&window=`
	- Chart rebuilt as single line chart with markers (`spanGaps: false`), sparse x-axis labels (`maxTicksLimit: 6`), and y-axis metric label
	- Y-axis auto-range now applies dynamic 10% padding around finite values
	- Theme redraw retained in `applyTheme()` while Workouts tab is active and movement data is loaded
	- Outside-click dropdown close integrated into existing document click listener using `event.target.closest()` without changing mobile-nav behavior
	- Handler binding is idempotent (`mvtHandlersBound` guard) to prevent duplicate listeners
	- Static diagnostics pass on `static/index.html`: no errors
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
	- Exercise Rename Tool moved out of diagnostics and into the Exercises tab in `static/index.html`:
		- new `Rename Exercise` card above Exercise Movement Mappings
		- helper text: `Use this when an exercise title changes in Hevy. Updates all historical sets and the exercise mapping table.`
		- Current title now uses debounced autocomplete (`/api/movements/search?q=`, min 2 chars, 300 ms)
		- New title remains free-text input
		- submit posts to `POST /api/exercises/rename` and surfaces exact success/404/backend-detail messages
		- clearing Current title clears both inputs and result area
		- outside-click close for dropdown integrated into existing document click listener
		- handler setup is idempotent (`exRenameHandlersBound` guard)
	- Removed Exercise Rename Tool UI and JS handler from `static/diagnostic.html`
	- Added backend endpoint `POST /api/exercises/rename` in `main.py`:
		- body: `{ old_title, new_title }`
		- validates trimmed non-empty values and rejects unchanged rename target
		- transaction updates `WorkoutLog.exercise_title` (case-insensitive old-title match)
		- transaction updates `ExerciseMapping.exercise_title` when a mapping row exists
		- returns `{ updated_sets, mapping_updated }`
		- returns 404 when no WorkoutLog rows match old title
		- syntax validation: `python -m py_compile main.py` passed
		- static diagnostics: `static/index.html` and `static/diagnostic.html` report no errors
	- No-check-in-today state now renders a neutral placeholder while keeping available non-check-in diagnostics visible
- Exercise canonical-title stack implemented (2026-05-02):
	- Added `ExerciseCanonical` model/table in `database.py` with fields:
		- `exercise_id` (PK)
		- `canonical_title` (not null)
		- `created_at`, `updated_at`
	- Startup-safe schema creation added in `database.py:init_db()`:
		- explicit sqlite table-existence check for `exercise_canonical`
		- creates table when missing (idempotent alongside `Base.metadata.create_all`)
	- Import canonical substitution added in `importer.py`:
		- preloads `exercise_canonical` once per sync into dict keyed by `exercise_id`
		- set-level write path uses canonical title when mapping exists
		- falls back to Hevy API title unchanged when mapping missing
	- Canonical API endpoints added in `main.py` before static mounts:
		- `GET /api/exercises/canonical`
		- `POST /api/exercises/canonical`
		- `DELETE /api/exercises/canonical/{exercise_id}`
		- GET joins canonical rows with most-recent `workout_logs.exercise_title` per `exercise_id` (nullable)
	- Exercises tab UI updated in `static/index.html`:
		- Added `Exercise Name Overrides` card above `Rename Exercise`
		- card loads from `GET /api/exercises/canonical` on each Exercises-tab activation
		- table columns: `Hevy Title | Your Name | Action`
		- inline Edit/Save flow posts to `POST /api/exercises/canonical` and refreshes rows
		- empty state copy: `No overrides set. Exercises use names from Hevy.`
- Canonical gate script added (2026-05-02):
	- New `canonical_gate.py` validates canonical CRUD endpoints against running local app
	- Script simulates importer path with controlled fake-Hevy payload to verify set-title substitution deterministically
	- Outputs PASS/FAIL per gate and summary with exit code
- Dedup gate script added (2026-05-02):
	- New `dedup_gate.py` validates dedup/index protections against SQLite DB + running local API sync path
	- Gate 1 checks index existence for `uq_workout_logs_set` in `sqlite_master`
	- Gate 2 checks duplicate natural-key groups `(workout_id, exercise_id, set_number)` are zero
	- Gate 3 records row counts before/after `POST /api/sync` with `/api/sync/status` polling and enforces `delta <= 10`
	- Prints PASS/FAIL per gate with final summary and exits non-zero on failure
- Dedup DB migration fix applied (2026-05-02):
	- Root cause: `init_db()` never created index name `uq_workout_logs_set`; model-level `UniqueConstraint` (`uq_workout_set`) did not satisfy gate check
	- `database.py:init_db()` now runs startup dedup on `(workout_id, exercise_id, set_number)` keeping earliest `id`
	- `database.py:init_db()` now executes `CREATE UNIQUE INDEX IF NOT EXISTS uq_workout_logs_set ON workout_logs (workout_id, exercise_id, set_number)`
	- Migration is idempotent and enforces hard DB-level uniqueness independent of importer behavior
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
	- WorkoutLog conflict policy updated in `importer.py` for set rows:
		- changed set insert from `on_conflict_do_nothing()` to `on_conflict_do_update()` on unique key (`workout_id`, `exercise_id`, `set_number`)
		- on conflict, only `exercise_title` and `workout_title` are updated so Hevy title renames propagate
		- all training data fields remain unchanged on conflict (`weight_lbs`, `reps`, `rpe`, `rir`, `estimated_1rm`, `is_conditioning`)
		- syntax validation: `python -m py_compile importer.py` passed
- Admin data-repair endpoint added (2026-05-01):
	- Added backend endpoint `POST /api/admin/backfill-sessions` in `main.py`
	- Endpoint backfills missing `workout_sessions` rows for `workout_id` values present in `workout_logs` but absent in `workout_sessions.hevy_workout_id`
	- For each missing workout id, source row is the earliest `WorkoutLog` record by `(date, id)` for deterministic mapping
	- Backfilled defaults:
		- `hevy_workout_id = workout_id`
		- `workout_date = earliest WorkoutLog.date`
		- `workout_title = earliest WorkoutLog.workout_title`
		- `modality = "strength"`
		- `modality_confidence = 0.0`
		- `verification_status = "verified"`
		- `verified_at = datetime.utcnow()`
		- `start_time/end_time/duration_minutes/srpe = null`
	- Response contract: `{ "backfilled": N }`
	- Syntax validation: `python -m py_compile main.py` passed
	- Runtime verification note: local API start currently blocked in this environment by missing dependency `cryptography` (`ModuleNotFoundError`)

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
- Canonical stack validation: PASS
	- `database.py` bootstrap check confirms `exercise_canonical` exists with requested columns and PK/nullability shape
	- Focused runtime check confirms importer stores canonical title in `workout_logs` when canonical mapping exists
	- Canonical CRUD route checks passed via local handler/runtime test
	- `canonical_gate.py` execution result: `SUMMARY: 6 passed, 0 failed`
	- Syntax/error checks passed for touched files: `database.py`, `importer.py`, `main.py`, `static/index.html`, `canonical_gate.py`
- Dedup gate validation: PARTIAL
	- Syntax check passed: `python -m py_compile dedup_gate.py`
	- Runtime gate execution against `/data/hevy_fatigue.db` pending environment-specific DB path availability
- Dedup index migration fix: PASS
	- `python -m py_compile database.py` passed after `init_db()` migration update
- Conflict gate script created: SYNTAX PASS
	- `conflict_gate.py` written with GateRunner, 7 gates, preflight, and cleanup blocks
	- `python -m py_compile conflict_gate.py` passed with no errors
	- Runtime execution blocked pending implementation of ExerciseConflict model, importer detection, main.py endpoints, and index.html conflict UI
- Conflict stack implementation: COMPLETE (syntax validated)
	- `database.py`: `ExerciseConflict` model added (exercise_id PK, hevy_title, stored_title, detected_at, resolved, resolved_at); `init_db()` migration block creates `exercise_conflicts` table on startup
	- `importer.py`: preloads `already_flagged` set and `stored_titles` dict per sync; upserts `ExerciseConflict` row when title drifts with no canonical and no existing open flag
	- `main.py`: `ExerciseConflictResolveInput` Pydantic model; GET `/api/exercises/conflicts`; POST `…/{id}/resolve` (upserts canonical, marks resolved); POST `…/{id}/dismiss` (marks resolved only)
	- `static/index.html`: Needs Review card (hidden until conflicts exist); nav badge on desktop + mobile exercises buttons; `loadExerciseConflicts()`, `renderExerciseConflictTable()`, `resolveExerciseConflict()`, `dismissExerciseConflict()` JS functions
	- `python -m py_compile` passed for all touched files; JS brace count balanced (842/842)
- Sync response contract + conflict detection refactor: COMPLETE (validated)
	- `main.py`: `POST /api/sync` success payload changed to `{ "status": "complete", "synced_at": "<utc iso>" }`; removed `new_sets` from sync response
	- `static/index.html`: `runSync()` now renders `Sync complete` with `synced_at` timestamp and no set-count messaging; existing cooldown/already-running behavior unchanged
	- `importer.py`: removed per-loop conflict logic (`already_flagged`, `stored_titles`, and inline `ExerciseConflict` upsert)
	- `importer.py`: added `detect_exercise_conflicts(db)` post-sync pass:
		- finds `exercise_id` values with multiple distinct `workout_logs.exercise_title`
		- excludes IDs with canonical mappings in `exercise_canonical`
		- excludes IDs with existing unresolved rows in `exercise_conflicts`
		- upserts conflict row using newest title by `date desc, id desc` and oldest title by `date asc, id asc`
	- Validation:
		- `python -m py_compile importer.py` — OK
		- `python -m py_compile main.py` — OK
		- `static/index.html` diagnostics — OK (`<script>`/`</script>`: 3/3, JS braces: 841/841)

## 5) Open Items / Next Backlog

Source of truth: see `backlog.md` for current outstanding work and release-priority tracking.
This section is historical context and may lag behind `backlog.md`.

Priority A

- Movement Trend live validation: browser click-through with real populated data (search → select → chart renders, week toggle reloads, clear resets, theme toggle rebuilds chart).
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

"Read plan.md first. Movement Trend feature is complete (backend + frontend). Continue from Priority A validation with real data. Preserve the new Today-first check-in flow, Trend-owned charts, and combined-score Today recommendation model."

