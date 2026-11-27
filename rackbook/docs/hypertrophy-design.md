# Hypertrophy training design (parked until the switch)

_Moved from the old training-app backlog during #142 (2026-11-27). Open work lives in GitHub issues; this is the agreed design for when Brian moves to hypertrophy training._

Requested 2026-10-18. Keep the current strength workflow for now; build this when Brian transitions to hypertrophy training, potentially with few or no barbell movements.

## Dynamic double progression — Brian's method

Prescribe a set count and rep range, such as leg press **4 × 8–10**, with many movements trained close to or at failure. Adjust load between sets based on performance and Brian's judgment of whether the next set can stay within the range:

1. Set 1: 10 reps; increase weight if another set can still land within 8–10.
2. Set 2: 10 reps at the higher weight, harder; increase again if the range still seems achievable.
3. Set 3: 9 reps @10 at the heaviest weight; anticipate falling below 8 on the next set and reduce the load.
4. Set 4: 8 reps @9 at the reduced weight.
5. **Next session starts at set 3's weight: the heaviest load successfully completed within the rep range in the previous session.** Then repeat the within-session adjustments.

The logger should retain each set's actual load, reps and RPE, support the prescribed rep range, and offer that heaviest qualifying load as the next session's starting point, with manual override. Increases, holds and reductions during the session remain Brian's decisions. This is not a rule requiring all four sets to reach 10 before increasing, nor a separate progression ladder carried forward for each set position. Intentional lighter later sets reflect within-session fatigue and must not automatically be labelled a strength decline. Compare performance across comparable sessions and efforts; do not treat reaching failure alone as a reason to remove sets. Keep progression exercise-specific when substituting equipment or movements.

## One fatigue system, per-exercise progression, mode defaults

Agreed 2026-10-18. The shared goal in strength, hypertrophy and mixed training is to monitor fatigue and progression, then help judge when to add/remove sets or consider changing an exercise. Strength and Hypertrophy are presets for defaults and interface emphasis, not separate monitoring systems or restrictions on how a workout can be built.

- **Shared monitoring:** use recorded workload, comparable performance, soreness/pain and BW context across training modes. Retain collection gates and uncertainty; suggestions remain reviewable and do not automatically rewrite training. Performance evidence depends on the exercise: marked TS/e1RM where appropriate, or load/reps at comparable effort where no TS is used. A single monitoring system does not mean applying the current TS thresholds unchanged to every exercise.
- **Per-exercise progression support:** initially support the existing TS/e1RM/TM/RPE-based strength workflow and Brian's specific dynamic double progression described above. Allow manual targets/loading without requiring a named progression method; monitoring should use available actual training data even when Rackbook does not automate that exercise's progression. Missing or incomparable evidence should be shown as such, not forced into a TS or DDP model.
- **Modes set defaults:** Strength can emphasize TS references and RPE-planned loading; Hypertrophy can emphasize rep ranges, effort and DDP starting loads. Individual exercises can override those defaults. Changing a preset must preserve history and explicit exercise choices; the precise settings UI remains for implementation.
- **Powerbuilding fits within the same workout:** for example, TS-based squat followed by DDP leg press and manually loaded leg curls. No separate third system is needed. Keep each exercise's performance baseline distinct while considering overlapping muscle workload/soreness across exercises; do not pool their strength numbers. Muscle mapping and workload attribution need explicit rules when implemented.
- **Shared foundation:** exercise identities, actual set records, workout drafts, units, rest timers, microcycle loading/completion, history and Hevy saving remain common. Progression assistance is Rackbook-side behavior; it must not depend on Hevy representing the progression method. Continue sending the resulting actual workout through the existing integration.
- **Scope boundary:** modality-agnostic monitoring is the goal, not a universal progression engine or a recreation of Hevy. Do not build a catalogue of every progression model, a generic programming language, or a plugin framework in anticipation of hypothetical methods. Add another automated method only for a concrete training need Brian requests. Manual logging remains a valid first-class workflow.

Parked for the hypertrophy transition; no current training behavior changes are requested by this design update.
