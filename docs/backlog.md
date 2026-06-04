# Hevy Fatigue — Backlog

Last updated: 02JUN2026

---

## Open Bugs

### `02JUN2026` — Pattern Stress Showing Zero Knee Stress After Heavy Quad Work
Knee pattern stress card shows 0 despite recent high-volume squat sessions. Likely a TSB signal calculation or pattern distribution issue. Needs `main.py` and pattern stress endpoint review. Investigate before speccing.

### `02JUN2026` — Regular Sync Does Not Pick Up Hevy Exercise Edits
If an exercise is renamed in Hevy after a workout is already synced, a regular sync does not re-fetch or re-process the affected workout. Full sync re-imports all data and does pick up the change, but also appends duplicate rows if the exercise_id changed (old title rows + new title rows). Root cause: importer does not delete existing `workout_logs` rows for a workout before re-inserting on full sync — it appends. Fix: on full sync, `DELETE FROM workout_logs WHERE workout_id = ?` before re-inserting sets for each workout. Long-term: detect changed workouts via `updated_at` on the Hevy API side and re-process only those in regular sync.

### `02JUN2026` — Edit Modal CSS Missing (Patterns Tab)
Modal overlay opened but rendered unstyled — `.modal`, `.modal-title`, `.modal-subtitle`, `.modal-footer`, `.pattern-examples`, `.ex-row`, `.ex-list`, `.presets`, `.preset-btn`, `.slider-num-row`, `.pct-num-input`, `.pct-sym`, `.split-bar`, `.split-seg` CSS blocks all missing from stylesheet. Partially resolved: `.modal` box CSS restored. Slider layout still broken — `input[type="range"]` global `width: 100%` conflicts with flex layout in `.slider-num-row`; grid-based fix specced but not yet confirmed. In progress.

---

## Planned Features / Refactors

### `02JUN2026` — Session Verification: Add Workout Detail Context + Unverified Indicator
Currently the verification UI shows only the session title — not enough context to verify confidently. Two changes needed:
- **Detail view on verification card:** show date, duration, modality, sRPE, exercise list with set count. User should be able to confirm the session is what the title says it is before verifying.
- **Unverified indicator:** badge or dot on the Workouts tab nav button when one or more sessions are pending verification. Mirrors the pattern of the existing unreviewed exercise indicator.

### `02JUN2026` — Move Exercise Naming / Needs-Review Card to Exercises Tab
The canonical name "needs review" card currently lives on the Patterns tab. Patterns is for movement distribution (Knee/Hip/Push/Pull splits) — nomenclature is an exercise-level concern and belongs on the Exercises tab. Changes needed:
- Move needs-review card UI to Exercises tab
- Add indicator (badge or flag) on the Exercises tab nav button when one or more exercises have unreviewed canonical names
- Patterns tab should be clean of naming concerns after this move

### `02JUN2026` — Move Movement Trend to Exercises Tab
Movement Trend (exercise search + metric toggle + time window chart) currently lives on the Workouts tab. It is an exercise-level metric, not a session-level one. Workouts tab should own session-level views only. Exercises tab should own all per-exercise views: metrics browser, naming/canonical review, and movement trend. Move the Movement Trend card to the Exercises tab.

### `02JUN2026` — Dead Code Audit
Review `index.html` and `main.py` for dead code — unreachable JS functions, orphaned DOM sections, unused endpoints, and stale CSS classes. Known candidate: `tab-trend` section may still exist in DOM but be inaccessible from nav. Audit before any major feature work to reduce noise for Copilot.

---

### `26MAY2026` — Canonical Name Notification
If exercise name needs review for canonical naming, there should be a flag of some type.

Move renaming confirmation to Exercises tab.

Movement trend from Workouts also should move to Exercises tab.

### `11MAY2026` — MRV Stats
Surface Maximum Recoverable Volume indicators informed by JTS fatigue framework.

Reference material:
- https://www.jtsstrength.com/fatigue-indicators-and-how-to-use-them/
- https://www.jtsstrength.com/fatigue-explained/
- https://osf.io/6z3xu/overview

**Foundation inputs:**
- Rolling gross load — normalized using existing session stress scores as common currency; both ST/HYP and CON/CAR pathways already output to same arbitrary unit system via respective scaling factors; rolling load = sum of session stress scores over 28-day flat window
- Rolling average fatigue score — ready now, sourced from `daily_readiness`
- e1RM trend direction — Brzycki formula applied to best set per ST session; tracked per pattern (Knee/Hip/Push/Pull) via `exercise_mappings`; trend direction via linear regression slope over recent data points

**Scope:**
- Systemic level first
- Pattern level (Knee/Hip/Push/Pull) as second layer
- No muscle group granularity, no set counting

**Display intent:**
- Current state read — where are you right now
- Trend over time — volume and fatigue moving together so MRV is visually readable
- e1RM trend as adaptation confirmation signal

