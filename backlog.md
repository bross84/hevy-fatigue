# Hevy Fatigue Backlog

## 🔴 Pre-Release (must fix before public release)
Items that are known bugs or missing features that would affect any user.

- [ ] Update TSB training state labels to load-descriptive language in Today recommendations.
- [ ] Resolve the contradictory Today-card state where a Fatigued training state can appear with a low fatigue score.
- [ ] Complete README and FAQ documentation for public-facing release use.
- [ ] Merge v2 to main after release-gate QA is complete.
- [ ] Run full Movement Trend live validation with populated data (search/select/chart render, window toggles, clear/reset, theme redraw).
- [ ] Run real-data visual QA for Trend and Session Log realism (including inline row edit behavior and verified/pending filters).
- [ ] Run cross-device pass (Safari iOS + Chrome Android) for Today check-in button groups and endpoint labels.
- [ ] Run Workouts regression click-through: verify queue -> log refresh, pending/verified edit flows, detail/edit mutual exclusion.
- [ ] Validate full served-app runtime and API behavior in an environment with app dependencies installed (not file:// context).

## 🟡 Bookmarked (flagged for future work)
Items that have been explicitly flagged during development as things to revisit but are not blocking release.

- 7-day readiness trend bands should be user-configurable.
- Movement Trend chart date axis currently shows month/day only; include year context.
- Expand exercise stats page similar to Hevy Insights exercise detail view:
  Total, Active, Gaining, Declining summary plus per-exercise charts.
- Add a dedicated movement pattern percentage editor experience on the Exercises tab.
- Optional cleanup of obsolete helper names/comments still referencing legacy dashboard wording.
- Add a lightweight release checklist for pre-commit UI and endpoint regression checks.

## 🟢 Nice to Have (low priority wants)
Features or improvements that would be good eventually but are not urgent.

- Auto-sync on page load or tab focus (similar to Hevy Insights behavior).
- Add a clearer in-app confirmation UX around workout deletion handling.
- Add in-app notification surfacing for deleted workouts.

## ✅ Recently Completed
Last 10 completed items with brief descriptions for context.

1. Preserved verification state on initial import in importer so reimported sessions keep verification_status, verified_at, and srpe.
2. Reworked Needs Review section UI into a collapsible card with conflict-aware default expansion behavior.
3. Removed Exercise Name Overrides and Rename Exercise cards from Exercises tab and cleaned related frontend state.
4. Added inline Add Override flow inside Needs Review with autocomplete, canonical save, cancel, and inline error feedback.
5. Removed sync cooldown from POST /api/sync while keeping already-running lock protection.
6. Added incremental sync gate coverage for first-sync bootstrap, cursor advancement, delete simulation, and canonical substitution checks.
7. Added one-time incremental sync migration and GET /api/sync/last-sync endpoint.
8. Refactored importer into initial import + incremental sync paths with shared workout processing logic.
9. Added Hevy workout events client support (GET /v1/workouts/events) with robust error handling.
10. Added startup dedup migration + unique index enforcement for workout_logs natural key protection.
