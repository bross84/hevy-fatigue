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
A movement's stress index divided across movement patterns by its exercise mapping and summed per calendar week.
_Avoid_: Pattern Stress, weekly SI

**Pattern Stress**:
The dashboard card showing each movement pattern's decaying training load alongside soreness and a gradual fatigue trend. A different quantity from the stress index.
_Avoid_: Stress index, pattern stress index

**Plan proposal**:
A week of training the AI coach suggests in a reply. It is advice until the athlete saves it as a draft microcycle.
_Avoid_: AI plan, recommendation

**Draft microcycle**:
An inactive saved week, created from a plan proposal or by hand, that the athlete reviews and activates.
_Avoid_: Pending plan, AI-applied plan
