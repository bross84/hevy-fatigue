# Hevy Fatigue Backlog

## 🔴 Pre-Release (must fix before public release)
Items that are known bugs or missing features that would affect any user.

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
10. Per-pattern tonnage EWMA added to training load history payload - ton_atl field per pattern, same EWMA decay as ATL, tonnage distributed via pct_* exercise mapping weights.
