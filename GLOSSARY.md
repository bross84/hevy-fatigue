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
One saved plan of training days, completed in order at the athlete's own pace. It is not a calendar week and has no fixed length in days.
_Avoid_: Week, calendar week

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
