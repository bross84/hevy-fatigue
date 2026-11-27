# Stage-Gated Plan

## Completed

### 2026-06-15 - Workout session single-row layout rewrite
- Scope: Replaced two-row-per-set table (row-a showing set label + load, row-b showing @RPE + a.RPE) with single-row-per-set layout featuring 6 columns: Set | Load | Reps | @RPE | a.RPE | e1RM. Updated CSS for fixed column widths and tight padding (5px 8px). Pre-filled reps inputs: working sets with planned reps, AMRAP with placeholder ★, jokers with 1. All reps editable, no spinner arrows.
- Gates:
1. Activate program, start session: single-row table renders with 6 columns per set: PASS
2. Set labels display correctly (1, 2, 3+ bold, 4J/5J/6J): PASS
3. Load column: working/AMRAP show text "Xkg (Ylbs)", jokers show input field: PASS
4. Reps column: working pre-filled with planned (5,6), AMRAP placeholder ★, joker pre-filled 1: PASS
5. @RPE column: working "5 / 75%", AMRAP "7 / 80%", joker "—": PASS
6. a.RPE column: number input (min 1, max 10, step 0.5) for all sets: PASS
7. e1RM column: empty initially, calculates Epley formula when AMRAP reps filled: PASS (8 reps → 170kg, 10 reps → 180kg)
8. Finish Session button disabled until AMRAP reps filled, enabled after: PASS
9. No spinner arrows on number inputs (CSS -moz-appearance + WebKit hiders): PASS
10. No "tier" word in rendered UI: PASS

### 2026-06-13 - Day view Loading column replaces Sets and @RPE
- Scope: Updated program day movement list in `index.html` to render a single `Loading` column from `wave_params.sets` with inline formats: working `reps@rpe`, AMRAP `reps+@rpe`, Joker `repsJ`; returns `—` when `wave_params` is null/malformed or invalid.
- Gates:
1. Open day with saved movement containing working + AMRAP + Joker sets: PASS
2. Loading format renders as joined set scheme (observed `5@5 / 5@6 / 5+@7 / 1J / 1J / 1J`): PASS
3. AMRAP set uses `+` suffix with RPE (`5+@7`): PASS
4. Joker sets use `J` suffix with no RPE (`1J / 1J / 1J`): PASS
5. `@RPE` column removed; header is `Movement | Loading | Actions`: PASS

### 2026-06-12 - Session set rpe_percentage field
- Scope: Added set-level rpe_percentage in GET /active-blocks/{id}/session using get_rpe_percentage(target_rpe, reps).
- Gates:
1. python -m py_compile main.py: PASS
2. uvicorn main:app --reload --port 8126 startup: PASS
3. GET /active-blocks/{id}/session returns sets[*].rpe_percentage as float or null: PASS
- Notes:
1. PRAGMA table_info verified for rpe_chart before implementing lookup usage.

### 2026-06-12 - Session route fix for TM/week/set flags/BBB
- Scope: Fixed GET /active-blocks/{id}/session to use tm_{slot_id}, explicit week_number semantics, derived set flags, and BBB weight output.
- Gates:
1. python -m py_compile main.py: PASS
2. uvicorn main:app --reload --port 8126 startup: PASS
3. GET /active-blocks/{id}/session with active block + TM set returns non-null first_set_weight_kg: PASS
4. Session slot payload includes is_amrap, jokers_enabled, sets, and bbb_weight_kg: PASS
5. python -m py_compile main.py (final): PASS
- Notes:
1. PRAGMA table_info verified for active_blocks, blocks, days, tiers, exercise_slots, e1rm_log, and app_settings before edits.

### 2026-06-12 - TM API wiring in Programs UI
- Scope: Replaced TM localStorage access in index.html with backend TM endpoints and updated nav order to Workout, Program, Settings.
- Gates:
1. Day view slot with no TM shows amber Set TM badge: PASS
2. Enter TM and blur saves value and shows WM dual-unit format: PASS
3. Reload page retains TM via backend fetch: PASS
4. localStorage search confirms no TM-related key usage remains in index.html: PASS

### 2026-06-12 - TM + delete endpoint backend work
- Scope: Added training-max settings endpoints and microcycle/day delete endpoints in main.py with guard rails and ordered deletes.
- Gates:
1. python -m py_compile main.py: PASS
2. uvicorn main:app --reload --port 8126 startup: PASS
3. POST /settings/tm with slot_id=1, value_kg=140.0: PASS
4. GET /settings/tm/1: PASS
5. GET /settings/tm/9999 returns 404: PASS
6. DELETE /days/{id} when only day in cycle returns 400 with expected detail: PASS
- Notes:
1. Column usage was verified with PRAGMA table_info for app_settings, blocks, days, and exercise_slots before implementing new SQL.

### 2026-06-12 - Programs tab UX rewrite
- Scope: Rebuilt Programs tab in index.html to a three-screen flow (list -> program -> day) with mobile-first layout.
- Gates:
1. Server startup on port 8126: PASS
2. Create program and open detail immediately: PASS
3. Add microcycle and auto-navigate to Day 1: PASS
4. Add movement with exercise search and immediate set grid: PASS
5. Save movement and render in day list: PASS
6. Ensure rendered UI does not contain the word "tier": PASS
7. Unsaved movement TM warning badge (Set TM, amber class): PASS
- Notes:
1. TM persistence is localStorage fallback keyed by slot id with TODO for backend endpoint.
2. Delete cycle/day UI is implemented with confirmation and API calls; backend delete routes are currently missing.
