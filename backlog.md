# Hevy Fatigue Backlog

## 🔴 Pre-Release (must fix before public release)
Items that are known bugs or missing features that would affect any user.

- [x] Fixed 30OCT2026: HYP sRPE fallback double-counting in `calculate_stress_scores()`. Verified HYP sessions with sRPE, duration, and >=50% missing RPE now use Pathway 4 exclusively; their sets are excluded from Pathway 1. Existing fallback scaling and pattern distribution are preserved. Regression tests: `tests/test_hypertrophy_stress.py`.
- [ ] Resolve dead code: tab-trend section still exists in DOM but is inaccessible from nav - remove section HTML and associated JS (renderVolFatigueView, activateTrendTab, _vfChartRpe/Tonnage/Sets, _vfRenderCharts).
- [ ] Complete README and FAQ documentation for public-facing release use.

## 🟡 Bookmarked (flagged for future work)
Items that have been explicitly flagged during development as things to revisit but are not blocking release.

- Add e1RM trend direction tag (Gaining / Steady / Declining) per exercise on the Exercise Metrics detail view, derived from linear regression slope over recent sessions.
- Optional cleanup of obsolete helper names/comments still referencing legacy dashboard wording.
- Unit toggle in settings, selection of Lbs or KG

## 🟢 Nice to Have (low priority wants)
Features or improvements that would be good eventually but are not urgent.

- Auto-sync on page load or tab focus (similar to Hevy Insights behavior).
- Add a clearer in-app confirmation UX around workout deletion handling.
- Surface in-app notification when workouts are removed during sync (deleted from Hevy).

## ✅ Recently Completed

- 30OCT2026: Pattern Stress preserves exact soreness ratings, residual decaying load, and a separate gradual trend. Completed training is no longer discarded during monitoring gaps. Added pattern decay, evidence-gap, causal-cutoff and UI tests.

- 30OCT2026: Shared smoother daily recommendations with immediate worsening, confirmed single-level recovery, and “Continue Training as Normal” for insufficient data. Startup/long-gap monitoring gates preserve continued training history. Dashboard, chart, log, diagnostics and AI snapshot agree. Regression coverage includes monitoring gaps and UI fallback rendering.
Last 10 completed items with brief descriptions for context.

1. Complete dashboard layout overhaul - sidebar (readiness, pattern stress gauges, recent sessions) + full-width chart stack, responsive single-column on mobile.
2. Check-in moved to modal - opens on page load if no check-in today, accessible via prompt banner.
3. New color theme - #3772FF primary accent, dark slate (#0F172A/#111827), light mode (#F1F5F9/#FFFFFF).
4. Bottom nav (mobile) + bottom sheet More menu replacing hamburger/drawer - Dashboard, Exercises, Workouts, AI Coach, More.
5. Top nav restructured - Dashboard, Exercises, Workouts, AI Coach, Log, Patterns, Docs, Settings; tab renamed AI -> AI Coach.
6. Vol-Fatigue correlation chart - daily tonnage/RPE load/set count as bars vs rolling readiness as dashed line; signal toggle (Tonnage/RPE Load/Sets); block window selector (4/8/12 weeks/custom).
7. Per-Pattern Fatigue Trend - ATL and tonnage EWMA per pattern (Knee/Hip/Push/Pull); ATL/Tonnage signal toggle; 30-day window with 7/14/30 day smoothing term selector.
8. Pattern stress redesigned as horizontal gauge rows - fill length + color (green/amber/red) replaces 2x2 dot grid.
9. Toggle button groups redesigned as segmented strips (Option D) - joined, slim, solid accent fill on active.
10. Readiness orientation follow-up - subjective readiness scaling was reverted in main.py so `/api/volfatigue/summary` and `/api/readiness/combined-history` again move higher with more fatigue.
11. Importer timezone fix - converted workout date extraction from UTC date to local date using `TZ` + `zoneinfo` in importer so late-evening local workouts no longer shift to next-day UTC date.
