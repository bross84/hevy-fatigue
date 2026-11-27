# Hevy Fatigue

Training monitoring and logging around Hevy workouts: how much work was done, how the athlete responds, and what the AI coach is told about it.

## Language

**Stress index**:
A descriptive estimate of a movement session's training dose, from its working sets relative to an estimated max. It describes work done; it is not a recovery limit.
_Avoid_: SI score, fatigue, load

**Central stress**:
The mechanical, muscle-and-tendon part of the stress index, driven mostly by how heavy the sets are relative to the athlete's max.
_Avoid_: CNS fatigue

**Peripheral stress**:
The metabolic, muscle-fibre part of the stress index, driven by effort and reps.
_Avoid_: Volume load

**Typical session**:
The median stress index of a movement's sessions in the preceding eight weeks, with an 80–120% usual range around it.
_Avoid_: Normal, optimal zone

**Movement pattern**:
One of Knee, Hip, Push or Pull, the four groups every exercise is divided across.
_Avoid_: Muscle group, body part

**Exercise mapping**:
An exercise's percentage split across the four movement patterns, either auto-classified or confirmed by the athlete.
_Avoid_: Classification, tag

**Pattern stress index**:
A movement's stress index divided across movement patterns by its exercise mapping and summed over rolling 7-day windows ending on the report date. It is never grouped by calendar week.
_Avoid_: Pattern Stress, weekly SI, calendar week

**Pattern Stress**:
The dashboard card showing each movement pattern's decaying training load alongside soreness and a gradual fatigue trend. A different quantity from the stress index.
_Avoid_: Stress index, pattern stress index

**Microcycle**:
One week of training days, completed in order at the athlete's own pace; one of the weeks of a plan. It is not a calendar week and has no fixed length in days. The app's Microcycles page holds these.
_Avoid_: Plan, calendar week

**Plan**:
A full training block, usually about six weeks, made of microcycles. The app does not group microcycles into plans yet (#187); until then a microcycle's Program, Cycle and Week numbers show which plan it belongs to.
_Avoid_: Microcycle, program (for one week)

**Skipped day**:
A microcycle day the athlete chose not to train. It counts as finished for plan progress but not as trained, and it never creates or changes a Hevy workout.
_Avoid_: Missed day, completed manually

**Opening review** (replaced by the weekly coaching call):
The AI Coach review that used to start by itself when the athlete confirmed the check-in for the first day of a microcycle. Saved ones still open; new ones no longer start automatically.
_Avoid_: Weekly review

**Closing review** (replaced by the weekly coaching call):
The AI Coach review of a finished microcycle that used to start at the first check-in after the last day. Saved ones still open; the weekly coaching call now does this look-back.
_Avoid_: End-of-week review, weekly review

**Progress status**:
A movement's label from comparing its estimated max over the last four weeks with the four weeks before: progressing, flat, declining, or insufficient evidence. It describes what the logs show; it does not say why, and it is not a recommendation to change the program.
_Avoid_: Stall, plateau, regression

**Proposal outcome**:
What happened after a plan proposal was saved: how far its draft microcycle got, whether the athlete edited it, and how the proposed movements' progress status compared before and after. It is a record, not a grade, and does not show that the proposal caused anything.
_Avoid_: Result, success, effectiveness

**Plan proposal**:
A week of training the AI coach suggests in a reply. It is advice until the athlete saves it as a draft microcycle.
_Avoid_: AI plan, recommendation

**Weekly coaching call**:
The one AI Coach session per finished microcycle, starting by itself on the Log page when the microcycle rolls over, whatever the calendar day, or at the next pre-training check-in. It reviews the microcycle that ended and lays out the next one for the athlete to accept, change, or run back unchanged. It replaced the opening and closing reviews (ADR 0002).
_Avoid_: Monday check-in, weekly review, end-of-week review

**Plan change**:
An edit to an existing microcycle that the AI coach suggests in a reply, shown day by day on a Suggested change card. It is advice until the athlete taps Accept, can be undone, and never touches trained or skipped days or sets weights.
_Avoid_: AI edit, auto-update, applied recommendation

**Run it back**:
The athlete's choice in a weekly coaching call to repeat the finished microcycle unchanged as the next, active one, without waiting for the coach.
_Avoid_: Repeat week, copy plan

**Draft microcycle**:
An inactive saved week, created from a plan proposal or by hand, that the athlete reviews and activates.
_Avoid_: Pending plan, AI-applied plan

**Week text**:
A training week written in the builder's shorthand: `Week N Day N` headings, `#movement` lines and sets such as `1x3@8 TS, 3x5@7 BO`. The app reads it into one microcycle per week; it never guesses a movement.
_Avoid_: Import, spreadsheet, program parser

**Callout**:
A word in week text saying how a group of sets is run: TS, BO (back-off), + (AMRAP), DS / DS2 (drop sets), myo, DDP or TM90. For now the Log page shows callouts as a label and the athlete chooses the weights. Effort labels such as ME and RE are not callouts and are ignored.
_Avoid_: Tag, set type, ME/RE label

## Two apps in one repo

The repo holds two applications served by one FastAPI host, and several file names repeat between them. The root file belongs to the host; the `rackbook/` file belongs to the training app.

**Host app**:
Hevy Fatigue monitoring at the repo root: daily check-ins, Hevy imports, the dashboard, the AI Coach and its settings. Its files are `main.py`, `database.py` (SQLAlchemy, `DB_PATH`) and `hevy_client.py`.
_Avoid_: Backend, server (both apps run on the same server)

**Training app**:
The workout logger mounted at `/training` (historically called Rackbook): the Log, Microcycles, Recent, Progress, Stress and RPE Charts pages. Its files are `rackbook/main.py`, `rackbook/database.py` (stdlib sqlite3, `RACKBOOK_DB_PATH`) and `rackbook/hevy_client.py`. The two databases are never merged.
_Avoid_: Logger backend, Rackbook container (it no longer runs on its own)

## Words that mean different things

**Daily fatigue**:
The host's whole-body readiness picture from check-ins and imported training load: the dashboard's Fatigue Trend, training state and daily recommendation.
_Avoid_: Fatigue (unqualified)

**Movement fatigue observations**:
The training app's per-movement trend rules in `rackbook/fatigue.py` (TS trend tracker), with comparability checks in `fatigue_context.py` and reviewed workload links in `fatigue_relationships.py`. Descriptive only; they never change prescriptions.
_Avoid_: Fatigue score, daily fatigue

**Model trial**:
The optional blinded comparison of a shared performance model, in `rackbook/fatigue_trial.py` with its `_legacy`, `_replay` and `_smoother` helpers. Frozen trial records are never regenerated.
_Avoid_: Fatigue model, daily fatigue

