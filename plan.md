# Hevy Fatigue - Local Plan Snapshot

Last updated: 2026-04-19

## 1) Current Product State

- Subjective-first fatigue model is the primary recommendation driver.
- Daily recommendation is based on:
	- subjective base fatigue score from the check-in
	- bounded training-stress modifier from recent loading
- Dashboard language is fatigue/readiness oriented.
- Advanced calibration exists in Settings:
	- custom fixed thresholds (optional)
	- adaptive percentile mode (optional)
	- lookback and minimum-entry controls

## 2) UI and Frontend Status

- Main UI is single-page in static/index.html.
- Theme switching now refreshes both charts (no manual page refresh needed).
- Narrow-screen behavior improved for Dashboard controls.
- Settings tab now uses desktop two-column placement:
	- API key card top-left
	- Advanced calibration right column (spanning down)
	- Hevy sync card lower-left
- Header icon uses resources/favicon.png.

## 3) Assets and Paths

- Images moved to resources/.
- FastAPI serves:
	- /static -> static/
	- /resources -> resources/
- README and frontend image references were updated to /resources.

## 4) Documentation Status

- README refreshed for current model language.
- Screenshot placeholders were removed.
- Dedicated Screenshots section added (Dashboard, Workouts, Exercises, Log, Settings).

## 5) Suggested Next Backlog

Priority A

- Verify all moved image assets load correctly in both local and server environments.
- Confirm mobile behavior on iPhone SE width and real-device Safari after final CSS tweaks.
- Confirm chart colors/contrast in light and dark themes for accessibility.

Priority B

- Remove remaining internal variable names that still use legacy tsb naming where safe.
- Add tiny UI polish pass for spacing and card rhythm in Settings and Dashboard.
- Add a short deployment workflow section in README for quick local-first iteration.
- Evaluate a future "Recovery Rate" feature as an optional replacement/complement to legacy freshness-style framing.

Priority C

- Optional: add a lightweight release checklist file for merge/deploy sanity checks.

## 6) Quick Context Prompt For Future Sessions

Use this when you come back:

"Read plan.md first, then continue implementation from Priority A. Keep subjective-first fatigue language, preserve the two-column Settings layout, and do not reintroduce TSB-first wording in user-facing text."

