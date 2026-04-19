# Hevy Fatigue - Plan and Bookmark Notes

Last updated: 2026-04-19

## Current Direction

- Keep the model subjective-first.
- Keep user-facing language simple: fatigue, readiness, short-term fatigue, long-term fatigue, daily recommendation.
- Avoid TSB-first wording in UI messaging.

## Readiness and Fatigue Score Model

- Subjective base score comes from daily check-in inputs (0-4 fields), weighted into a 0.0-1.0 value, then scaled to 0-10.
- Training modifier is bounded and applied on top of the subjective base.
- Final fatigue score = clamp(subjective base + training modifier, 0, 10).
- If no check-in exists for today, fallback uses a neutral base (5.0) plus training modifier.
- Recommendation buckets are generated from fatigue thresholds:
  - >= 8.0: Large Decrease
  - >= 6.5: Decrease
  - >= 4.5: Continue
  - >= 3.0: Increase
  - < 3.0: Large Increase
- Calibration settings support:
  - Custom thresholds (manual, optional)
  - Adaptive percentile mode over recent fatigue history
  - Lookback and minimum-entry controls


## UI State Snapshot

- Settings desktop layout:
  - API key card in upper-left
  - Advanced calibration in right column
  - Hevy sync in lower-left
- Theme toggle now re-renders both charts (no manual refresh needed).
- Dashboard narrow-width controls were tuned for very small screens.

## Assets and Paths

- Images now live in resources/.
- Server mounts:
  - /static -> static/
  - /resources -> resources/
- Frontend icon and recommendation face images use /resources paths.
- README screenshots now reference resources/*.png.

## Bookmarked / Deferred Items

- Keep the current freshness concept for now; possible future rename to recovery rate.
- Keep architecture simple (single-page static/index.html) unless complexity forces a split.
- Keep advanced calibration opt-in only; default mode should remain clearly documented.
- One proposed UI change was intentionally skipped/bookmarked during this cycle and can be revisited later if needed.

## Next Priority Backlog

1. Verify all resources paths and screenshots load correctly in local and deployed environments.
2. Do a final language sweep for any remaining internal TSB wording leaking into user-facing text.
3. Validate very-small-screen behavior (iPhone SE width) for Dashboard and Settings.
4. Optional: clean up legacy variable names that still use tsb naming internally.

## Reuse Prompt For Future Chats

Read plan.md first. Continue from Next Priority Backlog item 1. Keep subjective-first fatigue logic and do not reintroduce TSB-first user-facing terminology.