**Design position:**
- v1 is a correlation view, not a threshold calculator — thresholds emerge from the athlete reading the data, not from the app computing them; honest given current data history length

**Scale factor calibration — prerequisite before MRV numbers are meaningful:**
- `CON_SRPE_SCALE` (existing, default 29.0) and `HYP_SRPE_SCALE` (new, default 29.0) — separate named constants, both in `app_settings`, user-adjustable
- Neutral prior — both start equal; calibrated independently via controlled sessions over time
- Calibration protocol: two fixed controlled sessions:
  - HYP — full-body dumbbell circuit (no per-set RPEs, sRPE logged immediately after)
  - CON — Cindy (20min AMRAP: 5 pull-ups, 10 push-ups, 15 air squats, sRPE logged immediately after)
  - Entry condition: morning check-in ≥7/10 with full rest day prior
  - Minimum 3 runs per modality before drawing conclusions
- App handles calibration automatically — checkbox on HYP/CON session cards ("Mark as controlled calibration session"); pre/post fatigue scores pulled from existing check-in data; delta calculated automatically; derived scale factor surfaced in Settings when minimum runs met; user applies derived factor or enters manually
- Re-calibration expected as training style shifts — not a one-time setup

**Build prerequisites (in order):**
1. ~~HYP sRPE fallback~~ — COMPLETE (merged 11MAY2026)
2. Calibration feature — checkbox on session cards, auto delta calculation, Settings summary with derived scale factor
3. Controlled calibration sessions — run protocol, apply derived scale factors
4. MRV view — build on calibrated inputs

**Backend:**
- No new tables required for v1; all data across `workout_sessions`, `daily_readiness`, `workout_logs`, `exercise_mappings`
- New endpoint: `/api/mrv/summary` — computes all three signals for requested window, returns systemic + per-pattern breakdown
- 28-day flat window default (not EWMA — flat window reflects current training reality)
- e1RM signal only meaningful for ST sessions; HYP/CON gap noted for documentation

---

### `08MAY2026` — MacroFactor Nutrition Integration
Pull daily macros (protein, carbs, fat) from Apple Health via Claude iOS Health integration; export as structured JSON; ingest into SQLite; calculate calories as `(P×4) + (C×4) + (F×9)`; use prior-day nutrition adequacy as a covariate in tonnage→fatigue correlation to isolate training volume signal from nutritional confounders; flag sessions where poor nutrition may explain fatigue rather than volume.

**Dependencies (must be resolved in order):**
1. Apple Health nutrition sync enabled in MacroFactor
2. Apple Health → JSON export pipeline built
3. Tonnage → fatigue correlation feature built first
4. MRV Stats feature complete (consumer of the cleaned signal)

---

## Design Decisions / Closed / Won't Fix

| Item | Resolution |
|---|---|
| Edit modal `.open` vs `.active` class mismatch | COMPLETE — 02JUN2026. `openModal()` and `closeModal()` corrected to use `.active` matching the CSS rule. |
| Docs page check-in schema | COMPLETE — updated `static/docs.html` on 21MAY2026 to match implemented 0–4 fields, subjective weighting formula, current TSB labels, and joint advisory behavior. |
| Trend history window | Fixed at 30 days. `_trendSlice` hardcodes `slice(-30)` by design. Range buttons change baseline smoothing term only. |
| HYP sRPE fallback | COMPLETE — merged 11MAY2026. `sRPE × duration_minutes / HYP_SRPE_SCALE` when ≥50% of sets lack RPE values. |
| TSB state labels | COMPLETE — removed from trend tooltip and session cards 11MAY2026. Today page label preserved. |
| CTL time constant | COMPLETE — EWMA with τ=42 days implemented per Allen 2019 / TrainingPeaks standard. |
| Sticky AI model selection | COMPLETE |
| Sticky navbar on desktop | COMPLETE |
| Settings view mobile layout | COMPLETE — 22MAY2026. |
| Combined score formula label truncation | COMPLETE |
| Pattern stress dots vs trend chart contradiction | COMPLETE — merged 16MAY2026. `_pattern_tsb_signal(tsb, ctl)` replaces ATL/CTL ratio. |
| Pattern stress card color/label | COMPLETE — Normal → green, Elevated → yellow, High → red, Fresh → teal/blue. |
| Pre-check-in misleading values | COMPLETE — 16MAY2026. |
| Today page chart load speed | COMPLETE — 17MAY2026. Load time halved (~3s → ~1.5s). |
| 7-day Readiness Trend band adjustability | COMPLETE |
| CTL lookback window | COMPLETE — switched to EWMA τ=42 days from flat 6-month rolling window. |
| Force Full Sync button | COMPLETE |
| Movement Trend stale exercise names | COMPLETE |
| Improved Exercise List | COMPLETE |