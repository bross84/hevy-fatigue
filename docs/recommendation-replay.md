# Offline recommendation replay

`tools/replay_recommendations.py` compares daily recommendation stability without
importing either application, contacting Hevy, initializing a database, recording
Rackbook trial entries, or changing production recommendations.

Input is a private folder containing JSON responses from these read-only endpoints:

- Hevy Fatigue `/api/readiness/log` -> `hevy-readiness.json`
- Hevy Fatigue `/api/readiness/combined-history?days=<full-check-in-span>` -> `hevy-combined-history.json`
- Hevy Fatigue `/api/workouts/recent?count=<enough-for-complete-history>` -> `hevy-workouts.json`
- Rackbook `/fatigue-trial/dashboard` -> `rackbook-trial-dashboard.json`

Keep acquisition timestamps, endpoint URLs, deployment revisions when known and
SHA-256 hashes in `provenance.json`. Do not export settings/credentials. Store
private inputs and generated results under git-ignored `data/analysis/`.

Run from the repository root:

```powershell
python tools/replay_recommendations.py --input data/analysis/2026-10-30
python -m unittest discover -s tests -v
```

The tool writes `report.md`, `daily-replay.csv` and `replay-summary.json` beside the
inputs. These are retrospective reconstructions, not an audit of originally
shown recommendations. Workouts on/after the target date are excluded to avoid
using the outcome workout as pre-workout evidence. The exported history scores
are retained separately because their date window differs from the dashboard.
Missing check-ins remain gaps. API summaries round tonnage, do not fully expose
session identity, and normalize missing daily ratings to zero. For stronger
reconciliation use consistent database backups and Rackbook's existing
`fatigue_trial_replay.py` with exact workout/exercise IDs.

The experimental `offline-recovery-v1` candidates use the same raw score and fixed
thresholds as the current model. One slows recovery using 35% today's fatigue and
65% prior memory while allowing worse scores immediately. The second additionally
requires two consecutive check-ins beyond a 0.5-point threshold buffer, advancing
at most one tier toward increased training. Gaps over seven days reset state;
initial/reset days are explicitly marked. These parameters are provisional.

Compare switches, two-or-more-tier jumps, immediate reversals, time spent in each
recommendation and extra conservative days. Lower volatility alone is not model
validation; delayed recovery can create unnecessary warnings. This experiment
retains the legacy tonnage signal and its limitations.

Rackbook's frozen `shared-trial-v0` records remain a separate cohort. A prospective
candidate must have a new model version, immutable input/state snapshots, explicit
recording/cutoff times, exact identity links, and separately defined movement
outcomes. Preserve original daily 0-4 and movement soreness 0-3 scales, nulls,
local exact RPE/weights and TS markers. Never backfill invented TS observations or
rewrite existing predictions. Daily action labels and movement-performance
predictions have different meanings and cannot share an accuracy denominator.

## Implemented daily model

`recommendations.py` contains `recovery-confirmation-v1`. Unlike the initial
experimental replay, it withholds directional advice until three consecutive
complete observations establish monitoring, and reacquires after gaps over seven
days. It uses the same recovery/confirmation policy and retains imported workouts
through gaps. Missing today, partial ratings or an insufficient workout baseline
produce `insufficient_data` with the label **Continue Training as Normal**.

The workout gate requires three positive-tonnage training dates and at least 28
days since the oldest inside the prior 180 days. These are explicit provisional
rules; they do not establish physiological recovery or model accuracy. The
baseline remains the existing tonnage/26 calculation. The main history adapter
aggregates exact database tonnage once and rebuilds state from all check-ins
before slicing the requested chart range. Repeated requests never advance state.

`tests/test_monitoring_recommendations.py` covers startup, long/short monitoring
gaps, continued training, incomplete data, evidence boundaries, causal windows,
recovery confirmation and HTTP consistency across dashboard/history/log/diagnostics.
`node tests/test_recommendation_ui.cjs` checks fallback rendering, smoothed scores,
chart gaps and diagnostics without contacting a live service.

## Other-PC continuation and live capture diagnostics

Rackbook's new trial arm freezes the actual daily model alongside the legacy
movement trial; it does not rewrite the historical replay or original trial data.
The October 30 unavailable captures later proved readable via a fresh probe,
but their original failure cause remains unknown. New Rackbook diagnostic logs
identify future failures without altering frozen observations. See the
[cross-project handoff](https://github.com/bross84/rackbook/blob/main/docs/fatigue-handoff.md)
for current status, update/verification commands and a development checklist.
The local private exports referenced above are intentionally not committed;
obtain new read-only snapshots if continuing analysis elsewhere.
